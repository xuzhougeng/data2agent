#!/usr/bin/env python
"""scrna_py adapter: AnnData (.h5ad) -> Data2Agent contract package.

usage: run.py input.h5ad out_dir --id pbmc3k --title "..." [--group louvain] [--layer raw|X|<layer>]
                                 [--value-kind lognorm] [--shard-mb 100] [--kind scrna]

Writes out_dir/data/*.parquet + out_dir/manifest.json and finalizes hashes.
Everything scientific comes from anndata/scanpy; this file only moves data into the contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import scipy.sparse as sp

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import contract  # noqa: E402

ROW_GROUP = 50_000  # ponytail: ~a few genes per row group so DuckDB-WASM range-reads one gene cheaply


def infer_columns(df: pd.DataFrame, id_col: str, group: str | None, facet_max=50):
    cols = [{"name": id_col, "label": id_col, "dtype": "string", "role": "id"}]
    for c in df.columns:
        if c == id_col:
            continue
        s = df[c]
        if pd.api.types.is_bool_dtype(s):
            role, dtype = "facet", "bool"
        elif pd.api.types.is_integer_dtype(s):
            role, dtype = ("facet" if s.nunique() <= 20 else "numeric"), "int"
        elif pd.api.types.is_float_dtype(s):
            role, dtype = "numeric", "float"
        else:  # categorical, string, object
            n = s.nunique(dropna=True)
            role, dtype = ("facet" if n <= facet_max else "text"), "string"
        col = {"name": c, "label": c.replace("_", " ").capitalize(), "dtype": dtype, "role": role, "source": c}
        if group and c == group:
            col["primary_group"] = True
            col["role"] = "facet"
        cols.append(col)
    return cols


def to_table(df: pd.DataFrame) -> pa.Table:
    df = df.copy()
    for c in df.columns:
        if isinstance(df[c].dtype, pd.CategoricalDtype):
            df[c] = df[c].astype(str).where(df[c].notna(), None)
    return pa.Table.from_pandas(df, preserve_index=False)


def write(table: pa.Table, path: Path, row_group_size=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd", row_group_size=row_group_size, use_dictionary=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("h5ad", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--short-title", default=None)
    ap.add_argument("--description", default=None)
    ap.add_argument("--label", action="append", default=[], help="col=Label, repeatable; relabel obs/feature columns")
    ap.add_argument("--kind", default="scrna")
    ap.add_argument("--group", help="obs column used as primary group (cell type)")
    ap.add_argument("--layer", default="auto", help="raw | X | <layer name> | auto (raw if present else X)")
    ap.add_argument("--value-kind", default=None, help="counts|lognorm|... (auto: integer -> counts else lognorm)")
    ap.add_argument("--shard-mb", type=int, default=100)
    ap.add_argument("--organism", default=None, help="e.g. 'Homo sapiens'")
    ap.add_argument("--taxon", default=None, help="e.g. NCBITaxon:9606")
    ap.add_argument("--subsample", type=int, default=None, help="keep at most N cells (random, seed 0); for preview builds only")
    a = ap.parse_args()

    adata = ad.read_h5ad(a.h5ad)
    if a.subsample and adata.n_obs > a.subsample:
        rng = np.random.default_rng(0)
        adata = adata[np.sort(rng.choice(adata.n_obs, a.subsample, replace=False))].copy()
    out = a.out
    data = out / "data"
    data.mkdir(parents=True, exist_ok=True)

    # ---- choose matrix
    if a.layer == "auto":
        layer = "raw" if adata.raw is not None else "X"
    else:
        layer = a.layer
    if layer == "raw":
        X, var = adata.raw.X, adata.raw.var.copy()
    elif layer == "X":
        X, var = adata.X, adata.var.copy()
    else:
        X, var = adata.layers[layer], adata.var.copy()
    X = sp.csr_matrix(X) if not sp.issparse(X) else X.tocsr()
    sample = X.data[: min(100_000, X.nnz)]
    value_kind = a.value_kind or ("counts" if np.allclose(sample, np.round(sample)) else "lognorm")

    # ---- obs
    obs = adata.obs.copy()
    obs.insert(0, "obs_id", obs.index.astype(str))
    obs = obs.reset_index(drop=True)
    obs_cols = infer_columns(obs, "obs_id", a.group)
    relabel = dict(kv.split("=", 1) for kv in a.label)
    for c in obs_cols:
        c["label"] = relabel.get(c["name"], "Cell ID" if c["name"] == "obs_id" else c["label"])
    write(to_table(obs), data / "obs.parquet")

    # ---- features
    var.insert(0, "feature_id", var.index.astype(str))
    if "symbol" not in var.columns:
        var.insert(1, "symbol", var.index.astype(str))
    var = var.reset_index(drop=True)
    feat_cols = infer_columns(var, "feature_id", None)
    for c in feat_cols:
        if c["name"] in ("feature_id", "symbol"):
            c["search"] = True
        c["label"] = relabel.get(c["name"], {"symbol": "Gene symbol", "feature_id": "Gene ID", "n_cells": "Cells detected in"}.get(c["name"], c["label"]))
    write(to_table(var), data / "features.parquet")

    # ---- matrix (long, sorted by feature_id)
    coo = X.tocoo()
    fid = var["feature_id"].to_numpy()
    oid = obs["obs_id"].to_numpy()
    mat = pd.DataFrame({"obs_id": oid[coo.row], "feature_id": fid[coo.col], "value": coo.data.astype(np.float32)})
    mat.sort_values(["feature_id", "obs_id"], inplace=True, kind="stable")
    mat_table = pa.Table.from_pandas(mat, preserve_index=False)
    single = data / "matrix.parquet"
    write(mat_table, single, ROW_GROUP)
    matrix_entry = {
        "name": "expression", "label": "Expression", "path": "data/matrix.parquet",
        "obs": "obs", "features": "features", "sparse": True, "nnz": int(len(mat)),
        "value": {"kind": value_kind, "label": {"counts": "Raw counts", "lognorm": "log-normalized expression"}.get(value_kind, value_kind), "dtype": "float32"},
    }
    if single.stat().st_size > a.shard_mb * 1024 * 1024:
        n_shards = int(np.ceil(single.stat().st_size / (a.shard_mb * 1024 * 1024)))
        single.unlink()
        uniq = mat["feature_id"].unique()
        bounds = np.array_split(uniq, n_shards)
        shards = []
        for i, feats in enumerate(bounds):
            part = mat[mat["feature_id"].isin(set(feats))]
            rel = f"data/matrix/part-{i:03d}.parquet"
            write(pa.Table.from_pandas(part, preserve_index=False), out / rel, ROW_GROUP)
            shards.append({"path": rel, "feature_min": str(feats[0]), "feature_max": str(feats[-1]), "rows": int(len(part))})
        matrix_entry["path"] = "data/matrix"
        matrix_entry["shards"] = shards

    # ---- embeddings
    embeddings = []
    for key, label in (("X_umap", "UMAP"), ("X_tsne", "t-SNE"), ("X_pca", "PCA"), ("spatial", "Spatial")):
        if key in adata.obsm:
            arr = np.asarray(adata.obsm[key])[:, :2]
            name = key.replace("X_", "").lower()
            rel = f"data/embeddings/{name}.parquet"
            write(pa.Table.from_pandas(pd.DataFrame({"obs_id": oid, "x": arr[:, 0].astype(np.float32), "y": arr[:, 1].astype(np.float32)}), preserve_index=False), out / rel)
            embeddings.append({"name": name, "label": label, "path": rel, "obs": "obs", "spatial": key == "spatial"})

    # ---- results: rank_genes_groups -> long table
    results = []
    rgg = adata.uns.get("rank_genes_groups")
    if rgg is not None and "names" in rgg:
        groupby = str(rgg["params"]["groupby"]) if "params" in rgg else a.group
        keys = list(rgg["names"].dtype.names)
        labels = keys
        if groupby and groupby in adata.obs and isinstance(adata.obs[groupby].dtype, pd.CategoricalDtype):
            cats = list(adata.obs[groupby].cat.categories.astype(str))
            if all(k.isdigit() for k in keys) and len(cats) == len(keys):
                labels = [cats[int(k)] for k in keys]
        rows = []
        feat_set = set(fid)
        for k, lab in zip(keys, labels):
            names = rgg["names"][k]
            for rank, g in enumerate(names):
                if g is None or (isinstance(g, float) and np.isnan(g)) or str(g) not in feat_set:
                    continue
                row = {"group": lab, "feature_id": str(g), "rank": rank + 1}
                for fld, col in (("scores", "score"), ("logfoldchanges", "log2fc"), ("pvals_adj", "padj"), ("pvals", "pval")):
                    if fld in rgg:
                        row[col] = float(rgg[fld][k][rank])
                rows.append(row)
        if rows:
            df = pd.DataFrame(rows)
            rel = "data/results/markers.parquet"
            write(pa.Table.from_pandas(df, preserve_index=False), out / rel)
            method = str(rgg["params"].get("method", "")) if "params" in rgg else ""
            cols = [
                {"name": "group", "label": "Group", "dtype": "string", "role": "facet"},
                {"name": "feature_id", "label": "Gene", "dtype": "string", "role": "link"},
                {"name": "rank", "label": "Rank", "dtype": "int", "role": "numeric"},
            ] + [{"name": c, "label": {"score": "Score", "log2fc": "log2 fold change", "padj": "Adjusted p", "pval": "p-value"}[c], "dtype": "float", "role": "numeric"} for c in df.columns if c in ("score", "log2fc", "padj", "pval")]
            entry = {"name": "markers", "label": "Marker genes", "description": f"Top genes per {relabel.get(groupby, groupby)} (scanpy rank_genes_groups, {method}, each group vs. rest)", "path": rel,
                     "rows": int(len(df)), "feature_col": "feature_id", "group_col": "group", "columns": cols}
            if "log2fc" in df.columns:
                entry["effect_col"] = "log2fc"
            if "padj" in df.columns:
                entry["p_col"] = "padj"
            if "score" in df.columns:
                entry["score_col"] = "score"
            results.append(entry)

    # ---- aggregate: per feature x primary group mean & fraction expressing
    aggregates = []
    n_groups = None
    if a.group and a.group in obs.columns:
        g = obs[a.group].astype(str).to_numpy()
        groups = pd.unique(g)
        n_groups = len(groups)
        recs = []
        for grp in groups:
            mask = g == grp
            sub = X[mask]
            n = int(mask.sum())
            mean = np.asarray(sub.mean(axis=0)).ravel()
            pct = np.asarray((sub > 0).sum(axis=0)).ravel() / n
            recs.append(pd.DataFrame({"feature_id": fid, "group": grp, "n": n, "mean": mean.astype(np.float32), "pct": pct.astype(np.float32)}))
        agg = pd.concat(recs, ignore_index=True).sort_values(["feature_id", "group"])
        rel = "data/agg/feature_group.parquet"
        write(pa.Table.from_pandas(agg, preserve_index=False), out / rel)
        aggregates.append({"name": "feature_group", "path": rel, "matrix": "expression", "group_col": a.group,
                           "description": f"Per-gene mean {value_kind} and fraction of cells with value>0, by {relabel.get(a.group, a.group)}"})

    stats = {"n_obs": int(obs.shape[0]), "n_features": int(var.shape[0]), "nnz": int(len(mat))}
    if n_groups:
        stats["n_groups"] = int(n_groups)

    manifest = {
        "contract_version": 1,
        "id": a.id,
        "title": a.title,
        "short_title": a.short_title or a.id,
        "description": a.description or "",
        "kind": a.kind,
        "version": "0.1.0",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": {
            "obs": {"path": "data/obs.parquet", "rows": stats["n_obs"], "id": "obs_id", "label": "Cells", "label_singular": "Cell", "columns": obs_cols},
            "features": {"path": "data/features.parquet", "rows": stats["n_features"], "id": "feature_id", "label": "Genes", "label_singular": "Gene", "columns": feat_cols},
        },
        "matrices": [matrix_entry],
        "embeddings": embeddings,
        "results": results,
        "aggregates": aggregates,
        "assets": [],
        "stats": stats,
        "files": {},
        "methods": f"Converted from AnnData `{a.h5ad.name}` (layer: {layer}, {value_kind}) with the scrna_py adapter. Matrix stored as a sparse long table sorted by feature.",
    }
    if a.organism or a.taxon:
        manifest["organism"] = {k: v for k, v in (("label", a.organism), ("taxon", a.taxon)) if v}
    contract.finalize(out, manifest)
    print(json.dumps({"package": str(out), **stats, "layer": layer, "value_kind": value_kind,
                      "embeddings": [e["name"] for e in embeddings], "results": [r["name"] for r in results]}, indent=2))


if __name__ == "__main__":
    main()
