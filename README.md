# Data2Agent

Turn a paper's omics data into a queryable, citable database portal. Runs as an Agent Skill inside Claude Code / Codex; this repo holds the skill, its deterministic scripts, portal templates and (later) the Go `portal` binary.

Design docs: `doc/architecture.md` (layers, data contract, deployment tiers), `doc/phase1_plan.md` (what phase 1 builds).

## Use it as an Agent Skill (Claude Code / Codex)

```bash
# Claude Code
mkdir -p ~/.claude/skills/data2agent && cp -R skills/data2agent/. ~/.claude/skills/data2agent/
# Codex
mkdir -p ~/.agents/skills/data2agent && cp -R skills/data2agent/. ~/.agents/skills/data2agent/
```

Then, in a session: `/data2agent Build a portal for GSE60450 (paper doi:10.1038/ncb3117) in ./GSE60450-project` (Codex: `$data2agent …`).
The skill runs Ingest → Assess (preview + report) → **your decision: static or hosted** → Curate (labels, ontology terms, paper text) → Build → Verify (fresh agent, acceptance cases from raw data) → Deliver (zip + USAGE). See `skills/data2agent/SKILL.md`.

Prerequisites on the machine: Python 3.11+ with this repo's deps (`uv sync`), and the `portal` binary for MCP verification / hosted builds (`cd portal && go build -o portal ./cmd/portal`, needs gcc).

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

## Bulk RNA-seq example (GSE60450, GEO counts + series matrix)

```bash
mkdir -p data/raw/GSE60450 && cd data/raw/GSE60450
curl -sfLO https://ftp.ncbi.nlm.nih.gov/geo/series/GSE60nnn/GSE60450/suppl/GSE60450_Lactation-GenewiseCounts.txt.gz
curl -sfLO https://ftp.ncbi.nlm.nih.gov/geo/series/GSE60nnn/GSE60450/matrix/GSE60450_series_matrix.txt.gz
curl -sfLO https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/Mus_musculus.gene_info.gz
cd -

# sample sheet from the series matrix (one row per GSM; characteristics become columns)
.venv/bin/python skills/data2agent/scripts/geo_series_matrix.py data/raw/GSE60450/GSE60450_series_matrix.txt.gz \
  -o data/raw/GSE60450/samples.csv --series-json data/raw/GSE60450/series.json

# optional: one DESeq2 contrast when the authors shipped no DE table (labelled "recomputed" in the portal)
.venv/bin/python skills/data2agent/adapters/bulk_rna_py/deseq2_contrast.py --counts data/raw/GSE60450/GSE60450_Lactation-GenewiseCounts.txt.gz \
  --samples data/raw/GSE60450/samples.csv --sample-key description_2 --feature-cols Length \
  --design immunophenotype --a "basal cell population" --b "luminal cell population" -o data/raw/GSE60450/de_basal_vs_luminal.csv

.venv/bin/python skills/data2agent/adapters/bulk_rna_py/run.py out/GSE60450 \
  --counts data/raw/GSE60450/GSE60450_Lactation-GenewiseCounts.txt.gz --samples data/raw/GSE60450/samples.csv \
  --sample-key description_2 --feature-cols Length --gene-info data/raw/GSE60450/Mus_musculus.gene_info.gz \
  --id GSE60450 --accession GSE60450 --title "Luminal and basal mammary cell transcriptomes (GSE60450)" \
  --group immunophenotype --label "immunophenotype=Cell population" --organism "Mus musculus" --taxon NCBITaxon:10090 \
  --de "data/raw/GSE60450/de_basal_vs_luminal.csv:basal_vs_luminal:Basal vs luminal (DESeq2, recomputed)"
.venv/bin/python skills/data2agent/scripts/validate_package.py out/GSE60450
.venv/bin/python skills/data2agent/scripts/build_portal.py out/GSE60450
```

The portal layer is identical for both examples; only the adapter differs.

## Hosted target (self-host with the Go `portal` binary)

```bash
cd portal && go build -o portal ./cmd/portal && cd ..      # needs gcc (go-duckdb is CGO); ~70 MB static binary
.venv/bin/python skills/data2agent/scripts/build_portal.py out/pbmc3k --target hosted   # pages talk to /api/* instead of DuckDB-WASM
./portal/portal serve out/pbmc3k --addr :8080                                           # site + api + parquet
# or, inside the package: docker compose up -d   (Dockerfile + compose.yaml are copied in by --target hosted)
```

Endpoints follow `skills/data2agent/templates/assets/api-contract.json`; the browser-side `api.static.js` and the Go server implement the same functions, so every page works unchanged on either target.

## MCP for AI agents

```bash
claude mcp add pbmc3k -- ./portal/portal mcp out/pbmc3k      # or Codex / Gemini CLI equivalents; stdio transport
# tools: describe_tables, sql (read-only DuckDB), search_features, get_obs, feature_summary
.venv/bin/python skills/data2agent/scripts/verify_mcp_server.py --server "./portal/portal mcp out/pbmc3k" \
  --cases skills/data2agent/references/examples/mcp-cases.pbmc3k.json       # real stdio handshake + acceptance cases
```

## Layout

```
skills/data2agent/
  templates/manifest.schema.json   # the data contract
  adapters/scrna_py/run.py         # AnnData -> contract (reference adapter; others may be R, Julia, ...)
  adapters/bulk_rna_py/run.py      # count matrix + sample sheet (+ DE tables) -> contract
  adapters/bulk_rna_py/deseq2_contrast.py  # optional pydeseq2 helper
  scripts/fetch_geo.py             # GEO series matrix + supplementary files -> raw/, work/sources.json
  scripts/geo_series_matrix.py     # GEO series matrix -> sample sheet CSV
  scripts/probe.py                 # sniff raw files -> work/inventory.json (kind, adapter, tier suggestion)
  scripts/apply_curation.py        # apply work/curation.json: labels, roles, ontology term columns (OLS4-checked), dataset text
  scripts/verify_mcp_server.py     # stdio MCP verifier (no deps); example cases in references/examples/
  scripts/contract.py              # finalize (hashes) + validate
  scripts/validate_package.py
  scripts/build_portal.py          # manifest -> 8 static pages + assets
  SKILL.md, references/, agents/   # the Agent Skill: stage prompts, curation/assessment/acceptance rules, checklist
  templates/site/*.html.j2         # pages
  templates/assets/                # site.css, app.js, charts.js, api.static.js (DuckDB-WASM), api-contract.json
portal/                            # Go: `portal serve` (static + /api/*), `portal mcp` (stdio), Dockerfile, compose.yaml, goreleaser
doc/                               # design documents
```
