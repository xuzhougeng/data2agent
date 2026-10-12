# Build a queryable database and application

Goal: the selected scientific tasks work on the validated artifacts. Read [application design](../application-design.md).

For thematic, organism and genome projects:

1. Implement the chosen data model, indexes, queries and schema/migrations. Preserve source and study/reference boundaries; expose catalog and data availability separately.
2. Build pages, navigation, interactions and visual design suited to the topic. Reuse components where helpful; write new frontend/backend code when required. Connect visible features to actual queries and data.
3. Implement the requested interfaces, including domain-appropriate HTTP/MCP functions where useful. Define unknown/missing/not-measured behavior and error/resource boundaries.
4. Install serving dependencies, launch at the selected local destination, and exercise representative scientific queries. Test the application in a browser at desktop/mobile sizes. Keep source, analysis environment and serving environment reproducible.
5. Record source/data versions and validation evidence. A server process, successful compile or database file alone is insufficient acceptance.

For a compatible dataset package, `validate_package.py` and `build_portal.py --target static|hosted` remain available. The Go service is an optional implementation; do not describe an unimplemented Postgres mode as available. If a standalone skill installation lacks a deployment asset, supply the needed project-owned configuration before promising that deployment method.

For remote object storage or publication, use the destination already authorized by the user. Confirm real Range retrieval/CORS when indexed assets need them. Local-first work stays local.
