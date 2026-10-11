#!/usr/bin/env python
"""Sniff raw input files and write work/inventory.json: what each file is, candidate matrices / sample tables /
DE tables, the suggested omics kind and adapter, and a deployment-tier suggestion from sizes.

usage: probe.py raw/ [--samples work/samples.csv] [--out work/inventory.json]
Reads only headers / first rows (and h5ad metadata); never loads a full matrix.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
from pathlib import Path

import pandas as pd

DE_HINTS = {"log2foldchange", "logfc", "log2fc", "padj", "fdr", "adj.p.val", "pvalue", "p.value", "qvalue"}
SKIP_SUFFIX = {".json", ".md", ".sha256", ".part", ".log"}


def open_text(path: Path, n_bytes=2_000_000) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as f:
            return f.read(n_bytes).decode("utf-8", "replace")
    with open(path, "rb") as f:
        return f.read(n_bytes).decode("utf-8", "replace")


def sniff_table(path: Path) -> dict:
    """Classify a delimited text table from its head."""
    text = open_text(path)
    if text.startswith("!") or "!Series_title" in text[:5000]:
        return {"kind": "geo_series_matrix"}
    lines = text.splitlines()
    head = [ln for ln in lines if not ln.startswith(("#", "!"))][:60]
    if len(head) < 2:
        return {"kind": "unknown", "note": "fewer than 2 rows"}
    sep = "," if path.name.replace(".gz", "").endswith(".csv") else "\t" if "\t" in head[0] else ","
    try:
        df = pd.read_csv(io.StringIO("\n".join(head)), sep=sep, nrows=50)
    except Exception as e:  # noqa: BLE001
        return {"kind": "unknown", "note": f"parse failed: {e}"}
    cols = [str(c) for c in df.columns]
    low = [c.lower() for c in cols]
    numeric = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    frac_num = len(numeric) / max(1, len(cols))
    info = {"columns": len(cols), "first_columns": cols[:8], "numeric_columns": len(numeric), "sep": "tab" if sep == "\t" else "comma"}
    est_rows = max(0, sum(1 for _ in lines) - 1)
    info["rows_in_head"] = est_rows if len(text) < 2_000_000 else f">= {est_rows} (truncated read)"
    if DE_HINTS & set(low):
        info["kind"] = "de_table"
        return info
    if len(numeric) >= 3 and frac_num > 0.6:
        vals = df[numeric].to_numpy(dtype=float)
        finite = vals[~pd.isna(vals)]
        is_int = bool(len(finite)) and bool((finite == finite.round()).mean() > 0.95)
        in_unit = bool(len(finite)) and bool(finite.min() >= 0 and finite.max() <= 1.0)
        info["integer_values"] = is_int
        info["kind"] = "count_matrix" if is_int else "beta_matrix" if in_unit else "expression_matrix"
        info["id_column"] = cols[0]
        info["sample_columns"] = numeric[:5] + (["…"] if len(numeric) > 5 else [])
        info["n_sample_columns"] = len(numeric)
        return info
    if len(cols) >= 3 and frac_num < 0.5:
        info["kind"] = "sample_table"
        return info
    info["kind"] = "table"
    return info


def sniff_h5ad(path: Path) -> dict:
    try:
        import anndata as ad
        a = ad.read_h5ad(path, backed="r")
        info = {"kind": "h5ad", "n_obs": int(a.n_obs), "n_vars": int(a.n_vars), "obs_columns": list(map(str, a.obs.columns))[:30],
                "obsm": list(a.obsm.keys()), "layers": list(a.layers.keys()), "has_raw": a.raw is not None,
                "raw_n_vars": int(a.raw.n_vars) if a.raw is not None else None, "uns": [k for k in a.uns.keys()][:20]}
        cats = {c: int(a.obs[c].nunique()) for c in a.obs.columns if str(a.obs[c].dtype) in ("category", "object", "str", "string")}
        info["candidate_group_columns"] = sorted([c for c, n in cats.items() if 2 <= n <= 50], key=lambda c: cats[c])
        a.file.close()
        return info
    except Exception as e:  # noqa: BLE001
        return {"kind": "h5ad", "note": f"could not open: {e}"}


def classify(path: Path) -> dict:
    name = path.name.lower()
    if path.suffix in SKIP_SUFFIX or name.startswith("."):
        return {"kind": "ignore"}
    if name.endswith(".h5ad"):
        return sniff_h5ad(path)
    if name.endswith((".h5", ".hdf5")):
        return {"kind": "hdf5", "note": "10x h5 or other HDF5; open with scanpy.read_10x_h5 if 10x"}
    if name.endswith((".mtx", ".mtx.gz")):
        return {"kind": "mtx", "note": "Matrix Market; expect barcodes/features alongside (10x)"}
    if name.endswith((".idat", ".idat.gz")):
        return {"kind": "idat"}
    if name.endswith(".pdf"):
        return {"kind": "paper_pdf"}
    if name.endswith((".xlsx", ".xls")):
        try:
            xl = pd.ExcelFile(path)
            return {"kind": "excel", "sheets": xl.sheet_names[:20]}
        except Exception as e:  # noqa: BLE001
            return {"kind": "excel", "note": str(e)}
    if name.endswith(("_series_matrix.txt.gz", "_series_matrix.txt")):
        return {"kind": "geo_series_matrix"}
    if name.endswith((".txt", ".tsv", ".csv", ".txt.gz", ".tsv.gz", ".csv.gz", ".tab", ".tab.gz")):
        return sniff_table(path)
    if name.endswith((".tar", ".tar.gz", ".tgz", ".zip")):
        return {"kind": "archive", "note": "extract into raw/ and re-run probe"}
    if name.endswith((".bam", ".fastq", ".fastq.gz", ".fq.gz", ".cram")):
        return {"kind": "raw_reads", "note": "reference only (assets); not loaded"}
    return {"kind": "unknown"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", type=Path)
    ap.add_argument("--samples", type=Path, help="sample sheet from geo_series_matrix.py (to match matrix headers)")
    ap.add_argument("--out", type=Path, default=Path("work/inventory.json"))
    a = ap.parse_args()

    files = []
    for p in sorted(a.raw.rglob("*")):
        if not p.is_file():
            continue
        info = classify(p)
        if info.get("kind") == "ignore":
            continue
        info.update({"path": str(p), "bytes": p.stat().st_size})
        files.append(info)

    kinds = [f["kind"] for f in files]
    matrices = [f for f in files if f["kind"] in ("count_matrix", "expression_matrix", "beta_matrix")]
    if "h5ad" in kinds or "mtx" in kinds or "hdf5" in kinds:
        kind, adapter = "scrna", "scrna_py"
    elif any(f["kind"] == "beta_matrix" for f in files) or "idat" in kinds:
        kind, adapter = "methylation", "methylation_r (planned) / write adapter"
    elif matrices:
        kind, adapter = "bulk_rna", "bulk_rna_py"
    else:
        kind, adapter = "unknown", None

    # sample-key hint: which sample-sheet column matches the matrix headers
    sample_key = None
    if a.samples and a.samples.exists() and matrices:
        sheet = pd.read_csv(a.samples, dtype=str).fillna("")
        headers = set()
        for m in matrices:
            text = open_text(Path(m["path"]), 200_000)
            first = next((ln for ln in text.splitlines() if not ln.startswith(("#", "!"))), "")
            headers |= set(first.split("\t" if "\t" in first else ","))
        best = None
        for col in sheet.columns:
            hit = sheet[col].isin(headers).sum()
            if hit and (best is None or hit > best[1]):
                best = (col, int(hit))
        if best:
            sample_key = {"column": best[0], "matched": best[1], "of": int(len(sheet))}

    matrix_mb = sum(f["bytes"] for f in files if f["kind"] in ("count_matrix", "expression_matrix", "beta_matrix", "h5ad", "mtx", "hdf5")) / 1e6
    meta_mb = sum(f["bytes"] for f in files if f["kind"] not in ("count_matrix", "expression_matrix", "beta_matrix", "h5ad", "mtx", "hdf5", "raw_reads", "archive")) / 1e6
    # ponytail: parquet is roughly comparable to gzipped text; refine with real package sizes after the preview build
    est_pkg_mb = matrix_mb + meta_mb
    tier = "S" if est_pkg_mb < 200 else "M" if est_pkg_mb < 5000 and meta_mb < 200 else "L"

    inv = {
        "kind": kind, "adapter": adapter, "sample_key_hint": sample_key,
        "matrices": [f["path"] for f in matrices], "h5ad": [f["path"] for f in files if f["kind"] == "h5ad"],
        "de_tables": [f["path"] for f in files if f["kind"] == "de_table"],
        "sample_tables": [f["path"] for f in files if f["kind"] == "sample_table"],
        "series_matrices": [f["path"] for f in files if f["kind"] == "geo_series_matrix"],
        "papers": [f["path"] for f in files if f["kind"] == "paper_pdf"],
        "unknown": [f["path"] for f in files if f["kind"] in ("unknown", "table", "excel")],
        "sizes": {"matrix_mb": round(matrix_mb, 1), "meta_mb": round(meta_mb, 1), "estimated_package_mb": round(est_pkg_mb, 1)},
        "tier_suggestion": {"tier": tier, "rule": "S < 200 MB; M < 5 GB with meta < 200 MB; else L. XL only when writes/accounts are required."},
        "files": files,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(inv, indent=2) + "\n")
    print(json.dumps({k: inv[k] for k in ("kind", "adapter", "sample_key_hint", "matrices", "h5ad", "de_tables", "sizes", "tier_suggestion")}, indent=2))
    if kind == "unknown":
        sys.exit(2)


if __name__ == "__main__":
    main()
