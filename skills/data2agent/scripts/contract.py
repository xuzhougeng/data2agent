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
    return sorted(set(out))


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

    # matrices
    for m in manifest.get("matrices", []):
        checks += 1
        src = parquet_source(pkg, m)
        cols = [r[0] for r in q(f"describe select * from {src}")]
        for c in ("obs_id", "feature_id", "value"):
            if c not in cols:
                err(f"matrix {m['name']}: missing column {c}")
        if errors:
            continue
        bad_obs, bad_feat = q(f"""
            select
              (select count(*) from (select distinct obs_id from {src}) x where obs_id not in (select {obs['id']} from {obs_src})),
              (select count(*) from (select distinct feature_id from {src}) x where feature_id not in (select {feats['id']} from {feat_src}))
        """)[0]
        if bad_obs:
            err(f"matrix {m['name']}: {bad_obs} obs_id values not in obs table")
        if bad_feat:
            err(f"matrix {m['name']}: {bad_feat} feature_id values not in features table")
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
        if r.get("feature_col") and r["feature_col"] in cols:
            bad = q(f"select count(*) from read_parquet('{pkg / r['path']}') where {r['feature_col']} not in (select {feats['id']} from {feat_src})")[0][0]
            if bad:
                err(f"result {r['name']}: {bad} rows whose {r['feature_col']} is not in features")
        if r.get("rows") is not None:
            n = q(f"select count(*) from read_parquet('{pkg / r['path']}')")[0][0]
            if n != r["rows"]:
                err(f"result {r['name']}: rows {n} != declared {r['rows']}")

    # stats
    checks += 1
    if manifest["stats"]["n_obs"] != obs["rows"]:
        err(f"stats.n_obs {manifest['stats']['n_obs']} != obs rows {obs['rows']}")
    if manifest["stats"]["n_features"] != feats["rows"]:
        err(f"stats.n_features {manifest['stats']['n_features']} != features rows {feats['rows']}")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "checks": checks}


if __name__ == "__main__":
    print(json.dumps(validate(Path(sys.argv[1])), indent=2))
