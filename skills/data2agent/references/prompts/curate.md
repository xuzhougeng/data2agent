# Curate and execute scientific processing

Goal: traceable domain artifacts with validated metadata, values and relationships. Read [processing](../processing.md) and the relevant domain reference.

1. Inspect actual input identifiers, layers/units, dimensions and annotations. Decide what author outputs to retain and which computations are needed for the stated objective. Keep scientific assumptions and resource choices in a processing plan.
2. Standardize metadata through explicit keyed mappings. Preserve original IDs, categories and unresolved values; verify ontology IDs before assigning them. Separate author annotations, predictions and recomputed outputs. Document display-name expansions.
3. Select mature domain tools and write necessary adapters/workflows. Record environment locks, parameters, seeds, source/reference versions and validation checks. Use the task runner or an existing workflow engine to preserve execution state and invalidate changed descendants.
4. Check shape, unique IDs/relationships, missingness, units, finite values and domain-specific constraints. A changed numeric value requires a documented processing method, not an editorial curation edit.
5. Update provenance and evidence. A failed or partially downloaded task is not queryable data.

For the dataset-package route, use the existing adapters and `contract.finalize`, then `apply_curation.py` for labels/ontology/text and `validate_package.py` for structural checks. Multi-modal merge requires matching observations. For a thematic project, implement validators for its own model rather than weakening the Parquet schema or fabricating its required entities. Source-data workbooks retain the reviewed recipe workflow in [source-data](../source-data.md).
