# Assessment report and decision (stage 2)

The assessment is the one document the user reads before committing. Write `reports/assessment.md` from `work/inventory.json` (probe output) and a preview build. Keep it under one screen; numbers come from the inventory, not from memory.

## Template

```markdown
# Assessment: <dataset id>

## Data profile
- Kind: scrna | bulk_rna | proteomics | … (confidence: high/medium/low, why); modalities when more than one (RNA + proteomics over the same N samples → multi-omics package)
- Source data: N figure workbooks / N panels found (or none)
- Observations: N <cells/samples>; features: N <genes/probes>; matrix non-zeros: N; value type: counts / lognorm / …
- Annotations found: <columns> (which look like group / condition / tissue); missing: <what a typical portal would want>
- Embeddings: present/absent (which); result tables: present/absent (which, how many rows)
- Files: total MB; largest file; data tier inputs: meta_mb=…, matrix_mb=…

## Pages this portal can offer
| Page | Status | Note |
| Home / Samples(Cells) / Map / Features (per modality) / Results / Figures / Download / API / Help | ready | needs: … | not possible: … |

## Recommended target
**static (tier S)** — reasons (2–3 bullets drawn from the table below)
Alternative: hosted (tier L) if … 

## Costs and operations
- static: push to GitHub Pages / any static host; zero running cost
- hosted: `portal serve` on a VM with ≥ N GB RAM, or `docker compose up`; needs a domain + reverse proxy

## Preview
- Local preview: http://localhost:8081/ (built from a subsample of N observations; numbers are not final)
- Screenshots: reports/screenshots/preview-*.png

## Open questions for you
1. … (only questions that change the build)
```

## Tier scoring (from probe.py)

| Signal | static S | static+object storage M | hosted L | hosted XL |
| --- | --- | --- | --- | --- |
| total package size | < 200 MB | matrix 200 MB – 5 GB, meta < 200 MB | > 5 GB or many concurrent users | — |
| updates | locked at publication | locked | occasional rebuilds | continuous ingest (phase 2) |
| access | public | public | public or behind a proxy | accounts / controlled access |
| server-side needs | none | none | SQL over large matrices without downloading | writes (submissions, comments) |

`probe.py` prints `tier_suggestion` with the sizes behind it. You may override with reasons.

## Decision

Ask the user with the host's question mechanism (AskUserQuestion in Claude Code; a plain question in Codex). Offer exactly: `static` (recommended or not) and `hosted`, plus any open question from the report. Then write `work/decision.json`:

```json
{"target": "static", "tier": "S", "data_base_url": "data/", "api_base_url": "api",
 "pages": {"results": true, "embedding": true}, "doi": false,
 "decided_by": "user", "decided_at": "2026-10-11T12:00:00Z", "notes": "…"}
```

`target` ∈ {static, hosted}; `tier` ∈ {S, M, L, XL}; for M set `data_base_url` to the object-storage URL; for hosted set `api_base_url` (relative `api` unless proxied elsewhere). No decision file, no build.
