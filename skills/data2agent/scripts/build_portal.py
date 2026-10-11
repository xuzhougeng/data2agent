#!/usr/bin/env python
"""Render the portal (HTML + assets) into a contract package directory.

usage: build_portal.py <package_dir> [--target static|hosted] [--data-base-url data/] [--api-base-url /api]
                                     [--preview-note "..."]

Reads manifest.json, derives page list from what the package contains, computes small summaries
(facet counts) with DuckDB, and renders Jinja templates. Omics-agnostic: never opens h5ad etc.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent
TPL = HERE.parent / "templates"
sys.path.insert(0, str(HERE))
import contract  # noqa: E402

PAGES = [  # (file, nav label, condition key)
    ("index.html", "Home", None),
    ("browse.html", "{obs}", None),
    ("embedding.html", "Map", "embeddings"),
    ("feature.html", "{features}", None),
    ("results.html", "Results", "results"),
    ("download.html", "Download", None),
    ("api.html", "API", None),
    ("help.html", "Help", None),
]


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def facet_summaries(pkg: Path, manifest: dict, max_values=40) -> dict:
    """{column: [{value, n}, ...]} for every obs facet column (top max_values)."""
    obs = manifest["tables"]["obs"]
    con = duckdb.connect()
    out = {}
    for c in obs["columns"]:
        if c["role"] != "facet":
            continue
        rows = con.execute(
            f"select cast(\"{c['name']}\" as varchar) v, count(*) n from read_parquet('{pkg / obs['path']}') group by 1 order by n desc, v limit {max_values}"
        ).fetchall()
        out[c["name"]] = [{"value": v, "n": n} for v, n in rows]
    return out


def example_features(pkg: Path, manifest: dict, n=6) -> list[str]:
    """A few features worth showing as examples: top-scoring result hits, else the first searchable ids."""
    con = duckdb.connect()
    feats = manifest["tables"]["features"]
    for r in manifest.get("results", []):
        if r.get("feature_col") and (r.get("score_col") or r.get("p_col")):
            order = f"{r['score_col']} desc" if r.get("score_col") else f"{r['p_col']} asc"
            rows = con.execute(f"select distinct {r['feature_col']} from read_parquet('{pkg / r['path']}') order by {order} limit {n * 3}").fetchall()
            out = []
            for (f,) in rows:
                if f not in out:
                    out.append(f)
                if len(out) >= n:
                    break
            if out:
                return out
    sym = next((c["name"] for c in feats["columns"] if c.get("search") and c["name"] != feats["id"]), feats["id"])
    return [r[0] for r in con.execute(f"select {sym} from read_parquet('{pkg / feats['path']}') limit {n}").fetchall()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package", type=Path)
    ap.add_argument("--target", choices=["static", "hosted"], default="static")
    ap.add_argument("--data-base-url", default="data/")
    ap.add_argument("--api-base-url", default="/api")
    ap.add_argument("--preview-note", default=None, help="Banner text for preview builds")
    a = ap.parse_args()

    pkg = a.package
    manifest = contract.load(pkg)
    manifest.setdefault("deploy", {})
    manifest["deploy"].update({"data_base_url": a.data_base_url, "api_base_url": a.api_base_url, "target": a.target})

    obs, feats = manifest["tables"]["obs"], manifest["tables"]["features"]
    pages = []
    for file, label, cond in PAGES:
        if cond and not manifest.get(cond):
            continue
        pages.append({"file": file, "label": label.format(obs=obs["label"], features=feats["label"])})

    primary = next((c for c in obs["columns"] if c.get("primary_group")), None)
    examples = example_features(pkg, manifest)
    h = hashlib.sha256()
    for name in sorted(p.name for p in (TPL / "assets").iterdir()):
        h.update((TPL / "assets" / name).read_bytes())
    portal = {
        "asset_v": h.hexdigest()[:10],
        "example_feature": examples[0] if examples else None,
        "example_features": examples,
        "manifest": manifest,
        "facets": facet_summaries(pkg, manifest),
        "primary_group": primary["name"] if primary else None,
        "pages": pages,
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "preview": a.preview_note,
    }

    env = Environment(loader=FileSystemLoader(str(TPL / "site")), autoescape=select_autoescape(["html"]))
    env.filters["human_bytes"] = human_bytes
    env.filters["tojson_safe"] = lambda v: json.dumps(v, ensure_ascii=False).replace("</", "<\\/")
    ctx = {"m": manifest, "portal": portal, "pages": pages, "obs": obs, "feats": feats, "primary": primary, "human_bytes": human_bytes}
    for p in pages:
        ctx["page"] = p
        (pkg / p["file"]).write_text(env.get_template(p["file"] + ".j2").render(**ctx))

    assets = pkg / "assets"
    assets.mkdir(exist_ok=True)
    for name in ("site.css", "app.js", "charts.js", "api-contract.json"):
        shutil.copy(TPL / "assets" / name, assets / name)
    shutil.copy(TPL / "assets" / ("api.static.js" if a.target == "static" else "api.http.js"), assets / "api.js")
    (pkg / "portal.json").write_text(json.dumps(portal, ensure_ascii=False, indent=1))

    usage = env.get_template("USAGE.md.j2").render(**ctx) if (TPL / "site" / "USAGE.md.j2").exists() else None
    if usage:
        (pkg / "USAGE.md").write_text(usage)
    print(json.dumps({"package": str(pkg), "target": a.target, "pages": [p["file"] for p in pages]}, indent=2))


if __name__ == "__main__":
    main()
