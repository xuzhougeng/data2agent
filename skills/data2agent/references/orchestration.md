# Orchestration

## Values to bind before anything else

| Value | Meaning |
| --- | --- |
| `SKILL_ROOT` | Absolute path of this skill directory (`.../skills/data2agent`) |
| `PROJECT_ROOT` | Absolute output project directory chosen by the user (default `./<dataset-id>-project`) |
| `PY` | From `PROJECT_ROOT/.d2a/env.json` after `bootstrap.sh`: the isolated venv's interpreter. Never the system `python3` |
| `PORTAL` | From `.d2a/env.json`: the `portal` binary, or null when none could be found, downloaded or built (then MCP verification and the hosted target are skipped and reported) |

Run every command from `PROJECT_ROOT` with explicit paths. Quote arguments; never interpolate user text into shell.

## Workspace

```
PROJECT_ROOT/
├── raw/            downloads and user-supplied inputs (never modified)
├── work/           sources.json, samples.csv, series.json, inventory.json, curation.json, decision.json, de/*.csv
├── pkg/            the contract package (adapter output, then portal files)
├── preview/        preview build (subsampled copy of pkg rendered with --preview-note)
├── reports/        assessment.md, validation.json, mcp-verify.json, acceptance-cases.json, checklist.md, screenshots/
├── dist/           <id>-portal.zip and its SHA-256
└── .pipeline/      stage markers (empty files) and workflow.json
```

Create `raw/ work/ pkg/ reports/ .pipeline/` at the start. Preview and dist are created by their stages. `.d2a/` (venv, env.json, check_env.json) is created by `bootstrap.sh` and never shipped.

## Markers and the workflow record

- Markers are empty files `.pipeline/<stage>_done`, written only after the stage's gate passed.
- `.pipeline/workflow.json` records, per stage: start/end time (UTC), commands run, gate outputs (paths), agent identity for curator and verifier, retries, and the SHA-256 of `pkg/manifest.json` when the stage finished. Append; never rewrite history. A stage whose inputs changed (new raw file, edited curation, changed decision) is re-run and its marker removed first.
- Hashes are the lock: `manifest.json → files` records every data file. Any edit to a parquet after curation invalidates verification; re-run from Build.

## Agents

- You coordinate and may do Ingest, Assess, Curate, Build and Deliver yourself.
- **Verify must be a fresh agent** (host subagent) that did not write the curation. Give it: `PROJECT_ROOT`, `SKILL_ROOT`, the raw file list, the decision, and [acceptance.md](acceptance.md). It writes `reports/acceptance-cases.json` with expected values derived from `raw/`, runs the verifiers, ticks the checklist, and returns a short summary plus paths. It may not edit `pkg/`; failures come back to you.
- If the host cannot spawn agents, do the verification yourself but say so in the final report ("independent verification unavailable").

## Retries and stopping

- Download failures: 3 attempts, then report the URL and stop the stage.
- Adapter failures: inspect the traceback, fix inputs/arguments, at most 3 attempts; if the data genuinely does not fit an existing adapter, write a new adapter under `adapters/<kind>_<lang>/` following [core-schemas.md](core-schemas.md) and note it in the report.
- Curation: at most 2 rounds of `apply_curation.py --check-ontology`; unresolved terms stay unmapped (free text), never guessed.
- Verification: at most 6 repair rounds per failing case; a case that cannot be made to pass is reported, not deleted.
- Never retry an unchanged external condition (no network, missing credential) more than once.

## Resume

On resume, read `.pipeline/workflow.json`, check which markers exist, recompute the manifest hash and compare with the last recorded one. If they differ, restart from Build. Preserve `work/decision.json` unless the user changes it.
