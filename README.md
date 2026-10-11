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

## Layout

```
skills/data2agent/
  templates/manifest.schema.json   # the data contract
  adapters/scrna_py/run.py         # AnnData -> contract (reference adapter; others may be R, Julia, ...)
  adapters/bulk_rna_py/run.py      # count matrix + sample sheet (+ DE tables) -> contract
  adapters/bulk_rna_py/deseq2_contrast.py  # optional pydeseq2 helper
  scripts/geo_series_matrix.py     # GEO series matrix -> sample sheet CSV
  scripts/contract.py              # finalize (hashes) + validate
  scripts/validate_package.py
  scripts/build_portal.py          # manifest -> 8 static pages + assets
  templates/site/*.html.j2         # pages
  templates/assets/                # site.css, app.js, charts.js, api.static.js (DuckDB-WASM), api-contract.json
doc/                               # design documents
```
