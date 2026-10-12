# Build the application for its scientific topic

Design navigation and interactions around what the intended user needs to find, compare or download. Reuse tested components; allow the Agent to write the frontend, backend, queries, indexes and deployment files appropriate to this project.

## From questions to an application

For every primary user task, identify its entity, query, evidence and useful visualization. Examples:

- Topic database: study/cohort/material discovery, feature lookup within studies, explicit availability and reanalysis relationships.
- Genome database: assembly and chromosome entry points, gene/transcript pages, region navigation, strand-correct sequence extraction and annotated track views.
- Single-cell collection: study-specific embeddings, gene/alias search, group/condition summaries, source labels and biological uncertainty.
- Source-data publication: figure/panel navigation, measurement tables, units and author statistics.

These are design patterns, not a required page inventory. Different topics may need different visual language, layout, navigation and interactions. A genome project should not inherit cell-count cards or an expression heatmap merely because the first example used them. Preserve an existing visual identity when editing a site.

Use a concrete preview with verified data when helpful. Clearly mark sampling, unavailable queries or unprocessed catalog items. Replace prototype content with real connected behavior before delivery; do not present an attractive source catalog as a queryable expression database.

## Query and service boundaries

Choose an appropriate stack based on current project/environment capabilities. The bundled Go portal handles its Parquet contract; a custom Python, Go, JavaScript or other service may better fit thematic computation, indexed assets or updates. Keep scientific processing separate from ordinary request handling unless online analysis is requested; long jobs need durable status and results.

Define shared domain query semantics for HTTP/MCP and frontend functions: identifier resolution, units, filtering, pagination, missing/not-measured behavior and errors. MCP tool names may follow the domain; do not force a genome into `get_obs` or require SQL when named queries suffice. Test actual transports, not only function calls.

If arbitrary SQL is exposed on a server, a SELECT-prefix check is insufficient. Use a read-only database boundary, disable external filesystem/network/extension access in the query engine as appropriate, and bound resources. Named queries are a valid simpler interface. Escape source text in templates; configure autoescape for the actual template suffix (for example `.html.j2`). Never trust dataset metadata as HTML or executable commands.

The legacy Go portal currently filters SQL by statement prefix; that alone does not isolate host files. Before exposing it to untrusted clients, implement and test the required database/process restrictions or choose a service with appropriate named queries. Do not assume the published word "read-only" establishes this boundary.

## Native scientific assets

Keep large sparse matrices and indexed tracks/sequences in formats suited to their readers. Expose reference versions and query semantics. Check HTTP Range and cross-origin behavior when a browser reads remote indexed files; embedding a browser widget alone does not prove the files can be read.

## Delivery and operation

Provide source, schema/migrations, data/assets or durable references, environment locks, build/update scripts and a release manifest. Use relative/configurable paths. Separate analysis dependencies from the smaller serving runtime when useful.

For hosted delivery, test health plus a real scientific query at the selected destination. A native local service, container and public deployment are distinct checks; report the one actually performed. Keep local-first projects local. Verify container health with a command available in its runtime, and use a dataset-independent health endpoint rather than assuming an `obs` table exists.

An update should preserve unrelated studies and user application work. Build changed artifacts in staging, validate, then switch the selected service to a consistent release. Deliver start/status/stop and backup/update instructions matching the implementation, without assuming a particular process manager or hosting provider.
