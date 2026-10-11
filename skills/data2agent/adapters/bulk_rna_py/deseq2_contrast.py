#!/usr/bin/env python
"""Optional helper: compute one DESeq2 contrast with pydeseq2 when the authors supplied no DE table.

usage: deseq2_contrast.py --counts counts.tsv.gz --samples samples.csv --sample-key description_2 \
         --design immunophenotype --a "basal cell population" --b "luminal cell population" -o de_basal_vs_luminal.csv

The output is a plain CSV (feature_id, baseMean, log2FoldChange, lfcSE, stat, pvalue, padj) that run.py ingests via --de.
Provenance: label the result as recomputed in the portal; it is not the authors' analysis.
"""
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats


def read_table(path: Path, **kw):
    sep = "," if path.name.replace(".gz", "").endswith(".csv") else "\t"
    return pd.read_csv(path, sep=sep, **kw)


ap = argparse.ArgumentParser()
ap.add_argument("--counts", required=True, type=Path)
ap.add_argument("--samples", required=True, type=Path)
ap.add_argument("--sample-key", default="obs_id")
ap.add_argument("--gene-col")
ap.add_argument("--feature-cols", default="")
ap.add_argument("--design", required=True, help="obs column for the contrast")
ap.add_argument("--a", required=True, help="numerator level")
ap.add_argument("--b", required=True, help="denominator (reference) level")
ap.add_argument("--min-count", type=int, default=10, help="drop genes with total counts below this")
ap.add_argument("-o", "--out", required=True, type=Path)
args = ap.parse_args()

counts = read_table(args.counts)
gene_col = args.gene_col or counts.columns[0]
extra = [c for c in args.feature_cols.split(",") if c]
counts[gene_col] = counts[gene_col].astype(str)
counts = counts.drop_duplicates(gene_col).set_index(gene_col).drop(columns=extra)
samples = read_table(args.samples, dtype=str).set_index(args.sample_key).loc[counts.columns]
keep = samples[args.design].isin([args.a, args.b])
counts, samples = counts.loc[:, keep.values], samples[keep]
counts = counts[counts.sum(axis=1) >= args.min_count]

# pydeseq2 wants samples x genes, integer counts, and clean factor levels
X = counts.T.round().astype(int)
meta = pd.DataFrame({"cond": samples[args.design].map(lambda v: re.sub(r"[^A-Za-z0-9]+", "_", v).strip("_")).values}, index=X.index)
la, lb = (re.sub(r"[^A-Za-z0-9]+", "_", v).strip("_") for v in (args.a, args.b))
dds = DeseqDataSet(counts=X, metadata=meta, design="~cond", quiet=True)
dds.deseq2()
st = DeseqStats(dds, contrast=["cond", la, lb], quiet=True)
st.summary()
res = st.results_df.reset_index().rename(columns={"index": "feature_id"})
res.insert(1, "group", f"{args.a} vs {args.b}")
res.to_csv(args.out, index=False)
print(f"{len(res)} genes, {(res['padj'] < 0.05).sum()} with padj<0.05 -> {args.out}")
