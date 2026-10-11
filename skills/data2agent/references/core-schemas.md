# Core schemas and adapters

The data contract (`templates/manifest.schema.json`) is omics-agnostic: `obs` x `features` x `matrix`, plus `embeddings`, `results`, `assets`, `aggregates`. Each omics kind maps onto it with fixed conventions so that the portal, the MCP tools and cross-dataset queries behave the same.

## Conventions every adapter follows

- `obs.obs_id` and `features.feature_id` are strings, unique, non-null. Use the source's stable identifier (GSM, cell barcode, Entrez/Ensembl id, probe id).
- `matrix`: long table `obs_id, feature_id, value(float32)`, **non-zero entries only**, sorted by `feature_id` then `obs_id`, row groups of ~50k rows, zstd. First matrix is what the pages display; raw counts can be a second matrix.
- `features.symbol` exists whenever a human-readable name exists; mark `feature_id` and `symbol` with `search: true`.
- Exactly one obs column carries `primary_group: true` (cell type, condition, tissue...). It drives composition charts, per-group aggregates and the dot/strip plots.
- `aggregates/feature_group.parquet`: `feature_id, group, n, mean, pct` over the display matrix by the primary group.
- Column `role`: `facet` for categorical columns with <= 50 distinct values, `numeric` for continuous, `text` for free text / high-cardinality, `link` for URLs, `ontology` for term-id columns (with `ontology` prefix and `label_column`), `coordinate` for chrom/start/end, `hidden` to keep but not show.
- Labels are human: "Cell type", not "louvain"; "Developmental stage", not "developmental_stage". Curation (stage 3) sets them; adapters only capitalise.

## Kind -> adapter

| kind | obs | features | display matrix | embeddings | results | adapter |
| --- | --- | --- | --- | --- | --- | --- |
| `scrna` | cells | genes | log-normalised (or counts) from `.raw` / `X` / a layer | UMAP, t-SNE, PCA from `obsm`, spatial coords | `rank_genes_groups` markers | `scrna_py` (h5ad; 10x MTX via `scanpy.read_10x_mtx` first) |
| `bulk_rna` | samples | genes | log2 CPM (+ raw counts as 2nd matrix) | PCA on top variable genes | DE tables supplied via `--de` (DESeq2 / edgeR / limma headers auto-detected) | `bulk_rna_py` |
| `methylation` | samples | CpG probes (chrom, pos) | beta (as given) | PCA | DMP / DMR tables | `bulk_rna_py --kind methylation --transform none --feature-label "CpG probes"` on a beta matrix; IDAT → beta first with minfi/sesame |
| `proteomics` | samples | proteins | log2(intensity + 1) | PCA | differential tables | `bulk_rna_py --kind proteomics --transform log2 --feature-label Proteins --ref gene_symbol=features.symbol` (missing intensities are stored as absent = 0) |
| `metabolomics` | samples | metabolites | log2(abundance + 1) | PCA | differential tables | `bulk_rna_py --kind metabolomics --transform log2 --feature-label Metabolites` |
| `atac` (bulk) | samples | peaks (chrom,start,end) | log2 CPM | PCA | DAR | `bulk_rna_py --kind atac --feature-label Peaks --feature-cols chrom,start,end` |
| `atac` (single cell) | cells | peaks | counts | UMAP / PCA | DAR | `scrna_py` on the peak h5ad (`--kind atac`) |
| `spatial` | spots | genes | counts / lognorm | spatial x,y (`spatial: true`) | — | `scrna_py` with `obsm['spatial']` |

`bulk_rna_py` is the generic wide-matrix adapter: any `features x samples` table plus a sample sheet. `--transform` picks the display matrix (`log2cpm` for counts, `log2` for intensities/abundances, `none` for betas and scores); `--feature-label` names the modality; `--ref col=table.column` declares that a feature column holds ids of another modality (the portal shows the link both ways).

## Multi-omics (several modalities over the same samples)

Run one adapter per modality into its own package (identical `obs_id` values in every sample sheet), then merge:

```bash
"$PY" "$SKILL_ROOT/scripts/merge_modalities.py" pkg --primary work/rna --add proteins=work/prot --add metabolites=work/met --id <id> --title "..."
```

In the merged package `tables.proteins` is the second feature table, its matrices are `proteins_<name>` with `features: "proteins"` and `kind: proteomics`, results/aggregates/embeddings carry the same prefix, and `kind` is `multi`. The portal derives the modality list from `matrices[].features`: the feature page gets a modality switch, the home page one stat per modality, and columns with `ref` become "Across modalities" links. Obs annotation columns only one package has are joined in. Modalities with different observation sets (unpaired cohorts) are separate datasets, not a merge.

## Source data (figure panels)

Journals increasingly publish the numbers behind every figure panel (Nature's "Source Data" workbooks: one sheet per panel). They are the most paper-faithful view of the result and go into the same package:

```bash
"$PY" "$SKILL_ROOT/adapters/source_data_py/run.py" pkg --xlsx "raw/Source Data Fig. 1.xlsx" --xlsx "raw/Source Data Fig. 2.xlsx"
```

Each sheet becomes `figures[].panels[]` with its parquet, the caption text found above the table, typed columns and an inferred `chart` (`columns`: every numeric column is a group; `group`: x categorical, y numeric; `scatter`; `none`). The Figures page draws it and offers CSV; SQL/MCP see `fig_<panel id>`. Fix labels, captions and chart hints in curation (`figures` block), never the values.

## Writing a new adapter

1. Create `adapters/<kind>_<lang>/` with `ADAPTER.md` (inputs, deps, command, outputs), `run.*`, and a lock file.
2. Read inputs with the domain library; build the tables above; write parquet (pyarrow / arrow / any writer).
3. Write `manifest.json` following the schema; in Python call `contract.finalize()`, otherwise run `validate_package.py <pkg> --finalize`.
4. The only acceptance test is `validate_package.py` exit 0. Keep science in the library calls; the adapter moves data.

## GEO specifics

- Count matrices in supplementary files often have library names as columns; the GSM mapping lives in `!Sample_description` or `!Sample_title`. `geo_series_matrix.py` exposes those as `description_N` / `title`; pass the matching column as `--sample-key`.
- Characteristics become columns (`tissue`, `cell_type`, `age`...). Values are free text; curation maps them to labels and ontology ids.
- Processed matrices (counts, TPM, FPKM, beta) are accepted; raw SRA re-processing is out of scope.
- Gene annotation: Entrez ids -> `--gene-info` (NCBI gene_info.gz); Ensembl ids -> a `--symbols` table (id, symbol, name) prepared from a GTF or BioMart export.
