#!/usr/bin/env python
"""Parse a GEO series_matrix.txt(.gz) into a sample sheet CSV (one row per GSM).

usage: geo_series_matrix.py GSExxxxx_series_matrix.txt.gz [-o samples.csv] [--series-json series.json]

Columns: obs_id (GSM), title, source, organism, platform, plus one column per
`key: value` characteristic (key normalised to snake_case) and description_1..n.
Also writes series-level metadata (title, summary, design, pubmed, contact) as JSON when asked.
Purely mechanical; curation (ontology mapping, relabelling) happens later.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path


def read_lines(path: Path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n")


def unquote(v: str) -> str:
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == '"' and v[-1] == '"' else v


def snake(s: str) -> str:
    s = re.sub(r"[^0-9A-Za-z]+", "_", s.strip().lower()).strip("_")
    return s or "field"


def parse(path: Path):
    series, samples = defaultdict(list), defaultdict(list)
    for line in read_lines(path):
        if line.startswith("!Series_"):
            key, _, rest = line[8:].partition("\t")
            series[key].append(unquote(rest))
        elif line.startswith("!Sample_"):
            key, _, rest = line[8:].partition("\t")
            samples[key].append([unquote(v) for v in rest.split("\t")])
    return series, samples


def build_sheet(samples: dict) -> list[OrderedDict]:
    gsm = samples["geo_accession"][0]
    n = len(gsm)
    rows = [OrderedDict(obs_id=g) for g in gsm]
    simple = {"title": "title", "source_name_ch1": "source", "organism_ch1": "organism", "platform_id": "platform",
              "molecule_ch1": "molecule", "library_strategy": "library_strategy", "instrument_model": "instrument"}
    for key, col in simple.items():
        if key in samples:
            for i in range(n):
                rows[i][col] = samples[key][0][i]
    # characteristics: each line is "key: value" per sample; keys may differ per line
    for line in samples.get("characteristics_ch1", []):
        for i in range(n):
            v = line[i] if i < len(line) else ""
            if not v:
                continue
            k, sep, val = v.partition(":")
            if sep:
                rows[i][snake(k)] = val.strip()
            else:
                rows[i].setdefault("characteristics", v)
    for j, line in enumerate(samples.get("description", []), 1):
        for i in range(n):
            v = line[i] if i < len(line) else ""
            if v:
                rows[i][f"description_{j}"] = v
    for line in samples.get("supplementary_file_1", []):
        for i in range(n):
            if i < len(line) and line[i] and line[i] != "NONE":
                rows[i]["supplementary_file"] = line[i]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("matrix", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--series-json", type=Path)
    a = ap.parse_args()
    series, samples = parse(a.matrix)
    rows = build_sheet(samples)
    cols = list(OrderedDict.fromkeys(k for r in rows for k in r))
    out = open(a.out, "w", newline="") if a.out else sys.stdout
    w = csv.DictWriter(out, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)
    if a.out:
        out.close()
    if a.series_json:
        meta = {k: (v[0] if len(v) == 1 else v) for k, v in series.items()}
        a.series_json.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(json.dumps({"samples": len(rows), "columns": cols}, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
