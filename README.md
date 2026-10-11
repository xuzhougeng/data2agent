# Data2Agent

Turn a paper's omics data into a queryable, citable database portal. Runs as an Agent Skill inside Claude Code / Codex; this repo holds the skill, its deterministic scripts, portal templates and (later) the Go `portal` binary.

Design docs: `doc/architecture.md` (layers, data contract, deployment tiers), `doc/phase1_plan.md` (what phase 1 builds).

## Try the pbmc3k template (static target)

```bash
uv sync
curl -sfL -o data/raw/pbmc3k.h5ad https://raw.githubusercontent.com/chanzuckerberg/cellxgene/main/example-dataset/pbmc3k.h5ad

# 1. adapter: h5ad -> contract package (parquet + manifest.json)
.venv/bin/python skills/data2agent/adapters/scrna_py/run.py data/raw/pbmc3k.h5ad out/pbmc3k \
  --id pbmc3k --title "PBMC 3k: peripheral blood mononuclear cells (10x Genomics)" --short-title "PBMC 3k" \
  --group louvain --label "louvain=Cell type" --organism "Homo sapiens" --taxon NCBITaxon:9606

# 2. validate the contract (exit 0 only when consistent)
.venv/bin/python skills/data2agent/scripts/validate_package.py out/pbmc3k

# 3. render the portal (omics-agnostic; reads only manifest.json + parquet)
.venv/bin/python skills/data2agent/scripts/build_portal.py out/pbmc3k --target static

# 4. open it
cd out/pbmc3k && python3 -m http.server 8080   # http://localhost:8080/
```

## Layout

```
skills/data2agent/
  templates/manifest.schema.json   # the data contract
  adapters/scrna_py/run.py         # AnnData -> contract (reference adapter; others may be R, Julia, ...)
  scripts/contract.py              # finalize (hashes) + validate
  scripts/validate_package.py
  scripts/build_portal.py          # manifest -> 8 static pages + assets
  templates/site/*.html.j2         # pages
  templates/assets/                # site.css, app.js, charts.js, api.static.js (DuckDB-WASM), api-contract.json
doc/                               # design documents
```
