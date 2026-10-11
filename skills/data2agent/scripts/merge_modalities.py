#!/usr/bin/env python
"""Merge several single-modality contract packages over the same samples into one multi-omics package.

usage: merge_modalities.py out_pkg --primary pkg_rna --add proteins=pkg_prot [--add metabolites=pkg_met ...]
                           [--id ID] [--title "..."] [--short-title ...] [--kind multi]

Rules (the portal reads only the merged manifest):
- obs: every package must cover the same obs_id set. The primary obs table is kept; annotation columns that only a
  secondary package has are joined in.
- the secondary package's `features` table becomes `tables.<name>`; its matrices / embeddings / results / aggregates
  are prefixed `<name>_` and point at that table; its files move under data/<name>/.
- nothing is recomputed. Cross-modality links are declared on columns with `ref` (adapter flag --ref) and checked by
  validate_package.py.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract  # noqa: E402


def obs_ids(pkg: Path, m: dict) -> set[str]:
    t = m["tables"]["obs"]
    return {r[0] for r in duckdb.connect().execute(f"select cast({t['id']} as varchar) from read_parquet('{pkg / t['path']}')").fetchall()}


def copy_file(src_pkg: Path, rel: str, out: Path, new_rel: str):
    dst = out / new_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src_pkg / rel, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--primary", required=True, type=Path)
    ap.add_argument("--add", action="append", default=[], help="name=package_dir (name becomes the feature table, e.g. proteins)")
    ap.add_argument("--id")
    ap.add_argument("--title")
    ap.add_argument("--short-title")
    ap.add_argument("--kind", default="multi")
    a = ap.parse_args()
    if not a.add:
        sys.exit("nothing to merge: pass at least one --add name=pkg")

    out = a.out
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty")
    prim = contract.load(a.primary)
    m = copy.deepcopy(prim)
    for rel in contract.data_paths(prim):
        copy_file(a.primary, rel, out, rel)
    for x in m.get("matrices", []):
        x.setdefault("kind", prim["kind"])
    ids = obs_ids(a.primary, prim)
    obs_df = pq.read_table(a.primary / prim["tables"]["obs"]["path"]).to_pandas()
    obs_id = prim["tables"]["obs"]["id"]
    methods = [f"## {prim['tables']['features']['label']} ({prim['kind']})\n\n{prim.get('methods', '')}".strip()]
    report = {"primary": {"package": str(a.primary), "kind": prim["kind"], "features": prim["tables"]["features"]["rows"]}, "added": []}

    for spec in a.add:
        name, src = spec.split("=", 1)
        src = Path(src)
        if name in m["tables"] or not name.isidentifier():
            sys.exit(f"bad modality name {name!r}: must be an identifier not already in tables {list(m['tables'])}")
        s = contract.load(src)
        sids = obs_ids(src, s)
        if sids != ids:
            only_p, only_s = sorted(ids - sids)[:5], sorted(sids - ids)[:5]
            sys.exit(f"{name}: obs ids differ from primary ({len(ids - sids)} only in primary e.g. {only_p}; {len(sids - ids)} only in {name} e.g. {only_s}). "
                     "Align the sample sheets (same obs_id values) and rerun the adapters.")
        rename = {}  # old table name -> new
        for tname, t in s["tables"].items():
            if tname == "obs":
                continue
            rename[tname] = name if tname == "features" else f"{name}_{tname}"
        relpath = lambda rel: f"data/{name}/{rel[5:] if rel.startswith('data/') else rel}"  # noqa: E731
        for rel in contract.data_paths(s):
            if rel != s["tables"]["obs"]["path"]:
                copy_file(src, rel, out, relpath(rel))

        # obs: join in columns the primary lacks
        s_obs = pq.read_table(src / s["tables"]["obs"]["path"]).to_pandas()
        s_obs[s["tables"]["obs"]["id"]] = s_obs[s["tables"]["obs"]["id"]].astype(str)
        extra = [c for c in s_obs.columns if c != s["tables"]["obs"]["id"] and c not in obs_df.columns]
        if extra:
            obs_df[obs_id] = obs_df[obs_id].astype(str)
            obs_df = obs_df.merge(s_obs[[s["tables"]["obs"]["id"]] + extra].rename(columns={s["tables"]["obs"]["id"]: obs_id}), on=obs_id, how="left")
            declared = {c["name"]: c for c in s["tables"]["obs"]["columns"]}
            for c in extra:
                if c in declared:
                    col = dict(declared[c])
                    col.pop("primary_group", None)
                    col["source"] = f"{name}: {col.get('source', c)}"
                    m["tables"]["obs"]["columns"].append(col)

        for tname, t in s["tables"].items():
            if tname == "obs":
                continue
            t = copy.deepcopy(t)
            t["path"] = relpath(t["path"])
            m["tables"][rename[tname]] = t
        for x in s.get("matrices", []):
            x = copy.deepcopy(x)
            x["name"] = f"{name}_{x['name']}"
            x["label"] = f"{x.get('label') or x['name']} · {s['tables']['features']['label']}"
            x["features"] = rename.get(x.get("features", "features"), name)
            x["obs"] = "obs"
            x.setdefault("kind", s["kind"])
            x["path"] = relpath(x["path"])
            for sh in x.get("shards", []):
                sh["path"] = relpath(sh["path"])
            m.setdefault("matrices", []).append(x)
        for e in s.get("embeddings", []):
            e = copy.deepcopy(e)
            e["name"], e["label"], e["path"], e["obs"] = f"{name}_{e['name']}", f"{e.get('label') or e['name']} ({s['tables']['features']['label']})", relpath(e["path"]), "obs"
            m.setdefault("embeddings", []).append(e)
        for r in s.get("results", []):
            r = copy.deepcopy(r)
            r["name"], r["path"] = f"{name}_{r['name']}", relpath(r["path"])
            r["features"] = rename.get(r.get("features", "features"), name)
            r["label"] = f"{r['label']} · {s['tables']['features']['label']}"
            m.setdefault("results", []).append(r)
        for g in s.get("aggregates", []):
            g = copy.deepcopy(g)
            g["name"], g["path"] = f"{name}_{g['name']}", relpath(g["path"])
            if g.get("matrix"):
                g["matrix"] = f"{name}_{g['matrix']}"
            m.setdefault("aggregates", []).append(g)
        m.setdefault("assets", []).extend(s.get("assets", []))
        for fig in s.get("figures", []):
            fig = copy.deepcopy(fig)
            for p_ in fig["panels"]:
                p_["path"] = relpath(p_["path"])
                if p_.get("features"):
                    p_["features"] = rename.get(p_["features"], name)
            m.setdefault("figures", []).append(fig)
        m["stats"][f"n_{name}"] = s["tables"]["features"]["rows"]
        methods.append(f"## {s['tables']['features']['label']} ({s['kind']})\n\n{s.get('methods', '')}".strip())
        report["added"].append({"name": name, "package": str(src), "kind": s["kind"], "features": s["tables"]["features"]["rows"], "obs_columns_added": extra})

    obs_cols = [c["name"] for c in m["tables"]["obs"]["columns"]]
    obs_df = obs_df[[c for c in obs_df.columns if c in obs_cols]]
    pq.write_table(pa.Table.from_pandas(obs_df, preserve_index=False), out / m["tables"]["obs"]["path"], compression="zstd")

    m["kind"] = a.kind
    if a.id:
        m["id"] = a.id
    if a.title:
        m["title"] = a.title
    if a.short_title:
        m["short_title"] = a.short_title
    m["methods"] = "\n\n".join(methods)
    m.setdefault("curation", {})["merged_from"] = report
    contract.finalize(out, m)
    print(json.dumps({"package": str(out), "kind": m["kind"], "modalities": [x["name"] for x in contract.modalities(m)], **report}, indent=2))


if __name__ == "__main__":
    main()
