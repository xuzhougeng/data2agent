# Project execution and resume

The host Agent coordinates research, data engineering, application development and delivery. Persist working state so a fresh session can resume without the conversation.

## Workspace and ownership

Preserve an existing repository layout. A new project often contains:

```text
project.json          objective, scope, entities, queries, design and decisions
source-plan.json      selected inputs with identity and optional pinned hashes
pipeline.json         reviewed processing/build tasks, when using the runner
raw/                  original inputs, never rewritten by processing
work/                 inventories, curation, intermediates and source receipts
pipeline/             project-specific adapters, scientific workflows and validators
app/, web/            services and topic-specific interface, if needed
pkg/                  release data, indexes, manifests and/or built application
reports/              assessment, acceptance, browser and deployment evidence
dist/                 portable deliveries and checksums
.d2a/                 project-owned environment and environment record
.pipeline/            machine task receipts, logs and append-only events
```

A generated project must not depend on an absolute skill/check-out path at runtime. Ship used helpers or a pinned dependency when needed. Exclude local environments, active PIDs, credentials and unrelated repository state from delivery.

## Decisions

Record `work/decision.json` or equivalent fields in `project.json`: scope, target, implementation, destination, and the basis for each choice. Use `decided_by: user` only for an actual user instruction; mark implementation defaults `agent` with a rationale. Earlier decisions remain authoritative until changed. Discovery and reversible local preparation need not wait for optional preferences. Work requiring a missing destination or resource commitment waits for that information; continue independent work.

The optional S/M/L/XL names are historical hints, not capability switches. A small submission service may need a server; large read-only tracks can use indexed assets. Missing Go `portal` does not rule out another backend.

## Tasks and evidence

Use [processing](processing.md) and `run_pipeline.py` for a reviewed local DAG, or an existing workflow engine with appropriate persistence and validation. The bundled runner records `.pipeline/tasks/<id>.json`, append-only `.pipeline/events.jsonl`, and per-attempt logs. It checks content fingerprints before reuse, requires outputs and validation commands, and records real exit/failure/timeout. It retains previous generated outputs in its attempt directory and restores them after failure; clean those backups only deliberately after validation.

It is not a remote scheduler. An HPC/cloud wrapper must submit, poll terminal job status and validate outputs, or use a suitable existing scheduler. A chat checkpoint or process ID is not a completion receipt.

Stage markers are optional conveniences. Write them only after their gate passes. Record commands, decisions, environments, input/release hashes, report paths and verification limits. On resume, compare fingerprints rather than trusting a marker or timestamp. Changed sources/scientific parameters invalidate downstream analysis and acceptance; application edits invalidate relevant application checks. Schema changes also require migration and data compatibility checks.

For live services, build a new release in a staging directory or stop the selected service before replacing its data. The local runner's output staging is a task gate, not a zero-downtime release switch.

## Verification and recovery

For a new scientific release, delegate [acceptance](acceptance.md) to a fresh verifier with original inputs, decisions, documented methods and real interfaces. It may write reports but may not curate data or derive expected values from the built package. If delegation is unavailable, perform the checks and disclose the independence limit.

Retry after a concrete corrective action. The acquisition helper retries transient transfers up to three times; do not repeatedly retry unchanged missing credentials, denied access, an unavailable repository or a broken host proxy. Report the blocked capability and complete unaffected work. Fix a failed acceptance case or leave it explicitly unverified; never weaken it to pass.

If a local listener is restricted, use the host's normal execution-permission mechanism for the specific authorized service. Do not use `file://` as evidence that a module-based web app works. If browser execution is unavailable, finish data/API/packaging checks and record the missing browser validation accurately.
