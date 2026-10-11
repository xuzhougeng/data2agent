#!/usr/bin/env python
"""source_data_py: journal Source Data / supplementary workbooks -> tidy `figures` panels in a contract package.

Three steps; the agent's judgement sits between probe and apply:

  run.py probe  raw/ --out work/source_data.draft.json      # every sheet: preview rows + a guessed cleaning recipe
  (agent edits the draft: layout, variable names, units, captions, chart, related stats panels -> work/source_data.json)
  run.py apply  pkg/ work/source_data.json                   # deterministic: recipe -> one tidy parquet per panel + manifest

  run.py pkg/ --xlsx book.xlsx ...                           # shortcut: probe + apply the guesses unchanged

Recipe (JSON). Top level: {"source_dir", "layouts": {name: recipe}, "figures": [{id, label, caption, panels: [panel]}]}.
A panel is {id, label, file, sheet, "like": <layout name>, ...recipe overrides}. Recipe keys:
  skip_rows        title rows above the table (their text becomes sheet_caption)
  rows, cols       [start, end] 0-based, end exclusive, null = open; cut one block out of a sheet (side-by-side tables)
  layout           wide_rows | grouped_columns | columns | long | table
    wide_rows        leading label columns (`labels`: names, `ffill`: which to fill down), then one value per column
                     -> long rows: labels..., replicate, <value>
    grouped_columns  header row with group names over blank cells (merged header); optional `sub_header` row;
                     optional `index` (name of the first column, e.g. "time") -> long rows: index?, group, replicate|sub, <value>
    columns          one header row, each column a group, rows are replicates -> long rows: group, replicate, <value>
    long             already one row per observation; `header_row`, `ffill`, optional `melt`
                     {"columns": [...] | "pattern": regex, "name": "site_year", "value": "yield"}
    table            keep as is (statistics, primers, accessions); no chart
    stacked          several titled blocks down one sheet (a statistics workbook: "Fig.1c / Lesion length / contrast ... ");
                     `block_pattern` (default ^(Extended Data |ED )?Fig) starts a block on its title row; each block becomes
                     a table panel <id>_<block> and is attached as `related` to the data panel whose id starts with
                     <figure>_<panel letters> (Fig.1g-SKZ -> fig1_1g)
  value, unit      name of the value column (default "value") and its unit
  group, index     column names for grouped_columns / columns (defaults "group", "index")
  split            {"<col>": {"pattern": regex with groups, "into": [names]}} derive columns from a label (Repeat 1-Shanghai_2021)
  rename, drop     column renames / drops after tidying
  caption          legend sentence for the panel (default: text found above the table)
  chart            {"type": strip|box|bar|line|scatter|table, "x", "y", "color", "facet", "value_label"}
  related          ids of other panels shown under this one (e.g. the planned-contrast statistics for the panel)
  feature_col, features   link a column to the feature page
Nothing is computed; every number in a panel parquet is a cell of the workbook.
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
STATS_HINTS = {"estimate", "se", "df", "t.ratio", "p.value", "p-value", "pvalue", "padj", "statistic"}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "x"


def is_blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip())


def is_num(v) -> bool:
    if is_blank(v) or isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        float(str(v).replace(",", ""))
        return True
    except ValueError:
        return False


def fig_id_from(name: str) -> tuple[str, str]:
    m = FIG_RE.search(name)
    if not m:
        return slug(Path(name).stem), Path(name).stem
    n, low = m.group(1), name.lower()
    if "extended" in low or re.search(r"\bed\s*fig", low):
        return f"edfig{n.lower()}", f"Extended Data Fig. {n}"
    if "suppl" in low or re.search(r"\bs\s*fig|fig\.?\s*s\d", low):
        return f"sfig{n.lower()}", f"Supplementary Fig. {n}"
    return f"fig{n.lower()}", f"Figure {n}"


def panel_slug(sheet: str, fig_id: str) -> str:
    m = re.search(r"(\d+)\s*([a-z](?:\s*[-–,]\s*[a-z])*)?\s*$", sheet.strip(), re.I)
    tail = slug(m.group(0)) if m else slug(sheet)
    return tail if tail.startswith(fig_id) else f"{fig_id}_{tail}"


# ---------------------------------------------------------------- reading + guessing

def read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=None) if path.suffix.lower() in (".xlsx", ".xls", ".xlsm") else pd.read_csv(path, header=None, sep=None, engine="python")
    return raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)


def cut(raw: pd.DataFrame, rec: dict) -> pd.DataFrame:
    r0, r1 = (rec.get("rows") or [None, None])
    c0, c1 = (rec.get("cols") or [None, None])
    df = raw.iloc[r0:r1, c0:c1]
    return df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)


def title_rows(df: pd.DataFrame) -> int:
    """Rows above the table: at most one non-blank cell each, and the next row has >= 2 cells."""
    n = 0
    for i in range(min(len(df) - 1, 4)):
        cells = [c for c in df.iloc[i].tolist() if not is_blank(c)]
        nxt = [c for c in df.iloc[i + 1].tolist() if not is_blank(c)]
        if len(cells) <= 1 and len(nxt) >= 2:
            n = i + 1
        else:
            break
    return n


def guess(df: pd.DataFrame) -> dict:
    """A cleaning recipe for one block, from its first rows. The agent corrects it."""
    skip = title_rows(df)
    body = df.iloc[skip:].reset_index(drop=True)
    rec = {"skip_rows": skip}
    if body.empty:
        return {**rec, "layout": "table"}
    h = body.iloc[0].tolist()
    htext = [str(c).strip().lower() for c in h if not is_blank(c)]
    if STATS_HINTS & set(htext):
        return {**rec, "layout": "table", "header_row": 0}
    if {"block", "genotype", "plants"} <= set(htext) or sum(is_num(c) for c in h) == 0 and len(htext) == len(h) and len(body) > 40:
        return {**rec, "layout": "long", "header_row": 0, "ffill": [str(c) for c in h[:2] if not is_blank(c)]}
    # leading text cells on data rows -> wide_rows
    lead = []
    for i in range(1, min(len(body), 6)):
        row = body.iloc[i].tolist()
        k = 0
        while k < len(row) and not is_num(row[k]):
            k += 1
        lead.append(k)
    k_data0 = 0
    while k_data0 < len(h) and not is_num(h[k_data0]):
        k_data0 += 1
    first_is_data = k_data0 < len(h) and sum(is_num(c) for c in h) >= len(h) // 2
    if first_is_data:  # no header at all: row 0 already holds values
        k = max(lead + [k_data0]) if lead else k_data0
        return {**rec, "layout": "wide_rows", "labels": [f"label{i + 1}" for i in range(k)], "ffill": [f"label{i + 1}" for i in range(k)]}
    blanks = sum(is_blank(c) for c in h[1:])
    if blanks and len(htext) >= 2:
        return {**rec, "layout": "grouped_columns", "index": None if is_blank(h[0]) or len(body) < 2 or is_num(body.iloc[1, 0]) is False else str(h[0])}
    if lead and max(lead) >= 1 and max(lead) < len(h) - 1 and sum(is_num(c) for c in body.iloc[1].tolist()) >= 2:
        k = max(lead)
        return {**rec, "layout": "wide_rows", "labels": [f"label{i + 1}" for i in range(k)], "ffill": [f"label{i + 1}" for i in range(k)], "header_row": 0}
    if len(htext) == len(h) and all(is_num(c) for c in body.iloc[1].tolist() if not is_blank(c)):
        return {**rec, "layout": "columns"}
    return {**rec, "layout": "table", "header_row": 0}


# ---------------------------------------------------------------- tidying

def dedupe(names):
    out, seen = [], {}
    for j, c in enumerate(names):
        n = str(c).strip() if not is_blank(c) else f"col_{j + 1}"
        if n in seen:
            seen[n] += 1
            n = f"{n}_{seen[n]}"
        else:
            seen[n] = 1
        out.append(n)
    return out


def typed(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        s = df[c]
        num = pd.to_numeric(s.astype(str).str.replace(",", "", regex=False), errors="coerce")
        if s.notna().any() and num.notna().sum() >= 0.9 * s.notna().sum():
            df[c] = num.astype(float)
        else:
            df[c] = s.map(lambda v: None if is_blank(v) else str(v).strip())
    return df


def tidy(df: pd.DataFrame, rec: dict) -> tuple[pd.DataFrame, str]:
    """Apply one recipe to a cut block. Returns (tidy frame, caption text found above the table)."""
    skip = rec.get("skip_rows", 0)
    caption = " ".join(str(c).strip() for i in range(skip) for c in df.iloc[i].tolist() if not is_blank(c))
    body = df.iloc[skip:].reset_index(drop=True)
    value = rec.get("value", "value")
    layout = rec["layout"]

    if layout == "wide_rows":
        labels = rec["labels"]
        k = len(labels)
        if "header_row" in rec:
            body = body.iloc[rec["header_row"] + 1:].reset_index(drop=True)
        lab = body.iloc[:, :k].copy()
        lab.columns = labels
        for c in rec.get("ffill", []):
            lab[c] = lab[c].ffill()
        vals = body.iloc[:, k:]
        vals.columns = range(1, vals.shape[1] + 1)
        out = pd.concat([lab, vals], axis=1).melt(id_vars=labels, var_name="replicate", value_name=value)
        out[value] = pd.to_numeric(out[value], errors="coerce")
        out = out.dropna(subset=[value]).sort_values(labels + ["replicate"], kind="stable")
        for c in labels:
            out[c] = out[c].map(lambda v: None if is_blank(v) else str(v).strip())

    elif layout in ("grouped_columns", "columns"):
        h = body.iloc[0].tolist()
        index = rec.get("index")
        start = 1 if index else 0
        groups = []
        last = None
        for c in h[start:]:
            if not is_blank(c):
                last = str(c).strip()
            groups.append(last)
        sub = None
        if rec.get("sub_header"):
            sub = [None if is_blank(c) else str(c).strip() for c in body.iloc[1].tolist()[start:]]
            data = body.iloc[2:]
        else:
            data = body.iloc[1:]
        recs = []
        gname = rec.get("group", "group")
        counters = {}
        col_rep = []
        for g in groups:
            counters[g] = counters.get(g, 0) + 1
            col_rep.append(counters[g])
        for i in range(len(data)):
            row = data.iloc[i].tolist()
            idx = row[0] if index else None
            for j, g in enumerate(groups):
                v = row[start + j]
                if is_blank(v):
                    continue
                r = {gname: g, "replicate" if sub is None else "sub": col_rep[j] if sub is None else sub[j], value: v}
                if index:
                    r = {index: idx, **r}
                if layout == "columns":
                    r = {gname: g, "replicate": i + 1, value: v}
                recs.append(r)
        out = pd.DataFrame(recs)
        out[value] = pd.to_numeric(out[value], errors="coerce")
        out = out.dropna(subset=[value])
        if index and index in out.columns:
            num = pd.to_numeric(out[index], errors="coerce")
            if num.notna().sum() == out[index].notna().sum():
                out[index] = num

    elif layout == "long":
        hr = rec.get("header_row", 0)
        names = dedupe(body.iloc[hr].tolist())
        out = body.iloc[hr + 1:].reset_index(drop=True)
        out.columns = names
        ren = rec.get("rename", {})
        out = typed(out).rename(columns=ren)  # rename first so ffill/melt can use the final names
        for c in rec.get("ffill", []):
            c = ren.get(c, c)
            if c not in out.columns:
                raise KeyError(f"ffill column {c!r} not in {list(out.columns)}")
            out[c] = out[c].ffill()
        melt = rec.get("melt")
        if melt:
            cols = melt.get("columns") or [c for c in out.columns if re.search(melt["pattern"], c)]
            ids = [c for c in out.columns if c not in cols]
            out = out.melt(id_vars=ids, value_vars=cols, var_name=melt.get("name", "variable"), value_name=melt.get("value", value))
            out = out.dropna(subset=[melt.get("value", value)])

    else:  # table
        hr = rec.get("header_row", 0)
        if hr is None:  # headerless: col_1, col_2, ...
            out = body.reset_index(drop=True)
            out.columns = [f"col_{j + 1}" for j in range(out.shape[1])]
        else:
            names = dedupe(body.iloc[hr].tolist())
            out = body.iloc[hr + 1:].reset_index(drop=True)
            out.columns = names
        out = typed(out)

    for col, sp in (rec.get("split") or {}).items():
        if col in out.columns:
            ext = out[col].astype(str).str.extract(sp["pattern"])
            ext.columns = sp["into"]
            for c in sp["into"]:
                out[c] = ext[c].where(ext[c].notna(), None)
                num = pd.to_numeric(out[c], errors="coerce")
                if out[c].notna().any() and num.notna().sum() == out[c].notna().sum():
                    out[c] = num
    out = out.drop(columns=[c for c in rec.get("drop", []) if c in out.columns])
    out = out.rename(columns=rec.get("rename", {}))
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = out[c].map(lambda v: None if is_blank(v) else str(v).strip() if not isinstance(v, str) else v.strip())
    return out.reset_index(drop=True), caption


def split_stacked(df: pd.DataFrame, rec: dict):
    """Yield (block id, title, caption, table) for every titled block down a sheet."""
    pat = re.compile(rec.get("block_pattern", r"^\s*(Extended Data |ED )?Fig"), re.I)
    col0 = df.iloc[:, 0].tolist()
    starts = [i for i, v in enumerate(col0) if not is_blank(v) and pat.search(str(v)) and sum(not is_blank(c) for c in df.iloc[i].tolist()) <= 2]
    for n, s in enumerate(starts):
        e = starts[n + 1] if n + 1 < len(starts) else len(df)
        block = df.iloc[s:e].reset_index(drop=True)
        title = str(block.iloc[0, 0]).strip()
        hdr = next((i for i in range(1, len(block)) if sum(not is_blank(c) for c in block.iloc[i].tolist()) >= 3), None)
        cap_rows = range(1, hdr if hdr is not None else len(block))
        caption = " · ".join(" ".join(str(c).strip() for c in block.iloc[i].tolist() if not is_blank(c)) for i in cap_rows if any(not is_blank(c) for c in block.iloc[i].tolist()))
        if hdr is None:
            continue
        names = dedupe(block.iloc[hdr].tolist())
        body = block.iloc[hdr + 1:].reset_index(drop=True)
        body.columns = names
        body = typed(body.dropna(how="all")).rename(columns=rec.get("rename", {}))
        for c in rec.get("ffill", names[:1]):
            if c in body.columns:
                body[c] = body[c].ffill()
        yield slug(re.sub(r"^\s*(extended data |ed )?fig\.?\s*", "", title, flags=re.I)), title, caption, body.reset_index(drop=True)


def describe(df: pd.DataFrame) -> list[dict]:
    cols = []
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append({"name": str(c), "label": str(c), "dtype": "float", "role": "numeric"})
        else:
            n = df[c].nunique(dropna=True)
            cols.append({"name": str(c), "label": str(c), "dtype": "string", "role": "facet" if 1 < n <= 60 and n < len(df) else "text"})
    return cols


def default_chart(df: pd.DataFrame, rec: dict) -> dict:
    layout, value = rec["layout"], rec.get("value", "value")
    if layout == "wide_rows":
        labels = rec["labels"]
        x = labels[-1]
        facet = labels[0] if len(labels) > 1 else None
        n_per = df.groupby(labels)[value].size().max() if len(df) else 0
        return {k: v for k, v in {"type": "strip" if n_per <= 40 else "box", "x": x, "y": value, "facet": facet}.items() if v}
    if layout in ("grouped_columns", "columns"):
        g = rec.get("group", "group")
        if rec.get("index"):
            return {"type": "line", "x": rec["index"], "y": value, "color": g}
        return {"type": "strip", "x": g, "y": value}
    if layout == "long":
        melt = rec.get("melt")
        num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        cat = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
        if melt:
            return {"type": "box", "x": cat[-2] if len(cat) > 1 else cat[0], "y": melt.get("value", value), "facet": melt.get("name", "variable")}
        if cat and num:
            return {"type": "box", "x": cat[0], "y": num[-1]}
    return {"type": "table"}


# ---------------------------------------------------------------- commands

def probe(paths: list[Path], out: Path):
    draft = {"source_dir": str(paths[0].parent if len(paths) == 1 and paths[0].is_file() else paths[0]), "layouts": {}, "figures": []}
    files = sorted(p for d in paths for p in ([d] if d.is_file() else d.rglob("*")) if p.suffix.lower() in (".xlsx", ".xls", ".xlsm", ".csv", ".tsv"))
    by_fig = {}
    for f in files:
        fid_file, label_file = fig_id_from(f.name)
        file_has_fig = bool(FIG_RE.search(f.name))
        if f.suffix.lower() in (".csv", ".tsv"):
            sheets = {f.stem: read_sheet(f, "")}
        else:
            sheets = {s: read_sheet(f, s) for s in pd.ExcelFile(f).sheet_names}
        for sheet, raw in sheets.items():
            if raw.empty:
                continue
            fid, label = (fid_file, label_file) if file_has_fig or not FIG_RE.search(sheet) else fig_id_from(sheet)
            fig = by_fig.setdefault(fid, {"id": fid, "label": label, "caption": "", "source": f.name, "panels": []})
            rec = guess(raw)
            preview = raw.head(6).fillna("").astype(str).apply(lambda r: " | ".join(v[:20] for v in r[:14]) + (" | …" if raw.shape[1] > 14 else ""), axis=1).tolist()
            pid = panel_slug(sheet, fid)
            while any(p["id"] == pid for p in fig["panels"]):
                pid += "_b"
            fig["panels"].append({"id": pid, "label": sheet, "file": f.name, "sheet": sheet, **rec, "_shape": list(raw.shape), "_preview": preview})
    draft["figures"] = list(by_fig.values())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(draft, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"draft": str(out), "files": len(files), "panels": sum(len(f["panels"]) for f in draft["figures"]),
                      "layouts_guessed": pd.Series([p["layout"] for f in draft["figures"] for p in f["panels"]]).value_counts().to_dict()}, indent=2))


def apply(pkg: Path, spec: dict, replace: bool):
    m = contract.load(pkg) if (pkg / "manifest.json").exists() else None
    if m is None:
        sys.exit("apply needs an existing package (manifest.json); create one with --init first")
    if replace:
        m["figures"] = []
    m.setdefault("figures", [])
    by_id = {f["id"]: f for f in m["figures"]}
    src = Path(spec.get("source_dir", "."))
    layouts = spec.get("layouts", {})
    taken = {p["id"] for f in m["figures"] for p in f["panels"]}
    summary, errors = [], []
    cache = {}
    for fig in spec["figures"]:
        target = by_id.get(fig["id"])
        if not target:
            target = {"id": fig["id"], "label": fig["label"], "panels": []}
            m["figures"].append(target)
            by_id[fig["id"]] = target
        for k in ("label", "caption", "source"):
            if fig.get(k):
                target[k] = fig[k]
        for p in fig["panels"]:
            if p.get("skip") or p["id"] in taken:
                continue
            rec = {**layouts.get(p.get("like", ""), {}), **{k: v for k, v in p.items() if not k.startswith("_")}}
            key = (rec["file"], rec["sheet"])
            if key not in cache:
                cache[key] = read_sheet(src / rec["file"], rec["sheet"])
            if rec["layout"] == "stacked":
                for bid, blabel, bcap, bdf in split_stacked(cut(cache[key], rec), rec):
                    pid = f"{p['id']}_{bid}"
                    if pid in taken or bdf.empty:
                        continue
                    rel = f"data/figures/{pid}.parquet"
                    (pkg / rel).parent.mkdir(parents=True, exist_ok=True)
                    pq.write_table(pa.Table.from_pandas(bdf, preserve_index=False), pkg / rel, compression="zstd")
                    panel = {"id": pid, "label": blabel, "sheet": rec["sheet"], "source": rec["file"], "path": rel, "rows": int(len(bdf)),
                             "columns": describe(bdf), "chart": {"type": "table"}, "layout": "table", "caption": bcap[:2000], "_block_title": blabel}
                    target["panels"].append(panel)
                    taken.add(pid)
                    summary.append({"panel": pid, "layout": "stacked/table", "rows": panel["rows"], "columns": [c["name"] for c in panel["columns"]], "chart": "table"})
                continue
            try:
                df, sheet_caption = tidy(cut(cache[key], rec), rec)
            except Exception as e:  # noqa: BLE001
                errors.append({"panel": p["id"], "error": f"{type(e).__name__}: {e}"})
                continue
            if df.empty:
                errors.append({"panel": p["id"], "error": "no rows after cleaning"})
                continue
            rel = f"data/figures/{p['id']}.parquet"
            (pkg / rel).parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.Table.from_pandas(df, preserve_index=False), pkg / rel, compression="zstd")
            chart = rec.get("chart") or default_chart(df, rec)
            if rec.get("unit") and "value_label" not in chart:
                chart["value_label"] = f"{rec.get('value', 'value').replace('_', ' ')} ({rec['unit']})"
            panel = {"id": p["id"], "label": p.get("label") or rec["sheet"], "sheet": rec["sheet"], "source": rec["file"], "path": rel, "rows": int(len(df)),
                     "columns": describe(df), "chart": chart, "layout": rec["layout"]}
            cap = rec.get("caption") or sheet_caption
            if cap:
                panel["caption"] = cap[:2000]
            if sheet_caption and rec.get("caption"):
                panel["sheet_caption"] = sheet_caption[:500]
            for k in ("related", "feature_col", "features", "unit", "image"):
                if rec.get(k):
                    panel[k] = rec[k]
            target["panels"].append(panel)
            taken.add(p["id"])
            summary.append({"panel": p["id"], "layout": rec["layout"], "rows": panel["rows"], "columns": [c["name"] for c in panel["columns"]], "chart": chart["type"]})
    m["figures"] = [f for f in m["figures"] if f["panels"]]
    all_panels = [p for f in m["figures"] for p in f["panels"]]
    for sp in all_panels:
        title = sp.pop("_block_title", None)
        if not title:
            continue
        fid, _ = fig_id_from(title)
        mm = re.search(r"(\d+)\s*([a-z])", title, re.I)
        prefix = f"{fid}_{mm.group(1)}{mm.group(2).lower()}" if mm else None
        for dp in all_panels:
            if prefix and dp is not sp and dp.get("layout") != "table" and dp["id"].startswith(prefix):
                dp.setdefault("related", [])
                if sp["id"] not in dp["related"]:
                    dp["related"].append(sp["id"])
    ids = {p["id"] for f in m["figures"] for p in f["panels"]}
    for f in m["figures"]:
        for p in f["panels"]:
            if p.get("related"):
                missing = [r for r in p["related"] if r not in ids]
                if missing:
                    errors.append({"panel": p["id"], "error": f"related panels not found: {missing}"})
    contract.finalize(pkg, m)
    print(json.dumps({"package": str(pkg), "figures": len(m["figures"]), "panels": len(summary), "errors": errors, "applied": summary}, indent=1, ensure_ascii=False))
    if errors:
        sys.exit(1)


def init_package(pkg: Path, a):
    """A package that holds only figures / supplementary tables (no omics matrix)."""
    pkg.mkdir(parents=True, exist_ok=True)
    if (pkg / "manifest.json").exists():
        return
    m = {"contract_version": 1, "id": a.id or slug(pkg.name), "title": a.title or pkg.name, "short_title": a.short_title or a.id or pkg.name, "kind": "other",
         "version": "0.1.0", "tables": {}, "matrices": [], "embeddings": [], "results": [], "aggregates": [], "assets": [], "figures": [], "stats": {}, "files": {},
         "methods": "Source data and supplementary tables as published; each figure panel is one tidy table whose values are the workbook cells, reshaped (never recomputed) by the source_data_py adapter."}
    contract.finalize(pkg, m)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    pp = sub.add_parser("probe")
    pp.add_argument("paths", nargs="+", type=Path)
    pp.add_argument("--out", type=Path, default=Path("work/source_data.draft.json"))
    pa_ = sub.add_parser("apply")
    pa_.add_argument("pkg", type=Path)
    pa_.add_argument("spec", type=Path)
    pa_.add_argument("--replace", action="store_true")
    pa_.add_argument("--init", action="store_true", help="create a figures-only package when pkg has no manifest")
    pa_.add_argument("--id")
    pa_.add_argument("--title")
    pa_.add_argument("--short-title")
    # shortcut: run.py pkg --xlsx ... -> probe + apply the guesses unchanged
    legacy = argparse.ArgumentParser()
    legacy.add_argument("pkg_legacy", type=Path)
    legacy.add_argument("--xlsx", action="append", default=[])
    legacy.add_argument("--csv", action="append", default=[])
    legacy.add_argument("--replace", action="store_true")
    legacy.add_argument("--init", action="store_true")
    legacy.add_argument("--id")
    legacy.add_argument("--title")
    legacy.add_argument("--short-title")
    argv = sys.argv[1:]
    if argv and argv[0] not in ("probe", "apply", "-h", "--help"):
        a = legacy.parse_args(argv)
        files = [Path(x.split(":")[0]) for x in a.xlsx + a.csv]
        if not files:
            sys.exit("give --xlsx/--csv, or use the probe / apply subcommands")
        draft = a.pkg_legacy / "work_source_data.draft.json"
        probe(files, draft)
        spec = json.loads(draft.read_text())
        spec["source_dir"] = "."
        for f in spec["figures"]:
            for p in f["panels"]:
                p["file"] = str(next(x for x in files if x.name == p["file"]))
        draft.unlink()
        if a.init:
            init_package(a.pkg_legacy, a)
        apply(a.pkg_legacy, spec, a.replace)
        return
    a = ap.parse_args(argv)
    if a.cmd == "probe":
        probe(a.paths, a.out)
    elif a.cmd == "apply":
        if a.init:
            init_package(a.pkg, a)
        apply(a.pkg, json.loads(a.spec.read_text()), a.replace)


if __name__ == "__main__":
    main()
