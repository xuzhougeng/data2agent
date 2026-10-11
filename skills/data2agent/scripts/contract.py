"""Shared helpers for the Data2Agent data contract (manifest.json + parquet tables).

Used by adapters (to finalize a package) and by validate_package.py (to check one).
Pure Python + pyarrow + duckdb; no omics knowledge lives here.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import duckdb

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "templates" / "manifest.schema.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def data_paths(manifest: dict) -> list[str]:
    """Every data file path the manifest references (shards expanded)."""
    out: list[str] = []
    for t in manifest.get("tables", {}).values():
        out.append(t["path"])
    for m in manifest.get("matrices", []):
        if m.get("shards"):
            out.extend(s["path"] for s in m["shards"])
        else:
            out.append(m["path"])
    for key in ("embeddings", "results", "aggregates"):
        out.extend(x["path"] for x in manifest.get(key, []))
    for fig in manifest.get("figures", []):
        out.extend(p["path"] for p in fig["panels"])
    return sorted(set(out))


def feature_tables(manifest: dict) -> list[str]:
    """Modalities = feature tables, primary first: 'features' plus every table a matrix is over."""
    out = ["features"]
    for m in manifest.get("matrices", []):
        if m.get("features", "features") not in out:
            out.append(m["features"])
    return out


def modalities(manifest: dict) -> list[dict]:
    """One entry per feature table: its matrices (first = display), aggregate, results, kind, label."""
    out = []
    for name in feature_tables(manifest):
        t = manifest["tables"][name]
        mats = [m for m in manifest.get("matrices", []) if m.get("features", "features") == name]
        agg = next((g for g in manifest.get("aggregates", []) if g.get("matrix") and mats and g["matrix"] == mats[0]["name"]), None)
        res = [r["name"] for r in manifest.get("results", []) if r.get("features", "features") == name]
        kind = (mats[0].get("kind") if mats else None) or manifest["kind"]
        out.append({"name": name, "label": t["label"], "label_singular": t.get("label_singular") or t["label"], "kind": kind, "rows": t["rows"],
                    "matrices": [m["name"] for m in mats], "display_matrix": mats[0]["name"] if mats else None,
                    "value_label": (mats[0]["value"].get("label") or mats[0]["value"]["kind"]) if mats else "value",
                    "aggregate": agg["name"] if agg else None, "results": res})
    return out


def finalize(pkg: Path, manifest: dict) -> dict:
    """Fill manifest['files'] with sha256/bytes for every referenced data file and write manifest.json."""
    files = {}
    for rel in data_paths(manifest):
        p = pkg / rel
        if not p.exists():
            raise FileNotFoundError(f"manifest references missing file: {rel}")
        files[rel] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    manifest["files"] = files
    (pkg / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def load(pkg: Path) -> dict:
    return json.loads((pkg / "manifest.json").read_text())


def parquet_source(pkg: Path, m: dict) -> str:
    """SQL expression reading a matrix (single file or shards) for duckdb."""
    if m.get("shards"):
        return "read_parquet([" + ",".join(f"'{pkg / s['path']}'" for s in m["shards"]) + "])"
    return f"read_parquet('{pkg / m['path']}')"


def validate(pkg: Path) -> dict:
    """Return {'ok': bool, 'errors': [...], 'warnings': [...], 'checks': n}."""
    import jsonschema

    errors: list[str] = []
    warnings: list[str] = []
    checks = 0

    def err(msg):
        errors.append(msg)

    manifest = load(pkg)
    schema = json.loads(SCHEMA_PATH.read_text())
    for e in sorted(jsonschema.Draft202012Validator(schema).iter_errors(manifest), key=str):
        err(f"schema: {'/'.join(str(p) for p in e.absolute_path)}: {e.message}")
    checks += 1
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "checks": checks}

    # files + hashes
    for rel in data_paths(manifest):
        checks += 1
        p = pkg / rel
        if not p.exists():
            err(f"missing file {rel}")
            continue
        rec = manifest["files"].get(rel)
        if rec is None:
            err(f"file not recorded in manifest.files: {rel}")
        elif rec["sha256"] != sha256_file(p) or rec["bytes"] != p.stat().st_size:
            err(f"hash/size mismatch for {rel} (package modified after finalize)")
    for rel in manifest["files"]:
        if not (pkg / rel).exists():
            err(f"manifest.files lists nonexistent {rel}")

    con = duckdb.connect()

    def q(sql):
        return con.execute(sql).fetchall()

    def cols_of(path):
        return [r[0] for r in q(f"describe select * from read_parquet('{pkg / path}')")]

    def q_id(name):
        return '"' + str(name).replace('"', '""') + '"'

    def table_src(name):
        t = manifest["tables"][name]
        return t["id"], f"read_parquet('{pkg / t['path']}')"

    # tables
    for name, t in manifest["tables"].items():
        if not (pkg / t["path"]).exists():
            continue
        checks += 1
        actual_cols = cols_of(t["path"])
        if t["id"] not in actual_cols:
            err(f"tables.{name}: id column {t['id']} not in parquet")
        declared = [c["name"] for c in t["columns"]]
        for c in declared:
            if c not in actual_cols:
                err(f"tables.{name}: declared column {c} not in parquet")
        for c in actual_cols:
            if c not in declared:
                warnings.append(f"tables.{name}: parquet column {c} not declared (will be hidden)")
        n, nid, nnull = q(f"select count(*), count(distinct {t['id']}), count(*) filter (where {t['id']} is null) from read_parquet('{pkg / t['path']}')")[0]
        if n != t["rows"]:
            err(f"tables.{name}: rows {n} != declared {t['rows']}")
        if nid != n or nnull:
            err(f"tables.{name}: id column {t['id']} not unique/non-null ({nid} distinct, {nnull} null of {n})")
        pg = [c["name"] for c in t["columns"] if c.get("primary_group")]
        if name == "obs" and len(pg) > 1:
            err(f"tables.obs: more than one primary_group column: {pg}")
        if name == "obs" and not pg:
            warnings.append("tables.obs: no primary_group column; group charts disabled")

    obs = manifest["tables"]["obs"]
    feats = manifest["tables"]["features"]
    obs_src = f"read_parquet('{pkg / obs['path']}')"
    feat_src = f"read_parquet('{pkg / feats['path']}')"

    # column refs (cross-table links): target must exist; warn when few values resolve
    for name, t in manifest["tables"].items():
        for c in t["columns"]:
            if not c.get("ref"):
                continue
            checks += 1
            rt, rc = c["ref"].split(".", 1)
            if rt not in manifest["tables"] or rc not in [x["name"] for x in manifest["tables"][rt]["columns"]]:
                err(f"tables.{name}.{c['name']}: ref {c['ref']} does not name a declared table.column")
                continue
            hit, tot = q(f"""select count(*) filter (where cast(a.{q_id(c['name'])} as varchar) in (select cast({q_id(rc)} as varchar) from read_parquet('{pkg / manifest['tables'][rt]['path']}'))), count(*)
                             from read_parquet('{pkg / t['path']}') a where a.{q_id(c['name'])} is not null""")[0]
            if tot and hit == 0:
                warnings.append(f"tables.{name}.{c['name']}: no value resolves through ref {c['ref']}")

    # matrices
    for m in manifest.get("matrices", []):
        checks += 1
        src = parquet_source(pkg, m)
        cols = [r[0] for r in q(f"describe select * from {src}")]
        for c in ("obs_id", "feature_id", "value"):
            if c not in cols:
                err(f"matrix {m['name']}: missing column {c}")
        for key in ("obs", "features"):
            if m.get(key, key) not in manifest["tables"]:
                err(f"matrix {m['name']}: {key}={m[key]} is not a declared table")
        if errors:
            continue
        o_id, o_src = table_src(m.get("obs", "obs"))
        f_id, f_src = table_src(m.get("features", "features"))
        bad_obs, bad_feat = q(f"""
            select
              (select count(*) from (select distinct obs_id from {src}) x where obs_id not in (select {o_id} from {o_src})),
              (select count(*) from (select distinct feature_id from {src}) x where feature_id not in (select {f_id} from {f_src}))
        """)[0]
        if bad_obs:
            err(f"matrix {m['name']}: {bad_obs} obs_id values not in obs table")
        if bad_feat:
            err(f"matrix {m['name']}: {bad_feat} feature_id values not in {m.get('features', 'features')} table")
        if m.get("nnz") is not None:
            n = q(f"select count(*) from {src}")[0][0]
            if n != m["nnz"]:
                err(f"matrix {m['name']}: rows {n} != declared nnz {m['nnz']}")
        # sorted by feature_id (within each file)
        for path in ([s["path"] for s in m["shards"]] if m.get("shards") else [m["path"]]):
            unsorted = q(f"select count(*) from (select feature_id, lag(feature_id) over () prev from read_parquet('{pkg / path}')) where prev > feature_id")[0][0]
            if unsorted:
                err(f"matrix {m['name']}: {path} not sorted by feature_id ({unsorted} inversions)")
        if m.get("shards"):
            for s in m["shards"]:
                lo, hi = q(f"select min(feature_id), max(feature_id) from read_parquet('{pkg / s['path']}')")[0]
                if lo != s["feature_min"] or hi != s["feature_max"]:
                    err(f"matrix {m['name']}: shard {s['path']} range [{lo},{hi}] != declared [{s['feature_min']},{s['feature_max']}]")

    # embeddings
    for e in manifest.get("embeddings", []):
        checks += 1
        cols = cols_of(e["path"])
        for c in ("obs_id", "x", "y"):
            if c not in cols:
                err(f"embedding {e['name']}: missing column {c}")
        if "obs_id" in cols:
            bad = q(f"select count(*) from read_parquet('{pkg / e['path']}') where obs_id not in (select {obs['id']} from {obs_src})")[0][0]
            if bad:
                err(f"embedding {e['name']}: {bad} obs_id not in obs")

    # results
    for r in manifest.get("results", []):
        checks += 1
        cols = cols_of(r["path"])
        for key in ("feature_col", "obs_col", "group_col", "effect_col", "p_col", "score_col"):
            if r.get(key) and r[key] not in cols:
                err(f"result {r['name']}: {key}={r[key]} not in parquet")
        for c in r["columns"]:
            if c["name"] not in cols:
                err(f"result {r['name']}: declared column {c['name']} not in parquet")
        if r.get("features", "features") not in manifest["tables"]:
            err(f"result {r['name']}: features={r['features']} is not a declared table")
        elif r.get("feature_col") and r["feature_col"] in cols:
            f_id, f_src = table_src(r.get("features", "features"))
            bad = q(f"select count(*) from read_parquet('{pkg / r['path']}') where {r['feature_col']} not in (select {f_id} from {f_src})")[0][0]
            if bad:
                err(f"result {r['name']}: {bad} rows whose {r['feature_col']} is not in {r.get('features', 'features')}")
        if r.get("rows") is not None:
            n = q(f"select count(*) from read_parquet('{pkg / r['path']}')")[0][0]
            if n != r["rows"]:
                err(f"result {r['name']}: rows {n} != declared {r['rows']}")

    # aggregates
    names = {m["name"] for m in manifest.get("matrices", [])}
    for g in manifest.get("aggregates", []):
        if g.get("matrix") and g["matrix"] not in names:
            err(f"aggregate {g['name']}: matrix {g['matrix']} not declared")

    # figures (source data panels)
    seen = set()
    for fig in manifest.get("figures", []):
        for p_ in fig["panels"]:
            checks += 1
            if p_["id"] in seen:
                err(f"figure {fig['id']}: duplicate panel id {p_['id']}")
            seen.add(p_["id"])
            if not (pkg / p_["path"]).exists():
                continue
            cols = cols_of(p_["path"])
            for c in p_["columns"]:
                if c["name"] not in cols:
                    err(f"panel {p_['id']}: declared column {c['name']} not in parquet")
            ch = p_.get("chart") or {}
            for key in ("x", "y", "group"):
                if ch.get(key) and ch[key] not in cols:
                    err(f"panel {p_['id']}: chart.{key}={ch[key]} not in parquet")
            n = q(f"select count(*) from read_parquet('{pkg / p_['path']}')")[0][0]
            if n != p_["rows"]:
                err(f"panel {p_['id']}: rows {n} != declared {p_['rows']}")
            if p_.get("features", "features") not in manifest["tables"]:
                err(f"panel {p_['id']}: features={p_['features']} is not a declared table")

    # stats
    checks += 1
    if manifest["stats"]["n_obs"] != obs["rows"]:
        err(f"stats.n_obs {manifest['stats']['n_obs']} != obs rows {obs['rows']}")
    if manifest["stats"]["n_features"] != feats["rows"]:
        err(f"stats.n_features {manifest['stats']['n_features']} != features rows {feats['rows']}")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "checks": checks}


if __name__ == "__main__":
    print(json.dumps(validate(Path(sys.argv[1])), indent=2))
