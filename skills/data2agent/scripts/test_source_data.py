#!/usr/bin/env python
"""Recipe engine check for source_data_py: a synthetic workbook with the layouts journals actually ship
(replicates across columns with labels filled down, merged group headers, side-by-side field tables, a stacked
statistics sheet) goes through probe -> recipe -> apply, and the tidy panels carry the right rows and links.

run: .venv/bin/python skills/data2agent/scripts/test_source_data.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ADAPTER = HERE.parent / "adapters/source_data_py/run.py"
PY = sys.executable


def run(*args, ok=True):
    r = subprocess.run([PY, "-I", *map(str, args)], capture_output=True, text=True)
    if ok and r.returncode:
        raise AssertionError(f"{args[0]} failed:\n{r.stdout}\n{r.stderr}")
    return r


class SourceData(unittest.TestCase):
    def test_recipe_engine(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            raw = d / "raw"
            raw.mkdir()
            with pd.ExcelWriter(raw / "Source Data Fig. 1.xlsx") as xw:
                # wide_rows: repeat filled down only on its first row, replicates across columns, ragged
                pd.DataFrame([["Lesion length (cm)"], ["Repeat 1-Shanghai_2021", "WT", 1.0, 2.0, 3.0], [None, "mut", 5.0, 6.0, None],
                              ["Repeat 2-Hainan_2022", "WT", 1.5, 2.5, 3.5], [None, "mut", 5.5, 6.5, 7.5]]).to_excel(xw, sheet_name="Fig.1a", header=False, index=False)
                # grouped_columns: merged group header over 2 replicate columns, time as the first column
                pd.DataFrame([["Bacterial populations"], ["Time", "WT", None, "mut", None], [0, 3.1, 3.2, 3.0, 3.3], [7, 7.1, 7.3, 9.5, 9.6]]).to_excel(xw, sheet_name="Fig.1b", header=False, index=False)
                # long, two tables side by side; the right one has no title row
                rows = [["seed setting rate", None, None, None, None, "yield", None, None, None, None]]
                rows.append(["Block", "Genotype", "Plants", "Site_2021", "Site_2022", "Block", "Genotype", "Plants", "Site_2021", "Site_2022"])
                rows.append([1, "WT", 1, 0.8, 0.7, 1, "WT", 1, 14, 13])
                rows.append([None, None, 2, 0.81, 0.72, None, None, 2, 15, 13.5])
                rows.append([None, "mut", 1, 0.5, 0.4, None, "mut", 1, 9, 8])
                pd.DataFrame(rows).to_excel(xw, sheet_name="Fig.1c", header=False, index=False)
            with pd.ExcelWriter(raw / "statistics.xlsx") as xw:
                pd.DataFrame([["Fig.1a"], ["Lesion length"], ["contrast", None, None, "estimate", "SE", "p.value"], ["mut", "-", "WT", 4.0, 0.3, "<0.0001"],
                              ["Fig.1c"], ["seed setting rate"], ["contrast", None, None, "estimate", "SE", "p.value"], ["mut", "-", "WT", -0.3, 0.02, "<0.0001"]]).to_excel(xw, sheet_name="Fig.1", header=False, index=False)

            r = run(ADAPTER, "probe", raw, "--out", d / "draft.json")
            draft = json.loads((d / "draft.json").read_text())
            by_sheet = {p["sheet"]: p for f in draft["figures"] for p in f["panels"]}
            self.assertEqual(by_sheet["Fig.1a"]["layout"], "wide_rows")
            self.assertEqual(by_sheet["Fig.1b"]["layout"], "grouped_columns")
            self.assertEqual(draft["figures"][0]["id"], "fig1")

            spec = {"source_dir": str(raw), "layouts": {
                "lesion": {"layout": "wide_rows", "labels": ["repeat", "genotype"], "ffill": ["repeat"], "value": "lesion_length", "unit": "cm",
                           "split": {"repeat": {"pattern": r"Repeat (\d+)-(\w+)_(\d{4})", "into": ["repeat_no", "site", "year"]}},
                           "chart": {"type": "strip", "x": "genotype", "y": "lesion_length", "facet": "repeat"}}},
                "figures": [
                    {"id": "fig1", "label": "Figure 1", "caption": "Synthetic.", "panels": [
                        {"id": "fig1_1a", "label": "Fig. 1a", "file": "Source Data Fig. 1.xlsx", "sheet": "Fig.1a", "like": "lesion", "skip_rows": 1},
                        {"id": "fig1_1b", "label": "Fig. 1b", "file": "Source Data Fig. 1.xlsx", "sheet": "Fig.1b", "layout": "grouped_columns", "skip_rows": 1, "index": "day", "group": "genotype", "value": "cfu"},
                        {"id": "fig1_1c_ssr", "label": "Fig. 1c · ssr", "file": "Source Data Fig. 1.xlsx", "sheet": "Fig.1c", "layout": "long", "skip_rows": 1, "cols": [0, 5],
                         "ffill": ["Block", "Genotype"], "rename": {"Block": "block", "Genotype": "genotype", "Plants": "plant"},
                         "melt": {"pattern": r"_\d{4}$", "name": "site_year", "value": "seed_setting_rate"}},
                        {"id": "fig1_1c_yield", "label": "Fig. 1c · yield", "file": "Source Data Fig. 1.xlsx", "sheet": "Fig.1c", "layout": "long", "skip_rows": 1, "cols": [5, 10],
                         "ffill": ["block", "genotype"], "rename": {"Block": "block", "Genotype": "genotype", "Plants": "plant"},
                         "melt": {"pattern": r"_\d{4}$", "name": "site_year", "value": "yield"}},
                    ]},
                    {"id": "stats", "label": "Statistics", "panels": [{"id": "stats_f1", "label": "Fig.1", "file": "statistics.xlsx", "sheet": "Fig.1", "layout": "stacked", "rename": {"col_2": "vs", "col_3": "control"}}]},
                ]}
            (d / "spec.json").write_text(json.dumps(spec))
            run(ADAPTER, "apply", d / "pkg", d / "spec.json", "--init", "--id", "t", "--title", "T")
            m = json.loads((d / "pkg/manifest.json").read_text())
            panels = {p["id"]: p for f in m["figures"] for p in f["panels"]}
            read = lambda pid: pd.read_parquet(d / "pkg" / panels[pid]["path"])  # noqa: E731

            a = read("fig1_1a")
            self.assertEqual(len(a), 11)  # 12 cells minus one blank
            self.assertEqual(sorted(a.columns), sorted(["repeat", "genotype", "replicate", "lesion_length", "repeat_no", "site", "year"]))
            self.assertEqual(set(a["site"]), {"Shanghai", "Hainan"})
            self.assertEqual(a[(a.genotype == "mut") & (a.repeat_no == 2)]["lesion_length"].tolist(), [5.5, 6.5, 7.5])
            self.assertEqual(panels["fig1_1a"]["chart"]["facet"], "repeat")
            self.assertEqual(panels["fig1_1a"]["sheet_caption"] if "sheet_caption" in panels["fig1_1a"] else panels["fig1_1a"]["caption"], "Lesion length (cm)")

            b = read("fig1_1b")
            self.assertEqual(len(b), 8)
            self.assertEqual(b[(b.genotype == "mut") & (b.day == 7)]["cfu"].tolist(), [9.5, 9.6])
            self.assertEqual(panels["fig1_1b"]["chart"]["type"], "line")

            s = read("fig1_1c_ssr")
            self.assertEqual(len(s), 6)
            self.assertEqual(s[(s.genotype == "WT") & (s.plant == 2) & (s.site_year == "Site_2022")]["seed_setting_rate"].item(), 0.72)
            y = read("fig1_1c_yield")
            self.assertEqual(y[(y.genotype == "mut") & (y.site_year == "Site_2021")]["yield"].item(), 9)

            self.assertEqual(panels["fig1_1a"]["related"], ["stats_f1_1a"])
            self.assertEqual(panels["fig1_1c_ssr"]["related"], ["stats_f1_1c"])
            self.assertEqual(panels["fig1_1c_yield"]["related"], ["stats_f1_1c"])
            st = read("stats_f1_1a")
            self.assertEqual(list(st.columns), ["contrast", "vs", "control", "estimate", "SE", "p.value"])
            self.assertEqual(st["p.value"].iloc[0], "<0.0001")

            v = json.loads(run(HERE / "validate_package.py", d / "pkg").stdout)
            self.assertTrue(v["ok"], v)
            run(HERE / "build_portal.py", d / "pkg")
            self.assertTrue((d / "pkg/figures.html").exists())
            self.assertFalse((d / "pkg/browse.html").exists())  # no obs table, no Samples page
            self.assertIn("Figure 1", (d / "pkg/index.html").read_text())

            # a recipe error is reported per panel and fails the run
            spec["figures"][0]["panels"][0]["labels"] = ["a", "b", "c", "d", "e", "f"]
            (d / "spec2.json").write_text(json.dumps(spec))
            r = run(ADAPTER, "apply", d / "pkg2", d / "spec2.json", "--init", "--id", "t", "--title", "T", ok=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("fig1_1a", r.stdout)


if __name__ == "__main__":
    unittest.main()
