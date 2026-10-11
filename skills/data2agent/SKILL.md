---
name: data2agent
description: Turn one paper's omics data (GEO accession, h5ad, count matrix, supplementary tables) into a validated data package and a database portal (static site or self-hosted server) with SQL, MCP and download, through assess -> user decision -> curate -> build -> verify -> deliver. Use for "make a database/portal/website for this dataset", "publish this GEO series as a queryable resource", or resumes of such a project.
---

# Data2Agent

Build a queryable, citable portal for one dataset. You are the coordinator; the host (Claude Code / Codex) is the runtime. Scripts are deterministic gates, you do the judgement: choosing an adapter, curating metadata, writing the assessment, writing acceptance cases.

## Start here

1. Inputs: a GEO accession and/or local data files, optionally the paper (DOI, PDF, or URL) and an output project directory. Ask only for what is missing and required. **Never ask the user to install or configure anything**; stage 0 does it.
2. Bind `SKILL_ROOT` to this directory and `PROJECT_ROOT` to the output directory, then run stage 0:
   ```bash
   sh "$SKILL_ROOT/scripts/bootstrap.sh" "$PROJECT_ROOT"      # installs uv if needed, builds .d2a/venv, verifies it, finds/downloads `portal`
   ```
   Read `PROJECT_ROOT/.d2a/env.json` and use its `PY` for every script and its `PORTAL` for MCP/hosted work. **Never run scripts with the system `python3`.** If `portal_available` is false, continue without MCP verification and the hosted target, and say so in the final report.
3. Read [orchestration](references/orchestration.md): workspace layout, stage markers, retries, resume.
4. Run the stages below in order. Load each stage prompt only when you reach it. Never skip the decision stage.

## Workflow

| Stage | Prompt | Who | Gate | Marker |
| --- | --- | --- | --- | --- |
| 0 Bootstrap | (above) | scripts | `.d2a/env.json` exists, `check_env.json → ok` | `bootstrap_done` |
| 1 Ingest | [ingest](references/prompts/ingest.md) | scripts | `probe.py` wrote `work/inventory.json` with a recognised kind | `ingest_done` |
| 2 Assess | [assess](references/prompts/assess.md) | you + preview build | `reports/assessment.md` written, preview opened or screenshotted | `assess_done` |
| ★ Decision | [assess](references/prompts/assess.md#decision) | user | `work/decision.json` exists and validates | `decision_done` |
| 3 Curate | [curate](references/prompts/curate.md) | you (LLM) | `apply_curation.py` + `validate_package.py` pass; ontology ids verified | `curate_done` |
| 4 Build | [build](references/prompts/build.md) | scripts | `validate_package.py` exit 0; portal rendered for the chosen target | `build_done` |
| 5 Verify | [verify](references/prompts/verify.md) | fresh verifier agent | acceptance cases pass via `verify_mcp_server.py` (+ `/api` for hosted); checklist ticked | `verify_done` |
| 6 Deliver | [deliver](references/prompts/deliver.md) | you + delivery check | zip opens elsewhere, USAGE.md accurate, hashes recorded | `deliver_done` |
| 7 Deploy | [deploy](references/prompts/deploy.md) | you (scripts) | hosted: `portal` installed on the target by `deploy_hosted.sh`, `api/obs/count` answers; static: published per USAGE | `deploy_done` |

## Essential rules

- **Never invent data.** Every column, value, ontology id, citation and number in the portal traces to a source file, a controlled vocabulary lookup, or the paper. Unmappable annotations stay as free text in `extra`, they are not guessed. Missing information is stated as missing.
- **Scientific computation stays in domain tools** (anndata, scanpy, pydeseq2, minfi...). Adapters move data into the contract; they do not re-analyse. A recomputed result (e.g. a DESeq2 contrast when the authors shipped none) is labelled "recomputed" in its table label and description.
- **The contract is the boundary.** Adapters may be any language; `validate_package.py` is the only acceptance test for a package. The portal layer reads nothing but `manifest.json` and parquet.
- **You install the server, not the user.** For the hosted target, stage 7 installs `portal` and runs the service on the machine the user names (local, ssh, Docker). Users supply data and a destination; nothing else.
- **Decision before build.** Target (static / hosted) and tier come from the user after reading the assessment. Changing them later only reruns stages 4 to 6.
- **Verifier independence.** Stage 5 is a fresh agent that was not the curator; it derives expected values from raw files, not from the package.
- **Honest completion.** Markers are written only after their gate passes. Report blocked or degraded parts explicitly; never relax a check to pass.

## Helpers (all under `scripts/`)

| Script | Does |
| --- | --- |
| `bootstrap.sh` | Stage 0: uv → isolated venv from `requirements.txt` → `check_env.py` → locate/download/build `portal` → `.d2a/env.json` |
| `fetch_geo.py` | Download series matrix + supplementary files for a GSE, record `work/sources.json` with sizes and SHA-256 |
| `geo_series_matrix.py` | Series matrix -> `work/samples.csv` (+ `series.json`) |
| `probe.py` | Sniff files -> `work/inventory.json`: kind, shapes, candidate id/annotation columns, size tier suggestion, adapter suggestion |
| `adapters/<kind>_<lang>/run.py` | Source files -> contract package (`pkg/`) |
| `apply_curation.py` | Apply `work/curation.json` (labels, roles, ontology terms, dataset text) to `pkg/`; re-finalise hashes; `--check-ontology` verifies ids against OLS4 |
| `validate_package.py` | Contract gate (schema, hashes, ids, sortedness, foreign keys) |
| `build_portal.py` | Render pages + assets for `--target static|hosted` (`--preview-note` for previews) |
| `verify_mcp_server.py` | Real stdio MCP handshake + acceptance cases against `portal mcp <pkg>` |
| `install_portal.sh` | Download the `portal` binary for this OS/arch from GitHub Releases (checksum-verified, no sudo) |
| `deploy_hosted.sh` | Hosted deploy: `--local` / `--remote user@host` / `--docker`; installs `portal` on the target, places the package, runs it as a service |

Reference material: [core schemas](references/core-schemas.md), [curation rules](references/curation.md), [paper extraction](references/paper-extraction.md), [assessment template](references/assessment.md), [quality checklist](references/quality-checklist.md), [acceptance cases](references/acceptance.md).

## Final response

Lead with the delivered path (`dist/<id>-portal.zip` or the served URL), then: target and tier, pages delivered, validation scope (what was checked and what was not), ontology mapping coverage, and remaining limits. Keep working evidence in `reports/`; do not paste it.
