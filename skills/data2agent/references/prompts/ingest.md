# Discover, inspect and acquire

Goal: an evidence-backed inventory of usable sources, not merely a directory of downloaded files. Read [acquisition](../data-acquisition.md).

1. For a topic, search primary repositories/publications and record candidate sources, inclusion/exclusion, organism/material/assay, relationships, accessibility and artifact availability. For supplied files/accessions, inspect those first. Reconcile the inventory with the user's actual scope.
2. Separate catalog coverage from the first queryable release. Identify reused studies/samples, mixed assays and repository subsets. Do not equate source sample counts with observations or import every file from a SuperSeries blindly.
3. Write a reviewed source plan with stable IDs and distinct paths, then acquire with `fetch_sources.py` or an appropriate repository tool. Record URL/accession, source version, bytes, hash and retrieval outcome. Original inputs remain unchanged.
4. Inspect signatures, headers, dimensions and annotation keys. Use `probe.py` as a hint; examine unknown/numeric-looking files before asking the user. If an unfamiliar format needs an adapter, implement one with the relevant domain library and explicit validation.
5. Record what is known, missing and feasible. A catalog-only source is a valid inventory entry but not evidence that its expression, sequence or signal is queryable.

For a known GSE and the dataset-package route, `fetch_geo.py` and `geo_series_matrix.py` remain useful. For multiple studies, use separate source identities/destinations; basename-based receipts from separate downloads must not collide. See [project design](../project-design.md) before forcing independent studies into one package.

Completion evidence: source inventory, receipts, inclusion scope and successful inspection of inputs needed for the next task. An unavailable optional study does not block unrelated verified sources; an essential missing input must remain explicit.
