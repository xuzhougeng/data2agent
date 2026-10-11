#!/usr/bin/env python
"""Validate a Data2Agent package against the data contract. Exit 0 only when valid.

usage: validate_package.py <package_dir> [--finalize] [--report out.json]
  --finalize  recompute manifest.files hashes first (adapters in other languages call this after writing parquet)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("package", type=Path)
ap.add_argument("--finalize", action="store_true")
ap.add_argument("--report", type=Path)
a = ap.parse_args()

if a.finalize:
    contract.finalize(a.package, contract.load(a.package))
result = contract.validate(a.package)
text = json.dumps(result, indent=2, ensure_ascii=False)
print(text)
if a.report:
    a.report.write_text(text + "\n")
sys.exit(0 if result["ok"] else 1)
