#!/usr/bin/env python
"""Verify the interpreter running this script has every dependency the skill needs and that they actually work.
Exit 0 and print JSON on success; exit 1 with the first failure otherwise. Run with the venv python, never the system one."""
import json
import sys

report = {"python": sys.version.split()[0], "executable": sys.executable, "ok": False}
try:
    import numpy, pandas, scipy, pyarrow, duckdb, jinja2, jsonschema, anndata, scanpy  # noqa: F401,E401
    import pydeseq2  # noqa: F401
    # the failure mode seen in the wild: numpy/pandas ABI mismatch raises at import of pandas._libs
    pandas.DataFrame({"a": [1, 2]}).describe()
    duckdb.sql("select 1").fetchall()
    report.update({"numpy": numpy.__version__, "pandas": pandas.__version__, "anndata": anndata.__version__,
                   "scanpy": scanpy.__version__, "duckdb": duckdb.__version__, "pyarrow": pyarrow.__version__, "ok": True})
except Exception as e:  # noqa: BLE001
    report["error"] = f"{type(e).__name__}: {e}"
print(json.dumps(report, indent=2))
sys.exit(0 if report["ok"] else 1)
