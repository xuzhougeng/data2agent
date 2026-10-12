#!/usr/bin/env python
"""Verify the interpreter running this script has every dependency the skill needs and that they actually work.
Exit 0 and print JSON on success; exit 1 with the first failure otherwise. Run with the venv python, never the system one."""
import json
import sys
import argparse
import importlib
import importlib.metadata

ap = argparse.ArgumentParser()
ap.add_argument('--profile', choices=['dataset', 'project'], default='dataset')
a = ap.parse_args()
report = {"python": sys.version.split()[0], "executable": sys.executable, "ok": False}
try:
    packages = ['pyarrow', 'duckdb', 'jinja2', 'jsonschema']
    if a.profile == 'dataset':
        packages += ['numpy', 'pandas', 'scipy', 'anndata', 'scanpy', 'pydeseq2', 'openpyxl']
    for package in packages:
        importlib.import_module(package)
        report[package] = importlib.metadata.version(package)
    if a.profile == 'dataset':
        importlib.import_module('pandas').DataFrame({'a': [1, 2]}).describe()
    importlib.import_module('duckdb').sql('select 1').fetchall()
    report.update({'profile': a.profile, 'ok': True})
except Exception as e:  # noqa: BLE001
    report["error"] = f"{type(e).__name__}: {e}"
print(json.dumps(report, indent=2))
sys.exit(0 if report["ok"] else 1)
