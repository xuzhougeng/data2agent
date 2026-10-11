#!/usr/bin/env python
"""source_data_py adapter: a journal "Source Data" workbook (one sheet per figure panel) -> `figures` in an existing package.

usage: run.py pkg --xlsx "Source Data Fig1.xlsx[:fig1:Figure 1]" [--xlsx ...] [--csv "panel.csv:fig2:Figure 2:2b"] [--replace]

Each sheet becomes one panel: the first row that looks like a header starts the table, text above it becomes the
caption, every column is typed (numeric when >= 90% of its values parse), and a chart hint is inferred:
  columns  every numeric column is a group, replicates down the rows   (bar + dots / box figures)
  group    x = the categorical column, y = the first numeric column
  scatter  two numeric columns, many rows
  none     anything else: table only
The agent corrects captions/charts in manifest.json (curation) when the heuristic is wrong. Nothing is computed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import contract  # noqa: E402

FIG_RE = re.compile(r"(?:extended\s*data\s*|supplementary\s*|supp\.?\s*|ed\s*|s)?fig(?:ure)?\.?\s*_?\s*([A-Za-z]?\d+)", re.I)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "x"


def fig_id_from(name: str) -> tuple[str, str]:
    """'Source Data Fig. 3.xlsx' -> ('fig3', 'Figure 3'); 'Extended Data Fig 2' -> ('edfig2', 'Extended Data Fig. 2')."""
    m = FIG_RE.search(name)
    if not m:
        return slug(Path(name).stem), Path(name).stem
    n = m.group(1)
    low = name.lower()
    if "extended" in low or re.search(r"\bed\s*fig", low):
        return f"edfig{n.lower()}", f"Extended Data Fig. {n}"
    if "suppl" in low or re.search(r"\bs\s*fig|fig\.?\s*s\d", low):
        return f"sfig{n.lower()}", f"Supplementary Fig. {n}"
    return f"fig{n.lower()}", f"Figure {n}"


def panel_slug(sheet: str, fig_id: str) -> str:
    m = re.search(r"(\d+)\s*([a-z](?:\s*[-–,]\s*[a-z])*)?\s*$", sheet.strip(), re.I)
    tail = slug(m.group(0)) if m else slug(sheet)
    return f"{fig_id}_{tail}" if not tail.startswith(fig_id) else tail


def is_num(v) -> bool:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return False
    try:
        float(str(v).replace(",", ""))
        return True
    except ValueError:
        return False


def split_sheet(raw: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Find the header row of a loosely formatted sheet. Returns (table, caption)."""
    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        return raw, ""
    rows = raw.values.tolist()
    header = None
    for i, r in enumerate(rows[:-1]):
        cells = [c for c in r if c is not None and not (isinstance(c, float) and pd.isna(c))]
        if len(cells) >= 2 and sum(not is_num(c) for c in cells) >= len(cells) * 0.6:
            nxt = [c for c in rows[i + 1] if c is not None and not (isinstance(c, float) and pd.isna(c))]
            if nxt and any(is_num(c) for c in nxt):
                header = i
                break
    if header is None:
        header = 0
    caption = " ".join(str(c).strip() for r in rows[:header] for c in r if c is not None and not (isinstance(c, float) and pd.isna(c)) and str(c).strip())
    names, seen = [], {}
    for j, c in enumerate(rows[header]):
        n = str(c).strip() if c is not None and not (isinstance(c, float) and pd.isna(c)) else f"col_{j + 1}"
        if n in seen:
            seen[n] += 1
            n = f"{n}_{seen[n]}"
        else:
            seen[n] = 1
        names.append(n)
    df = pd.DataFrame(rows[header + 1:], columns=names).dropna(how="all")
    for c in df.columns:
        s = df[c]
        num = pd.to_numeric(s.astype(str).str.replace(",", "", regex=False), errors="coerce")
        if s.notna().any() and num.notna().sum() >= 0.9 * s.notna().sum():
            df[c] = num
        else:
            df[c] = s.where(s.notna(), None).map(lambda v: None if v is None else str(v))
    return df.reset_index(drop=True), caption


def describe(df: pd.DataFrame) -> tuple[list[dict], dict]:
    cols, numeric, text = [], [], []
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append({"name": c, "label": c, "dtype": "float", "role": "numeric"})
            numeric.append(c)
        else:
            n = df[c].nunique(dropna=True)
            cols.append({"name": c, "label": c, "dtype": "string", "role": "facet" if 1 < n <= 50 and n < len(df) else "text"})
            text.append(c)
    n = len(df)
    if numeric and not text:
        chart = {"type": "scatter", "x": numeric[0], "y": numeric[1]} if len(numeric) == 2 and n > 30 else {"type": "columns"}
    elif text and numeric:
        x = text[0]
        chart = {"type": "group", "x": x, "y": numeric[0]} if df[x].nunique() < n or n <= 30 else {"type": "none"}
    else:
        chart = {"type": "none"}
    return cols, chart


def add_panel(m: dict, pkg: Path, fig: dict, sheet: str, df: pd.DataFrame, caption: str, label: str | None = None):
    pid = panel_slug(sheet, fig["id"])
    taken = {p["id"] for f in m["figures"] for p in f["panels"]}
    base, k = pid, 2
    while pid in taken:
        pid, k = f"{base}_{k}", k + 1
    rel = f"data/figures/{pid}.parquet"
    (pkg / rel).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), pkg / rel, compression="zstd")
    cols, chart = describe(df)
    panel = {"id": pid, "label": label or sheet, "sheet": sheet, "path": rel, "rows": int(len(df)), "columns": cols, "chart": chart}
    if caption:
        panel["caption"] = caption[:2000]
    fig["panels"].append(panel)
    return panel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pkg", type=Path)
    ap.add_argument("--xlsx", action="append", default=[], help="workbook[:fig_id:Label]; one sheet per panel")
    ap.add_argument("--csv", action="append", default=[], help="file.csv:fig_id:Label:panel_label; one panel")
    ap.add_argument("--replace", action="store_true", help="drop figures already in the manifest first")
    a = ap.parse_args()
    if not a.xlsx and not a.csv:
        sys.exit("give at least one --xlsx or --csv")
    m = contract.load(a.pkg)
    if a.replace:
        m["figures"] = []
    m.setdefault("figures", [])
    by_id = {f["id"]: f for f in m["figures"]}

    def figure(fid: str, label: str, source: str) -> dict:
        if fid not in by_id:
            by_id[fid] = {"id": fid, "label": label, "source": source, "panels": []}
            m["figures"].append(by_id[fid])
        return by_id[fid]

    summary = []
    for spec in a.xlsx:
        parts = spec.split(":")
        path = Path(parts[0])
        fid, label = fig_id_from(path.name)
        if len(parts) > 1 and parts[1]:
            fid = parts[1]
        if len(parts) > 2 and parts[2]:
            label = parts[2]
        fig = figure(fid, label, path.name)
        book = pd.read_excel(path, sheet_name=None, header=None)
        for sheet, raw in book.items():
            df, caption = split_sheet(raw)
            if df.empty or df.shape[1] < 1:
                summary.append({"figure": fid, "sheet": sheet, "skipped": "empty"})
                continue
            p = add_panel(m, a.pkg, fig, sheet, df, caption)
            summary.append({"figure": fid, "panel": p["id"], "rows": p["rows"], "columns": len(p["columns"]), "chart": p["chart"]["type"]})
    for spec in a.csv:
        parts = spec.split(":")
        path = Path(parts[0])
        fid, label = fig_id_from(path.name)
        fid = parts[1] if len(parts) > 1 and parts[1] else fid
        label = parts[2] if len(parts) > 2 and parts[2] else label
        plabel = parts[3] if len(parts) > 3 else path.stem
        raw = pd.read_csv(path, header=None, sep=None, engine="python")
        df, caption = split_sheet(raw)
        p = add_panel(m, a.pkg, figure(fid, label, path.name), plabel, df, caption)
        summary.append({"figure": fid, "panel": p["id"], "rows": p["rows"], "columns": len(p["columns"]), "chart": p["chart"]["type"]})

    contract.finalize(a.pkg, m)
    print(json.dumps({"package": str(a.pkg), "figures": len(m["figures"]), "panels": summary}, indent=2))


if __name__ == "__main__":
    main()
