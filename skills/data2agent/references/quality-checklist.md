# Quality checklist (ticked by the verifier in stage 5, copied to reports/checklist.md)

Mark each item `[x]`, `[ ]` with a reason, or `n/a`. Any `[ ]` without an accepted reason blocks delivery.

## Content and provenance
- [ ] Every statistic on the Home page can be recomputed from the downloadable tables (count obs, features, groups, non-zeros)
- [ ] Every result table names its comparison and method; recomputed tables say "recomputed"
- [ ] `manifest.json → files` hashes match the shipped files (`validate_package.py` ok)
- [ ] Source accession / URLs / paper citation present and correct; licence stated or "see source"
- [ ] Ontology ids verified (`apply_curation.py --check-ontology` ok) and shown as label + id linking to OLS
- [ ] No placeholder text, no "lorem", no AI self-reference, no internal paths, no secrets

## Pages
- [ ] Home: title, description, stats, composition chart, explore cards, cite box when a paper exists
- [ ] Samples/Cells: facets reflect the current filter, table paginates, CSV export works, "Clear" resets
- [ ] Map (if embeddings): colour by primary group and by a feature; legend toggles; PNG download
- [ ] Feature page: search suggests, direct link `feature.html?id=…` works, per-group chart + dot plot + map overlay + result hits
- [ ] Results (if any): facets, sort, pagination, volcano or top-N chart, CSV export, feature links
- [ ] Multi-omics (if any): modality switch on the feature page, one stat per modality on Home, "Across modalities" links resolve both ways for a spot-checked gene/protein pair
- [ ] Figures (if any): every panel opens, chart matches the paper's panel layout or is set to `none`, caption is the legend text, CSV export works
- [ ] Download: every parquet listed with rows/size/sha; code snippets reference real paths
- [ ] API: SQL console runs the default and example queries; MCP command shown; tables listed
- [ ] Help: column dictionary complete, methods, cite, changelog, contact

## Behaviour
- [ ] No console errors on any page (browser devtools / Playwright)
- [ ] Empty states: a filter with zero rows shows "No rows match", unknown feature id shows a message
- [ ] 375 px width: no horizontal scroll of the page; nav collapses
- [ ] Dark mode renders (prefers-color-scheme)
- [ ] hosted only: `/api/obs/count`, `/api/features/search`, `/api/sql` respond; write SQL rejected
- [ ] MCP: `verify_mcp_server.py` passes with ≥ 5 cases including one error case

## Delivery
- [ ] `USAGE.md` matches the target (static: http.server + Pages; hosted: binary + compose)
- [ ] zip extracted in a fresh directory serves the Home page and passes `verify_mcp_server.py` again
