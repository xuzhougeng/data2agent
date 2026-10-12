# Deliver a reproducible database project

Package the implemented source, versioned data/indexes or durable source references, dependency locks, processing/update commands, provenance and start/stop/deployment instructions. The exact layout follows the chosen architecture; a custom application is not required to fit the fixed portal zip layout.

1. Finalize a release inventory with hashes and concrete scope. Preserve the distinction between catalog entries and queryable data. Include original inputs when suitable for size/access/reproducibility, or explain how pinned sources can be acquired again.
2. Exclude local environments, credentials, active process state, unrelated files and accidental caches. Preserve user application work and source licenses/attribution; do not assign a blanket license to heterogeneous source data.
3. Extract/copy the delivery into an independent directory and run its intended startup and a scientific query. Verify downloads/indexed access where applicable. If using the same host/runtime, say so; this does not prove every OS/container deployment.
4. Record the archive checksum and validation scope. A failed optional container build does not invalidate a verified native local delivery, but remains a reported limitation.

Lead the handoff with the usable URL or project/archive path. State actual imported scope, implemented functionality, scientific processing/validation and remaining limits. Do not ask the user to perform setup the Agent can complete within the available environment. Keep the selected local service running when the user requested it; stop only obsolete task-owned previews.
