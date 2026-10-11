#!/usr/bin/env python
"""End-to-end check of multi-omics + source data: synthetic RNA and proteomics packages over the same samples are
merged, a Source Data workbook is attached, the package validates, and the static portal renders every page.

run: .venv/bin/python skills/data2agent/scripts/test_multiomics.py   (no network, no Go needed)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
PY = sys.executable


def run(*args):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(f"{args[0]} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


class MultiOmics(unittest.TestCase):
    def test_merge_and_build(self):
        rng = np.random.default_rng(0)
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            samples = [f"S{i}" for i in range(1, 7)]
            pd.DataFrame({"obs_id": samples, "condition": ["ctrl"] * 3 + ["treated"] * 3, "batch": [1, 2, 3, 1, 2, 3]}).to_csv(d / "samples.csv", index=False)
            genes = [f"G{i}" for i in range(1, 41)]
            counts = pd.DataFrame(rng.poisson(50, (40, 6)), columns=samples)
            counts.insert(0, "gene_id", genes)
            counts.to_csv(d / "counts.tsv", sep="\t", index=False)
            pd.DataFrame({"id": genes, "symbol": [f"Sym{i}" for i in range(1, 41)]}).to_csv(d / "symbols.tsv", sep="\t", index=False)
            prot = pd.DataFrame(rng.lognormal(10, 1, (15, 6)), columns=samples)
            prot.insert(0, "protein", [f"P{i}" for i in range(1, 16)])
            prot.insert(1, "gene_symbol", [f"Sym{i}" for i in range(1, 16)])
            prot.iloc[0, 2] = np.nan  # a missing intensity
            prot.to_csv(d / "prot.tsv", sep="\t", index=False)
            with pd.ExcelWriter(d / "Source Data Fig. 2.xlsx") as xw:
                pd.DataFrame([["Figure 2a: body weight (g), n=4 per group"], [None], ["WT", "KO"], [21.3, 19.1], [22.0, 18.4], [20.8, 19.9], [21.1, 18.0]]).to_excel(xw, sheet_name="Fig 2a", header=False, index=False)
                pd.DataFrame({"gene": ["Sym1", "Sym2", "Sym3"], "log2FC": [1.2, -0.8, 2.1], "padj": [0.01, 0.2, 0.001]}).to_excel(xw, sheet_name="Fig 2b", index=False)

            run(SKILL / "adapters/bulk_rna_py/run.py", d / "rna", "--counts", d / "counts.tsv", "--samples", d / "samples.csv", "--symbols", d / "symbols.tsv",
                "--id", "rna", "--title", "RNA", "--group", "condition", "--feature-cols", "")
            run(SKILL / "adapters/bulk_rna_py/run.py", d / "prot", "--counts", d / "prot.tsv", "--samples", d / "samples.csv", "--feature-cols", "gene_symbol",
                "--id", "prot", "--title", "Proteins", "--group", "condition", "--kind", "proteomics", "--transform", "log2", "--feature-label", "Proteins",
                "--ref", "gene_symbol=features.symbol")
            pm = json.loads((d / "prot/manifest.json").read_text())
            self.assertEqual(pm["tables"]["features"]["label_singular"], "Protein")
            self.assertEqual(pm["matrices"][0]["kind"], "proteomics")
            self.assertEqual(next(c for c in pm["tables"]["features"]["columns"] if c["name"] == "gene_symbol")["ref"], "features.symbol")

            out = run(HERE / "merge_modalities.py", d / "multi", "--primary", d / "rna", "--add", f"proteins={d / 'prot'}", "--id", "demo", "--title", "Demo multi-omics")
            self.assertIn('"proteins"', out)
            run(SKILL / "adapters/source_data_py/run.py", d / "multi", "--xlsx", d / "Source Data Fig. 2.xlsx")
            m = json.loads((d / "multi/manifest.json").read_text())
            self.assertEqual(m["kind"], "multi")
            self.assertIn("proteins", m["tables"])
            self.assertEqual({x["features"] for x in m["matrices"]}, {"features", "proteins"})
            self.assertEqual(m["figures"][0]["id"], "fig2")
            panels = {p["id"]: p for p in m["figures"][0]["panels"]}
            self.assertEqual(panels["fig2_2a"]["chart"]["type"], "columns")
            self.assertEqual(panels["fig2_2a"]["rows"], 4)
            self.assertIn("body weight", panels["fig2_2a"]["caption"])
            self.assertEqual(panels["fig2_2b"]["chart"], {"type": "group", "x": "gene", "y": "log2FC"})

            v = json.loads(run(HERE / "validate_package.py", d / "multi"))
            self.assertTrue(v["ok"], v)
            self.assertEqual(v["warnings"], [])

            run(HERE / "build_portal.py", d / "multi", "--target", "static")
            portal = json.loads((d / "multi/portal.json").read_text())
            self.assertEqual([x["name"] for x in portal["modalities"]], ["features", "proteins"])
            self.assertEqual(portal["modalities"][1]["display_matrix"], "proteins_log2")
            self.assertEqual(portal["modalities"][1]["aggregate"], "proteins_feature_group")
            self.assertTrue((d / "multi/figures.html").exists())
            self.assertIn('id="feat-mod"', (d / "multi/feature.html").read_text())
            self.assertIn("fig_fig2_2a", (d / "multi/api.html").read_text())

            # a mismatching obs set is refused
            pd.DataFrame({"obs_id": samples[:5], "condition": ["a"] * 5}).to_csv(d / "s5.csv", index=False)
            run(SKILL / "adapters/bulk_rna_py/run.py", d / "rna5", "--counts", d / "counts.tsv", "--samples", d / "samples.csv", "--id", "x", "--title", "x", "--feature-cols", "")
            prot5 = prot[["protein", "gene_symbol"] + samples[:5]]
            prot5.to_csv(d / "prot5.tsv", sep="\t", index=False)
            run(SKILL / "adapters/bulk_rna_py/run.py", d / "prot5", "--counts", d / "prot5.tsv", "--samples", d / "s5.csv", "--id", "p", "--title", "p", "--feature-cols", "gene_symbol", "--transform", "log2")
            r = subprocess.run([PY, HERE / "merge_modalities.py", d / "multi2", "--primary", d / "rna5", "--add", f"proteins={d / 'prot5'}"], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("obs ids differ", r.stderr)


if __name__ == "__main__":
    unittest.main()
