# Curation rules (stage 3)

Curation turns machine column names and free-text annotations into labelled, ontology-aligned metadata and fills the dataset-level text. It is the only stage where you write content into the package, and it goes through one file: `work/curation.json`, applied by `apply_curation.py`.

## curation.json

```json
{
  "dataset": {
    "title": "…", "short_title": "…", "description": "2–4 sentences, plain language, no marketing",
    "kind": "scrna", "organism": {"label": "Homo sapiens", "taxon": "NCBITaxon:9606"},
    "license": "CC-BY-4.0", "access": "open",
    "source": {"accession": "GSE…", "repository": "GEO", "urls": ["…"],
               "paper": {"doi": "…", "title": "…", "authors": "…", "journal": "…", "year": 2015, "citation": "…"}},
    "contact": {"name": "…", "email": "…"},
    "methods": "markdown; what the source files are and what the adapter did"
  },
  "obs": {
    "columns": {
      "louvain": {"label": "Cell type", "role": "facet", "primary_group": true,
                  "ontology": "CL", "terms": {"CD4 T cells": {"id": "CL:0000624", "label": "CD4-positive, alpha-beta T cell"}}},
      "percent_mito": {"label": "Mitochondrial fraction", "role": "numeric"},
      "description_1": {"role": "hidden"}
    }
  },
  "features": {"columns": {"n_cells": {"label": "Cells detected in"}}},
  "results": {"markers": {"label": "Marker genes", "description": "…"}},
  "proteins": {"columns": {"gene_symbol": {"label": "Encoding gene"}}},
  "figures": {"fig2_2a": {"label": "Fig. 2a", "caption": "Body weight at 8 weeks (g); n = 4 mice per genotype.", "chart": {"type": "columns", "value_label": "body weight (g)"}},
              "fig2_2b": {"feature_col": "gene", "features": "features"}},
  "notes": ["anything you could not map and why"]
}
```

- `terms` maps each distinct value of a column to an ontology term. `apply_curation.py` adds `<col>_ontology_term_id` and `<col>_ontology_label` columns to `obs.parquet`, declares them with `role: ontology`, and leaves the original column untouched.
- Values without a confident term are simply absent from `terms`; the column still works as a facet.
- `role: hidden` hides noise (GEO description lines, internal library names) from tables without deleting it.
- Any table in `tables` (obs, features, and every further modality such as `proteins`) accepts the same `columns` block.
- `figures.<panel id>` corrects what `source_data_py` inferred: `label`, `caption` (the figure legend sentence for that panel), `chart` (`columns` | `group` x,y | `scatter` x,y | `line` | `none`, plus `value_label`), and `feature_col`/`features` when a column holds gene or protein ids so rows link to the feature page. Never retype numbers; the parquet is the authors' sheet.

## Ontology choice

| Annotation | Ontology | Lookup |
| --- | --- | --- |
| cell type | CL | https://www.ebi.ac.uk/ols4/api/search?q=…&ontology=cl |
| tissue / organ | UBERON | ontology=uberon |
| disease | MONDO | ontology=mondo |
| assay / technology | EFO | ontology=efo |
| organism | NCBITaxon | ontology=ncbitaxon |
| developmental stage | HsapDv / MmusDv (or UBERON life-cycle stage) | ontology=hsapdv / mmusdv |
| sex | PATO (`PATO:0000383` female, `PATO:0000384` male) | — |
| ethnicity | HANCESTRO | ontology=hancestro |

Prefer exact label matches; accept a broader term over a wrong narrow one; record the choice in `notes` when it was not exact. `apply_curation.py --check-ontology` verifies every id exists in OLS4 (cached in `work/ontology-cache.json`); unknown ids fail the gate and must be fixed or removed.

## What not to do

- Do not rename `obs_id` / `feature_id` values, drop rows, or edit numeric data. Curation changes labels, roles and adds term columns only.
- Do not infer a value for a sample from other samples ("probably also female").
- Do not write claims about the biology that the paper does not make.
- Do not put secrets, personal emails other than the published contact, or internal paths into the package.
