---
name: data2agent
description: Build and maintain scientific databases from research topics, papers and public or local datasets. Use for a dataset portal, multi-study thematic database, organism/genome database, or an update to one, including data discovery, preprocessing, custom web applications and static or hosted delivery.
---

# Data2Agent

Turn the user's scientific objective into a working, traceable database project. The host Agent is the coordinator and developer: discover data, choose and execute domain tools, design the data model and application, verify it, and deliver/deploy within the requested scope. Write project-specific adapters, services and frontend code when needed. A fixed portal is one useful output, not the product boundary.

## Establish the project

1. Read the request and existing project/session decisions. A research topic is a valid starting point: discover candidate sources before asking for accession numbers. For an existing project, inspect its code, data receipts and deployment state before changing it.
2. Read [project design](references/project-design.md). Record the scientific questions, scope, entities, data availability, processing, application tasks and execution/deployment choices in `project.json`. Reuse earlier user choices. Resolve reversible implementation defaults yourself, recording them as Agent decisions; ask only for missing information that materially changes scope, compute/storage commitment or deployment destination. This skill does not add a universal confirmation gate.
3. Choose a route:
   - **Dataset publication:** one compatible data package, with optional source-data figures or modalities. Existing adapters, the Parquet contract and portal templates can be efficient. Read [core schemas](references/core-schemas.md), or [source data](references/source-data.md) for workbooks.
   - **Thematic / organism / genome database:** independent studies or domain entities, custom interactions, ongoing updates or online analysis. Read [application design](references/application-design.md), plus [single-cell](references/domains/single-cell.md) or [genome and tracks](references/domains/genome.md) when relevant. A theme may still use static delivery if its queries and updates fit.
4. Bind `SKILL_ROOT` to this skill and `PROJECT_ROOT` to the chosen output directory. Set up the environment yourself:
   ```sh
   sh "$SKILL_ROOT/scripts/bootstrap.sh" "$PROJECT_ROOT" --profile project
   ```
   Use `--profile dataset` for the bundled omics adapters/templates. Read `.d2a/env.json`; use its `PY`, install any additional domain/application dependencies in project-owned environments, and record versions. Reuse a verified project environment when one already exists. Missing optional Go `PORTAL` disables only that implementation, not custom HTTP/MCP services.

## Execute toward the deliverable

Read [orchestration](references/orchestration.md) for workspace, task receipts, resume and evidence. Load stage details when needed:

| Work | Reference | Evidence of completion |
| --- | --- | --- |
| Discover and acquire | [ingest](references/prompts/ingest.md), [acquisition](references/data-acquisition.md) | Source inventory, inclusion reasons, immutable inputs and verified receipts |
| Assess and design | [assess](references/prompts/assess.md) | Concrete scope, data model, processing plan, application preview and recorded decisions |
| Curate and process | [curate](references/prompts/curate.md), [processing](references/processing.md) | Source-linked annotations, validated artifacts and processing receipts |
| Build the database/application | [build](references/prompts/build.md) | Working scientific queries, topic-appropriate pages and domain validation |
| Verify | [verify](references/prompts/verify.md), [acceptance](references/acceptance.md) | Raw-derived checks through actual interfaces, browser evidence and explicit limitations |
| Deliver and deploy | [deliver](references/prompts/deliver.md), [deploy](references/prompts/deploy.md) | Portable source/data/environment records; service verified at the selected destination |

These are dependencies, not a prohibition on iteration. A small verified data slice can drive a preview while other sources are assessed. A new source, changed scientific assumption or failed check can send work back to acquisition/processing. An application-only edit should not automatically rerun analysis.

## Scientific and operational invariants

- **Evidence before claims.** Trace values, labels, identifiers and citations to inputs or documented computation. Keep author outputs distinct from recomputed analysis and model predictions. Preserve unresolved labels as unknown; verify ontology IDs before using them.
- **Represent the scientific objects.** Studies, subjects, samples, assays, cells, assemblies, genes, regions and evidence can require different entities. Keep sparse matrices and indexed genomic assets in suitable formats. Define versioned contracts and validators for the chosen model; the bundled Parquet schema is not a universal database schema.
- **Preserve distinctions.** Cataloged, downloaded, processed, validated and queryable are different states. A GEO library count is not a cell count. Overlapping cohorts/reanalyses must not inflate totals. Different studies or assays are not automatically comparable; unmeasured values are not zero.
- **Compute through domain tools.** Agent-authored glue and workflows may perform preprocessing and analysis using established tools. Inspect input units/layers first, validate joins and dimensions, and record parameters, environments, seeds and outputs. Do not invent scientific results in prose or code constants.
- **Adapt the application.** Select navigation, interactions, visualizations and visual style for the scientific topic and audience. Reuse components without requiring every project to resemble the first example. Pick static/hosted architecture from query, compute, update and access needs, as well as size.
- **Verify independently.** For a new scientific data release, use a fresh verifier that did not curate it, deriving expected values from original inputs. If unavailable, report the independence limit. Packaging/file hashes and a process PID are not scientific or service acceptance tests.
- **Respect the destination and report reality.** Local execution does not authorize public publication. Deploy to an authorized destination using available tools; retain a verified native alternative when an optional container path is blocked. Never describe a catalog, mockup, staged image or failed analysis as a completed database.

## Reusable execution tools

- `fetch_sources.py --project ... --plan source-plan.json`: reviewed local/public sources → checked inputs and resumable provenance. See [acquisition](references/data-acquisition.md).
- `run_pipeline.py --project ... --plan pipeline.json`: reviewed task graph → logs, content fingerprints, output gates and resumable task receipts. See [processing](references/processing.md). This is a local POSIX runner, not a cluster scheduler.
- `fetch_geo.py`, `geo_series_matrix.py`, `probe.py`: optional GEO and file-inspection helpers; inspect heuristic suggestions rather than treating them as scientific classifications.
- Existing `adapters/`, `apply_curation.py`, `merge_modalities.py`, `contract.py`, `validate_package.py`, `build_portal.py`: reusable **dataset-package** tools. `merge_modalities.py` requires matching observations and is not cross-study integration.
- `verify_mcp_server.py`: real stdio acceptance for an implemented MCP server; customize required tools/cases for its domain. HTTP, application and domain validators remain necessary.

## Handoff

Lead with the usable URL or delivered project/archive. State queryable scope separately from catalog coverage, what was preserved or recomputed, validation actually performed, and concrete remaining limits. Include source, data, dependency locks, processing/update commands, provenance and deployment instructions appropriate to the requested project. Keep detailed evidence in `reports/`.
