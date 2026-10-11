#!/usr/bin/env python
"""Apply work/curation.json to a contract package: dataset text, column labels/roles, ontology term columns,
result-table labels. Re-finalises hashes. Optionally verifies every ontology id against OLS4.

usage: apply_curation.py pkg/ work/curation.json [--check-ontology] [--cache work/ontology-cache.json] [--report reports/curation.json]
Exit 1 when the curation references unknown columns/tables or (with --check-ontology) unknown term ids.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract  # noqa: E402

DATASET_KEYS = ("title", "short_title", "description", "kind", "organism", "license", "access", "source", "contact", "methods", "changelog", "doi", "version")


def ols_lookup(term_id: str, cache: dict) -> dict:
    """{'found': bool, 'label': str|None}. Cached. Uses the OLS4 search endpoint restricted to obo_id (exact)."""
    if term_id in cache and cache[term_id].get("found"):
        return cache[term_id]
    prefix = term_id.split(":")[0].lower()
    url = "https://www.ebi.ac.uk/ols4/api/search?" + urllib.parse.urlencode({"q": term_id, "exact": "true", "queryFields": "obo_id", "rows": 10})
    out = {"found": False, "label": None}
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "data2agent/0.1"}), timeout=30) as r:
                data = json.loads(r.read().decode())
            docs = (data.get("response") or {}).get("docs") or []
            hit = next((d for d in docs if d.get("obo_id") == term_id and d.get("ontology_name") == prefix), None) \
                or next((d for d in docs if d.get("obo_id") == term_id), None)
            if hit:
                out = {"found": True, "label": hit.get("label"), "iri": hit.get("iri"), "ontology": hit.get("ontology_name")}
            out.pop("error", None)
            break
        except Exception as e:  # noqa: BLE001
            out["error"] = str(e)
            time.sleep(1.5 * (attempt + 1))
    cache[term_id] = out
    return out


def apply_columns(table_def: dict, spec: dict, errors: list[str], where: str) -> list[str]:
    """Update label/role/primary_group/ontology on declared columns. Returns relabelled column names."""
    by_name = {c["name"]: c for c in table_def["columns"]}
    touched = []
    for name, cs in (spec.get("columns") or {}).items():
        if name not in by_name:
            errors.append(f"{where}: column {name!r} not in package")
            continue
        c = by_name[name]
        for k in ("label", "role", "description", "unit"):
            if k in cs:
                c[k] = cs[k]
        if cs.get("primary_group"):
            for other in table_def["columns"]:
                other.pop("primary_group", None)
            c["primary_group"] = True
            c["role"] = "facet"
        touched.append(name)
    return touched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package", type=Path)
    ap.add_argument("curation", type=Path)
    ap.add_argument("--check-ontology", action="store_true")
    ap.add_argument("--cache", type=Path, default=Path("work/ontology-cache.json"))
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()

    pkg = a.package
    m = contract.load(pkg)
    cur = json.loads(a.curation.read_text())
    errors: list[str] = []
    report = {"applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "dataset_fields": [], "columns": {}, "terms": {}, "unknown_ids": [], "errors": errors}

    # ---- dataset text
    for k in DATASET_KEYS:
        if k in (cur.get("dataset") or {}):
            m[k] = cur["dataset"][k]
            report["dataset_fields"].append(k)

    # ---- results
    by_res = {r["name"]: r for r in m.get("results", [])}
    for name, rs in (cur.get("results") or {}).items():
        if name not in by_res:
            errors.append(f"results: {name!r} not in package")
            continue
        for k in ("label", "description"):
            if k in rs:
                by_res[name][k] = rs[k]
        if "columns" in rs:
            apply_columns(by_res[name], rs, errors, f"results.{name}")

    # ---- obs / features columns + ontology terms
    cache = json.loads(a.cache.read_text()) if a.cache.exists() else {}
    for tname in ("obs", "features"):
        spec = cur.get(tname) or {}
        if not spec:
            continue
        tdef = m["tables"][tname]
        report["columns"][tname] = apply_columns(tdef, spec, errors, tname)
        term_specs = {col: cs for col, cs in (spec.get("columns") or {}).items() if cs.get("terms")}
        if not term_specs:
            continue
        path = pkg / tdef["path"]
        table = pq.read_table(path)
        existing = {c["name"] for c in tdef["columns"]}
        for col, cs in term_specs.items():
            if col not in table.column_names:
                errors.append(f"{tname}: column {col!r} not in parquet")
                continue
            terms = cs["terms"]
            prefix = cs.get("ontology") or next(iter(terms.values()))["id"].split(":")[0]
            values = [None if v is None else str(v) for v in table.column(col).to_pylist()]
            ids = [terms.get(v, {}).get("id") if v is not None else None for v in values]
            labels = [terms.get(v, {}).get("label") if v is not None else None for v in values]
            id_col, label_col = f"{col}_ontology_term_id", f"{col}_ontology_label"
            for cname, data in ((id_col, ids), (label_col, labels)):
                arr = pa.array(data, type=pa.string())
                if cname in table.column_names:
                    table = table.set_column(table.column_names.index(cname), cname, arr)
                else:
                    table = table.append_column(cname, arr)
            base_label = cs.get("label") or next(c["label"] for c in tdef["columns"] if c["name"] == col)
            defs = [
                {"name": id_col, "label": f"{base_label} ({prefix})", "dtype": "string", "role": "ontology", "ontology": prefix, "label_column": label_col, "source": "curation"},
                {"name": label_col, "label": f"{base_label} ontology label", "dtype": "string", "role": "hidden", "source": "curation"},
            ]
            tdef["columns"] = [c for c in tdef["columns"] if c["name"] not in (id_col, label_col)] + defs
            existing |= {id_col, label_col}
            mapped = sum(1 for i in ids if i)
            distinct = {v for v in values if v is not None}
            report["terms"][f"{tname}.{col}"] = {"ontology": prefix, "values_total": len(distinct), "values_mapped": len([v for v in distinct if v in terms]),
                                                 "rows_total": len(values), "rows_mapped": mapped, "coverage": round(mapped / max(1, len(values)), 4)}
            if a.check_ontology:
                for v, t in terms.items():
                    res = ols_lookup(t["id"], cache)
                    if not res.get("found"):
                        report["unknown_ids"].append({"column": col, "value": v, "id": t["id"], "error": res.get("error")})
                    elif res.get("label") and t.get("label") and res["label"].lower() != t["label"].lower():
                        report.setdefault("label_mismatches", []).append({"id": t["id"], "given": t["label"], "ols": res["label"]})
        pq.write_table(table, path, compression="zstd", use_dictionary=True)
        tdef["rows"] = table.num_rows

    if a.check_ontology:
        a.cache.parent.mkdir(parents=True, exist_ok=True)
        a.cache.write_text(json.dumps(cache, indent=1))

    m.setdefault("curation", {})
    m["curation"].update({"applied_at": report["applied_at"], "curation_sha256": contract.sha256_file(a.curation),
                          "term_coverage": {k: v["coverage"] for k, v in report["terms"].items()}, "notes": cur.get("notes", [])})
    contract.finalize(pkg, m)

    ok = not errors and not report["unknown_ids"]
    report["ok"] = ok
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(text + "\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
