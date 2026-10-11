#!/usr/bin/env python
"""bulk_rna_py adapter: count matrix + sample sheet (+ optional DE tables) -> Data2Agent contract package.

usage: run.py --counts counts.tsv[.gz] --samples samples.csv out_dir --id GSE60450 --title "..."
              [--group immunophenotype] [--sample-key description_2] [--gene-col EntrezGeneID]
              [--feature-cols Length] [--gene-info Mus_musculus.gene_info.gz]
              [--de table.csv[:name:Label]]... [--label col=Label]... [--organism ...] [--taxon ...]

The count matrix is genes x samples (first column = gene id unless --gene-col). Sample columns are matched
to the sample sheet through --sample-key (an obs column whose values equal the count column names; default obs_id).
Writes two matrices: log2 CPM (displayed) and raw counts; a PCA embedding; per-group aggregates; DE result tables.
Everything scientific is standard numpy arithmetic (CPM, log2, SVD); DE tables must be supplied, not invented.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import contract  # noqa: E402

ROW_GROUP = 50_000

DE_COLS = {  # canonical name -> candidate headers (case-insensitive)
    "feature_id": ["feature_id", "gene", "gene_id", "geneid", "entrezgeneid", "entrez", "ensembl", "symbol", "id", "row.names", ""],
    "log2fc": ["log2foldchange", "log2fc", "logfc", "log2_fc", "log2 fold change"],
    "pval": ["pvalue", "pval", "p_value", "p.value", "p"],
    "padj": ["padj", "fdr", "adj.p.val", "qvalue", "q_value", "p.adjust", "adj_p", "padjust"],
    "base_mean": ["basemean", "aveexpr", "logcpm", "mean"],
    "stat": ["stat", "t", "lr", "f"],
    "group": ["group", "contrast", "comparison"],
}


def read_table(path: Path, **kw) -> pd.DataFrame:
    sep = "," if path.name.replace(".gz", "").endswith(".csv") else "\t"
    return pd.read_csv(path, sep=sep, **kw)


def infer_columns(df: pd.DataFrame, id_col: str, relabel: dict, group: str | None, facet_max=50):
    cols = [{"name": id_col, "label": relabel.get(id_col, id_col), "dtype": "string", "role": "id"}]
    for c in df.columns:
        if c == id_col:
            continue
        s = df[c]
        if pd.api.types.is_bool_dtype(s):
            role, dtype = "facet", "bool"
        elif pd.api.types.is_integer_dtype(s):
            role, dtype = ("facet" if s.nunique() <= 20 and len(s) > 40 else "numeric"), "int"
        elif pd.api.types.is_float_dtype(s):
            role, dtype = "numeric", "float"
        else:
            n = s.nunique(dropna=True)
            role = "facet" if 1 < n <= facet_max and n < len(s) else "text"
            if n == 1:
                role = "text"
            if s.astype(str).str.startswith(("http://", "https://", "ftp://")).all():
                role = "link"
            dtype = "string"
        col = {"name": c, "label": relabel.get(c, c.replace("_", " ").capitalize()), "dtype": dtype, "role": role, "source": c}
        if group and c == group:
            col["primary_group"] = True
            col["role"] = "facet"
        cols.append(col)
    return cols


def write(table: pa.Table, path: Path, row_group_size=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd", row_group_size=row_group_size, use_dictionary=True)


def long_matrix(values: np.ndarray, obs_ids: np.ndarray, feat_ids: np.ndarray) -> pd.DataFrame:
    """values: features x samples dense -> long (obs_id, feature_id, value) of non-zeros, sorted by feature then obs."""
    fi, oi = np.nonzero(values)
    df = pd.DataFrame({"obs_id": obs_ids[oi], "feature_id": feat_ids[fi], "value": values[fi, oi].astype(np.float32)})
    df.sort_values(["feature_id", "obs_id"], inplace=True, kind="stable")
    return df.reset_index(drop=True)


def pick(df: pd.DataFrame, candidates: list[str]) -> str | None:
    low = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand in low:
            return low[cand]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--counts", required=True, type=Path)
    ap.add_argument("--samples", required=True, type=Path)
    ap.add_argument("--id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--short-title")
    ap.add_argument("--description", default="")
    ap.add_argument("--kind", default="bulk_rna")
    ap.add_argument("--group", help="obs column used as primary group")
    ap.add_argument("--sample-key", default="obs_id", help="obs column matching count-matrix column names")
    ap.add_argument("--gene-col", help="gene id column in counts (default: first column)")
    ap.add_argument("--feature-cols", default="", help="comma list of non-sample columns in counts to keep as feature annotation (e.g. Length)")
    ap.add_argument("--gene-info", type=Path, help="NCBI gene_info(.gz) to add symbol/name/biotype for Entrez ids")
    ap.add_argument("--symbols", type=Path, help="2+ column table: id, symbol[, name] (header required)")
    ap.add_argument("--de", action="append", default=[], help="DE table path[:name:Label], repeatable")
    ap.add_argument("--label", action="append", default=[], help="col=Label, repeatable")
    ap.add_argument("--organism")
    ap.add_argument("--taxon")
    ap.add_argument("--accession")
    ap.add_argument("--methods", default="")
    ap.add_argument("--hvg", type=int, default=500, help="genes used for PCA (most variable by log2 CPM)")
    a = ap.parse_args()
    relabel = dict(kv.split("=", 1) for kv in a.label)
    out = a.out
    (out / "data").mkdir(parents=True, exist_ok=True)

    # ---- counts
    counts = read_table(a.counts)
    gene_col = a.gene_col or counts.columns[0]
    feature_extra = [c for c in a.feature_cols.split(",") if c]
    sample_cols = [c for c in counts.columns if c != gene_col and c not in feature_extra]
    counts[gene_col] = counts[gene_col].astype(str)
    counts = counts.drop_duplicates(gene_col).set_index(gene_col)
    mat = counts[sample_cols].to_numpy(dtype=np.float64)
    is_int = np.allclose(mat, np.round(mat))

    # ---- samples (obs)
    obs = read_table(a.samples, dtype=str).fillna("")
    if "obs_id" not in obs.columns:
        obs.insert(0, "obs_id", obs.iloc[:, 0])
    key = obs[a.sample_key].astype(str)
    missing = [c for c in sample_cols if c not in set(key)]
    if missing:
        sys.exit(f"count columns not found in samples[{a.sample_key}]: {missing[:5]}{'...' if len(missing) > 5 else ''}")
    obs = obs.set_index(key).loc[sample_cols].reset_index(drop=True)  # align to count column order
    obs_ids = obs["obs_id"].astype(str).to_numpy()
    if a.sample_key != "obs_id":
        obs = obs.rename(columns={a.sample_key: "library"}) if "library" not in obs.columns else obs
    obs = obs.replace({"": None})
    # numeric-looking columns back to numbers
    for c in obs.columns:
        if c == "obs_id":
            continue
        s = pd.to_numeric(obs[c], errors="coerce")
        if s.notna().sum() == obs[c].notna().sum() and obs[c].notna().any():
            obs[c] = s
    obs_cols = infer_columns(obs, "obs_id", {**{"obs_id": "Sample ID"}, **relabel}, a.group)
    for c in obs_cols:  # GEO-derived text columns nobody filters on
        if c["name"] in ("supplementary_file",):
            c["role"] = "link"
        if c["name"].startswith("description_") or c["name"] in ("library", "title"):
            c["role"] = "text"
    write(pa.Table.from_pandas(obs, preserve_index=False), out / "data/obs.parquet")

    # ---- features
    feat_ids = counts.index.to_numpy().astype(str)
    feats = pd.DataFrame({"feature_id": feat_ids})
    for c in feature_extra:
        feats[c] = counts[c].to_numpy()
    if a.gene_info:
        gi = pd.read_csv(a.gene_info, sep="\t", dtype=str, usecols=["GeneID", "Symbol", "description", "type_of_gene"]).rename(
            columns={"GeneID": "feature_id", "Symbol": "symbol", "description": "name", "type_of_gene": "biotype"})
        feats = feats.merge(gi, on="feature_id", how="left")
    elif a.symbols:
        sym = read_table(a.symbols, dtype=str)
        sym.columns = ["feature_id", "symbol"] + list(sym.columns[2:])
        feats = feats.merge(sym.iloc[:, :3], on="feature_id", how="left")
    if "symbol" not in feats.columns:
        feats["symbol"] = feats["feature_id"]
    feats["symbol"] = feats["symbol"].fillna(feats["feature_id"])
    feats["mean_count"] = mat.mean(axis=1).astype(np.float32)
    feats["detected_in"] = (mat > 0).sum(axis=1).astype(np.int32)
    feat_cols = infer_columns(feats, "feature_id", {"feature_id": "Gene ID", "symbol": "Gene symbol", "name": "Name", "biotype": "Biotype",
                                                     "Length": "Length (bp)", "mean_count": "Mean count", "detected_in": "Detected in (samples)", **relabel}, None)
    for c in feat_cols:
        if c["name"] in ("feature_id", "symbol"):
            c["search"] = True
        if c["name"] == "biotype":
            c["role"] = "facet"
        if c["name"] == "name":
            c["role"] = "text"
    write(pa.Table.from_pandas(feats, preserve_index=False), out / "data/features.parquet")

    # ---- matrices: log2 CPM (display) + raw counts
    lib = mat.sum(axis=0)
    cpm = mat / np.where(lib == 0, 1, lib) * 1e6
    logcpm = np.log2(cpm + 1)
    m_log = long_matrix(logcpm, obs_ids, feat_ids)
    write(pa.Table.from_pandas(m_log, preserve_index=False), out / "data/matrix.parquet", ROW_GROUP)
    m_raw = long_matrix(mat, obs_ids, feat_ids)
    write(pa.Table.from_pandas(m_raw, preserve_index=False), out / "data/matrix_counts.parquet", ROW_GROUP)
    matrices = [
        {"name": "logcpm", "label": "Expression (log2 CPM)", "path": "data/matrix.parquet", "obs": "obs", "features": "features", "sparse": True,
         "nnz": int(len(m_log)), "value": {"kind": "lognorm", "label": "log2 CPM", "dtype": "float32"}},
        {"name": "counts", "label": "Raw counts" if is_int else "Raw values", "path": "data/matrix_counts.parquet", "obs": "obs", "features": "features", "sparse": True,
         "nnz": int(len(m_raw)), "value": {"kind": "counts" if is_int else "other", "label": "raw counts" if is_int else "raw values", "dtype": "float32"}},
    ]

    # ---- PCA on top variable genes (log2 CPM, centred)
    embeddings = []
    if mat.shape[1] >= 3:
        var = logcpm.var(axis=1)
        top = np.argsort(var)[::-1][: min(a.hvg, len(var))]
        x = logcpm[top].T  # samples x genes
        x = x - x.mean(axis=0)
        u, s, _ = np.linalg.svd(x, full_matrices=False)
        pcs = u[:, :2] * s[:2]
        explained = (s ** 2 / (s ** 2).sum())[:2] * 100
        rel = "data/embeddings/pca.parquet"
        write(pa.Table.from_pandas(pd.DataFrame({"obs_id": obs_ids, "x": pcs[:, 0].astype(np.float32), "y": pcs[:, 1].astype(np.float32)}), preserve_index=False), out / rel)
        embeddings.append({"name": "pca", "label": f"PCA (PC1 {explained[0]:.0f}%, PC2 {explained[1]:.0f}%)", "path": rel, "obs": "obs"})

    # ---- aggregates by primary group
    aggregates, n_groups = [], None
    if a.group and a.group in obs.columns:
        g = obs[a.group].astype(str).to_numpy()
        groups = pd.unique(g)
        n_groups = len(groups)
        recs = []
        for grp in groups:
            mask = g == grp
            sub = logcpm[:, mask]
            recs.append(pd.DataFrame({"feature_id": feat_ids, "group": grp, "n": int(mask.sum()), "mean": sub.mean(axis=1).astype(np.float32), "pct": (sub > 0).mean(axis=1).astype(np.float32)}))
        agg = pd.concat(recs, ignore_index=True).sort_values(["feature_id", "group"])
        write(pa.Table.from_pandas(agg, preserve_index=False), out / "data/agg/feature_group.parquet")
        aggregates.append({"name": "feature_group", "path": "data/agg/feature_group.parquet", "matrix": "logcpm", "group_col": a.group,
                           "description": f"Per-gene mean log2 CPM and fraction of samples with counts>0, by {relabel.get(a.group, a.group)}"})

    # ---- DE result tables
    results = []
    feat_set = set(feat_ids)
    sym_to_id = dict(zip(feats["symbol"].astype(str), feats["feature_id"]))
    for i, spec in enumerate(a.de):
        parts = spec.split(":")
        path = Path(parts[0])
        name = parts[1] if len(parts) > 1 and parts[1] else re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_") or f"de_{i}"
        label = parts[2] if len(parts) > 2 else path.stem.replace("_", " ")
        de = read_table(path)
        if de.columns[0].startswith("Unnamed") or de.columns[0] == "":
            de = de.rename(columns={de.columns[0]: "feature_id"})
        found = {k: pick(de, v) for k, v in DE_COLS.items()}
        fcol = found["feature_id"] or de.columns[0]
        de = de.rename(columns={fcol: "feature_id"})
        de["feature_id"] = de["feature_id"].astype(str)
        # ids may be symbols; map to feature ids when that helps
        if de["feature_id"].isin(feat_set).mean() < 0.5 and de["feature_id"].map(sym_to_id).notna().mean() > 0.5:
            de["feature_id"] = de["feature_id"].map(sym_to_id).fillna(de["feature_id"])
        de = de[de["feature_id"].isin(feat_set)].copy()
        rename = {found[k]: k for k in ("log2fc", "pval", "padj", "base_mean", "stat", "group") if found[k] and found[k] != k}
        de = de.rename(columns=rename)
        if "group" not in de.columns:
            de.insert(1, "group", label)
        id_to_sym = dict(zip(feats["feature_id"], feats["symbol"].astype(str)))
        if "symbol" in de.columns:
            de = de.drop(columns=["symbol"])
        de.insert(1, "symbol", de["feature_id"].map(id_to_sym))
        cols = [{"name": "feature_id", "label": "Gene ID", "dtype": "string", "role": "link"}, {"name": "symbol", "label": "Gene", "dtype": "string", "role": "text"},
                {"name": "group", "label": "Contrast", "dtype": "string", "role": "facet"}]
        for c in de.columns:
            if c in ("feature_id", "symbol", "group"):
                continue
            dtype = "float" if pd.api.types.is_float_dtype(de[c]) else "int" if pd.api.types.is_integer_dtype(de[c]) else "string"
            cols.append({"name": c, "label": {"log2fc": "log2 fold change", "pval": "p-value", "padj": "Adjusted p", "base_mean": "Base mean", "stat": "Statistic"}.get(c, c),
                         "dtype": dtype, "role": "numeric" if dtype != "string" else "text"})
        rel = f"data/results/{name}.parquet"
        write(pa.Table.from_pandas(de.reset_index(drop=True), preserve_index=False), out / rel)
        entry = {"name": name, "label": label, "path": rel, "rows": int(len(de)), "feature_col": "feature_id", "label_col": "symbol", "group_col": "group", "columns": cols,
                 "description": f"Differential expression table from `{path.name}`"}
        if "log2fc" in de.columns:
            entry["effect_col"] = "log2fc"
        if "padj" in de.columns:
            entry["p_col"] = "padj"
        elif "pval" in de.columns:
            entry["p_col"] = "pval"
        if "stat" in de.columns:
            entry["score_col"] = "stat"
        results.append(entry)

    stats = {"n_obs": int(len(obs)), "n_features": int(len(feats)), "nnz": int(len(m_raw))}
    if n_groups:
        stats["n_groups"] = int(n_groups)
    manifest = {
        "contract_version": 1, "id": a.id, "title": a.title, "short_title": a.short_title or a.id, "description": a.description, "kind": a.kind,
        "version": "0.1.0", "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": {
            "obs": {"path": "data/obs.parquet", "rows": stats["n_obs"], "id": "obs_id", "label": "Samples", "label_singular": "Sample", "columns": obs_cols},
            "features": {"path": "data/features.parquet", "rows": stats["n_features"], "id": "feature_id", "label": "Genes", "label_singular": "Gene", "columns": feat_cols},
        },
        "matrices": matrices, "embeddings": embeddings, "results": results, "aggregates": aggregates, "assets": [],
        "stats": stats, "files": {},
        "methods": a.methods or f"Gene-level counts from `{a.counts.name}` ({len(feats)} genes x {len(obs)} samples). log2 CPM = log2(counts / library size x 1e6 + 1). PCA on the {a.hvg} most variable genes (log2 CPM, centred). Converted with the bulk_rna_py adapter.",
    }
    if a.organism or a.taxon:
        manifest["organism"] = {k: v for k, v in (("label", a.organism), ("taxon", a.taxon)) if v}
    if a.accession:
        manifest["source"] = {"accession": a.accession, "repository": "GEO", "urls": [f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={a.accession}"]}
    contract.finalize(out, manifest)
    print(json.dumps({"package": str(out), **stats, "value_kind": "counts" if is_int else "other", "results": [r["name"] for r in results]}, indent=2))


if __name__ == "__main__":
    main()
