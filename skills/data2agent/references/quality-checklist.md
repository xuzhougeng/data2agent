# Release checks

Apply checks to the requested capabilities and chosen implementation. Mark others not applicable or unverified with a reason; do not add features just to complete this list.

## Scientific evidence

- [ ] Source identity, provenance, versions and byte hashes are recorded.
- [ ] Catalog coverage and queryable/imported data are counted separately.
- [ ] Original identifiers and metadata joins are validated; overlaps/reanalyses do not inflate totals.
- [ ] Numeric units/layers, missingness and transformations are explicit.
- [ ] Domain validation covers relevant matrix, interval, sequence or result constraints.
- [ ] Author labels/results, predictions and recomputed outputs remain distinguishable.
- [ ] Claimed ontology terms, references and citations have supporting evidence.
- [ ] Raw-derived cases check meaningful values/relationships through real interfaces.

## Application

- [ ] Information architecture and visual design fit the scientific topic and requested audience.
- [ ] Primary user tasks work with real data; no promised feature is a placeholder.
- [ ] Unknown IDs, empty filters and unavailable catalog data produce clear states.
- [ ] Text is escaped; scientific plots show units, context and useful legends.
- [ ] Desktop/mobile navigation and layout work; normal use has no unexpected console errors.
- [ ] Downloads, aliases, source links and indexed-asset access work where supplied.
- [ ] HTTP/MCP/SQL boundaries are verified for the interfaces actually implemented.

## Reproducibility and delivery

- [ ] Environments, code, parameters and reference versions are recorded/locked.
- [ ] Failed/interrupted processing is not mistaken for completion.
- [ ] Changed inputs invalidate dependent results; verified unchanged outputs can be reused.
- [ ] Portable source/data or pinned acquisition instructions are included.
- [ ] The delivered project starts and answers a scientific query outside its original directory.
- [ ] The selected deployment method is verified; other methods remain explicitly unverified.
- [ ] Start/status/stop/update instructions match the implementation and preserve unrelated services.
- [ ] Final scope and remaining limitations are accurate.

A dedicated dark theme, account system, public domain, container or performance score is not universally required. Verify those if requested or claimed. Record independent versus self-verification, and evidence paths, in `reports/`.
