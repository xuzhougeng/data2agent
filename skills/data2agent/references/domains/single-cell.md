# Single-cell and single-nucleus database projects

Apply these rules to the relevant assay; do not impose human scRNA defaults on plants or all modalities.

## Inputs and identities

Determine whether an H5AD layer, R object or deposited table contains counts, CPM/TPM, log values, scaled residuals or a selected feature set. Inspect the actual object rather than trusting the extension. An RDS may be externally compressed again, or contain a list of full and subset objects. Retain one intended observation set; do not sum an `All` object and its control/treatment subsets.

Keep study, library/sample, donor/material and cell identities separate. Namespace cell IDs across independent studies. Preserve per-study feature presence: a gene not measured in one matrix is not an observed zero. Matching row counts do not prove a metadata join; use unique barcode/library keys and check both directions.

GEO series can include bulk controls, mutants, related subseries or reused atlas libraries. Track selected artifacts and exclusions explicitly. Counts reported in an abstract or sample listing are not imported cell counts.

## Author results and computation

Prefer suitable author labels and embeddings when available; otherwise compute with domain tools if required and label the result as recomputed. A numerical cluster is not a biological cell type. Preserve predicted labels, confidences and unresolved annotations without inventing marker-based identities. Do not transfer annotations from a reprocessed version unless IDs and scope have been verified.

A count normalization is a method choice, not a universal requirement. Never apply count normalization to residuals/log values. For a deliberately chosen display scale, `ln(1 + count / cell_total * 10000)` and `ln(1 + author_CPM / 100)` can express the corresponding arithmetic; record the assumption and keep source values. This does not make different studies or technologies statistically interchangeable.

For plant data, inspect organellar identifiers, reference annotation and protocol before choosing QC. Do not reuse mammalian mitochondrial cutoffs or human/mouse annotation models automatically. Species-specific alias dictionaries are versioned references; retain original gene IDs while indexing official and historical names.

Cross-study integration/batch correction, de novo annotation, trajectory inference and differential testing require a justified plan and appropriate experimental units. They are not an automatic prerequisite for a multi-study database. Study-aware browsing and summaries may better match the first release.

## Evidence to retain

- Source matrix/layer and original cell/gene order, annotation files, join keys, exclusions and reference build.
- Original values plus documented normalized/derived artifacts, software/parameter/model versions and seeds.
- Author or computed status for every embedding, cluster and annotation; keep raw category codes alongside documented display-name expansions.
- Sparse shape/nonzeros, complete finite coordinates, group membership and detection/mean denominators.
- Independent raw-derived checks of representative genes, all relevant annotation joins, a zero-expression group, unknown identifiers and not-measured genes.

A multi-study database does not require forcing independent cohorts through `merge_modalities.py`; that helper is for compatible modalities sharing the same observations.
