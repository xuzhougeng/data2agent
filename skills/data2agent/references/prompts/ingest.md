# Stage 1 — Ingest

Goal: all inputs in `raw/`, their provenance in `work/sources.json`, and `work/inventory.json` describing what they are.

1. Create the workspace (`raw/ work/ pkg/ reports/ .pipeline/`) under `PROJECT_ROOT`.
2. GEO accession given:
   ```bash
   "$PY" "$SKILL_ROOT/scripts/fetch_geo.py" GSE60450 --out raw --sources work/sources.json
   "$PY" "$SKILL_ROOT/scripts/geo_series_matrix.py" raw/GSE60450_series_matrix.txt.gz -o work/samples.csv --series-json work/series.json
   ```
   Several series matrices (one per platform) → one `samples-<GPL>.csv` each; say so in the assessment.
   A supplementary file larger than 2 GB is listed but not downloaded unless the user asks.
3. Local files given: copy or symlink them into `raw/` (never modify originals) and add them to `work/sources.json` with SHA-256 (`fetch_geo.py --add path` does this).
4. Paper given as DOI/URL/PDF: save the PDF or full text to `raw/paper/`; if only a DOI, fetch the Crossref record (`https://api.crossref.org/works/<doi>`) into `work/paper.json` for citation fields.
5. Probe:
   ```bash
   "$PY" "$SKILL_ROOT/scripts/probe.py" raw --samples work/samples.csv --out work/inventory.json
   ```
   Read `inventory.json`. It names the suggested `kind`, adapter, candidate matrices, sample tables, DE tables, `source_data` workbooks (journal Source Data: one sheet per figure panel), a `multi_modality_hint` (several matrices with different id patterns: RNA + protein + …), and a `tier_suggestion`.
6. Gate: `inventory.json` exists, `kind` is not `unknown` (if it is, ask the user what the files are before continuing). Write `.pipeline/ingest_done`.

Do not run adapters yet. Do not read matrices fully here; probe reads heads only.
