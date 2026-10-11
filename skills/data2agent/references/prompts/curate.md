# Stage 3 — Curate

Goal: `work/curation.json` written by you, applied to a fresh full package in `pkg/`, ontology ids verified.

1. Build the full package (no subsampling) with the adapter, passing what you already know (`--group`, `--label`, `--gene-info`, `--de`, `--organism/--taxon`, `--accession`, `--title`). Several modalities (RNA + proteomics + …): one adapter run per modality into `work/<modality>/` with identical `obs_id` values, then `merge_modalities.py pkg --primary work/rna --add proteins=work/prot …` (see [core-schemas](../core-schemas.md#multi-omics-several-modalities-over-the-same-samples)). Source Data / supplementary workbooks: `source_data_py/run.py probe raw/`, then write `work/source_data.json` per [source-data.md](../source-data.md) (this is curation work: figure mapping, variable names, units, captions, charts), then `apply pkg work/source_data.json` (`--init` when the paper has no omics matrix). Validate it.
2. Inspect the real values: for every obs facet column, list distinct values and counts (`"$PY" -c "import duckdb; print(duckdb.sql(\"select <col>, count(*) from 'pkg/data/obs.parquet' group by 1\"))"`).
3. Write `work/curation.json` per [curation.md](../curation.md) and [paper-extraction.md](../paper-extraction.md):
   - dataset text from the paper / GEO series (`work/series.json`, `work/paper.json`, `raw/paper/`);
   - labels for every visible column; `hidden` for GEO noise columns;
   - exactly one `primary_group`;
   - ontology `terms` for cell type, tissue, disease, assay, developmental stage, sex where the value is unambiguous. Look terms up in OLS4 (`https://www.ebi.ac.uk/ols4/api/search?q=<value>&ontology=<cl|uberon|mondo|efo|…>&exact=false&rows=5`) and pick the exact or nearest broader term; record non-exact choices in `notes`;
   - result table labels and descriptions naming the comparison and method;
   - for every figure panel (`figures` block): the panel label as in the paper, the legend sentence as caption, a corrected `chart` when the inferred one misreads the layout, and `feature_col` when a column holds gene/protein ids.
4. Apply and check:
   ```bash
   "$PY" "$SKILL_ROOT/scripts/apply_curation.py" pkg work/curation.json --check-ontology --cache work/ontology-cache.json --report reports/curation.json
   "$PY" "$SKILL_ROOT/scripts/validate_package.py" pkg --report reports/validation.json
   ```
   Unknown ids → fix or drop the term (max 2 rounds). Never invent an id to pass.
5. Record in `.pipeline/workflow.json`: your agent identity as curator, the curation file hash, coverage numbers from `reports/curation.json` (columns relabelled, values mapped per column). Write `.pipeline/curate_done`.

Curation is content; it never changes numeric data, row counts or ids.
