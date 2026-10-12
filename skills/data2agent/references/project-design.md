# Design a scientific database project

Start with the questions users need to answer. A data file format alone does not specify a database, and one successful example does not define every future site's pages, schema or style.

## Capture the brief

For a topic-only request, discover a small set of relevant primary sources and their accessible artifacts. Establish a useful first release without presenting a selected catalog as exhaustive. Record inclusion/exclusion and scope limits. Do not demand that the user supply accessions the Agent can find.

Use a compact `project.json`; extend it for the project rather than requiring one universal schema:

```json
{
  "id": "project-slug",
  "objective": "Scientific purpose and intended audience",
  "scope": {"included": [], "excluded": [], "catalog_is_exhaustive": false},
  "questions": [],
  "entities": [],
  "assets": [],
  "processing": {"reuse_author_outputs": [], "compute": [], "validation": []},
  "application": {"entry_points": [], "required_queries": [], "visual_direction": ""},
  "deployment": {"target": "static or hosted", "destination": "", "basis": "user or agent decision with evidence"}
}
```

Fill this from evidence and user intent, not from a predetermined list of generic database features. Omit irrelevant fields; add explicit relationships, identifiers and release/update behavior when needed. A prototype, catalog and queryable release are distinct outcomes.

## Match model and architecture to the project

| Scenario | Model and processing questions | Application implications |
| --- | --- | --- |
| One compatible omics dataset | What are observations, features, units and author results? | Bundled Parquet portal may fit; customize when requested |
| Multi-study topic database | Study/cohort/sample relationships, reanalysis overlap, comparable assays, identifier namespaces | Study-aware search, filters, evidence links, distinct availability states and updates |
| Genome publication | Organism, assembly version, sequence, gene/transcript/exon relationships, annotations and evidence | Gene/region/sequence entry points and genome views; no fabricated observation matrix |
| Track collection | Reference build, intervals, signal meaning, normalization, indexed files | Genome browser with linked annotation tables; keep native indexed formats |
| Source-data paper | Figure/panel identity, cleaning recipes, units and author statistics | Figure/measurement navigation; a matrix is optional |

Choose persistent metadata storage, matrix/asset storage and indexes independently. For example, a relational metadata catalog can reference sparse matrices, H5AD, bigWig or FASTA; those assets need not be expanded into a single SQL table. Keep assembly versions and study-specific gene presence explicit.

Static delivery is appropriate when supported browser queries and precomputed results answer the requested questions. Hosted services become useful for online computation, writes, controlled access, repeated ingestion, complex joins or resource limits. Size is one input, not the sole threshold. Pick a stack supported by the environment and required capabilities; a custom backend does not require the bundled Go portal.

## Contracts and evidence

Keep source identity, checksums, processing provenance, artifact types, relationships and query semantics explicit in every project. Version the chosen data model and write its validators. The existing `templates/manifest.schema.json` validates a particular Parquet package; it is not a universal contract for genomes, themes or application source.

The dataset package validator proves structural consistency, not scientific accuracy. For thematic projects, implement domain validation plus raw-derived query checks and application checks. See [acceptance](acceptance.md).

## Decisions without unnecessary pauses

Reuse requested scope, target, design direction and destination. The Agent can choose reversible implementation details and record why. Ask when available evidence cannot resolve a material scientific ambiguity, whether a large raw-data computation is intended, or where an external service should run. Produce a concrete assessment or preview when it helps that decision; do not impose a new approval gate when the user already authorized the work.
