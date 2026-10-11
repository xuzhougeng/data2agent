#!/usr/bin/env python
"""Download the DuckDB-WASM parquet extension so static portals do not depend on extensions.duckdb.org at runtime.

usage: vendor_duckdb_ext.py [--duckdb v1.1.1] [--out templates/vendor/duckdb-ext]
Layout produced (what `SET custom_extension_repository` expects): <out>/<version>/<platform>/parquet.duckdb_extension.wasm
Run once when the network allows; build_portal.py copies the directory into every static package that has it.
"""
import argparse
import sys
import urllib.request
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--duckdb", default="v1.1.1", help="DuckDB version bundled in the pinned @duckdb/duckdb-wasm (1.29.0 -> v1.1.1)")
ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "templates" / "vendor" / "duckdb-ext")
a = ap.parse_args()
ok = True
for platform in ("wasm_eh", "wasm_mvp"):
    url = f"https://extensions.duckdb.org/{a.duckdb}/{platform}/parquet.duckdb_extension.wasm"
    dest = a.out / a.duckdb / platform / "parquet.duckdb_extension.wasm"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
            f.write(r.read())
        print(f"ok  {dest} ({dest.stat().st_size // 1024} KB)")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"FAIL {url}: {e}", file=sys.stderr)
sys.exit(0 if ok else 1)
