# Stage 5 — Verify (fresh agent)

You are the verifier. You did not curate this package and you must not edit `pkg/`. Inputs: `PROJECT_ROOT`, `SKILL_ROOT`, `PY`, `PORTAL`, `work/decision.json`, the list of raw files, [acceptance.md](../acceptance.md), [quality-checklist.md](../quality-checklist.md).

1. Derive expected values from `raw/` (the original matrix / h5ad / sample sheet / DE tables), using the transforms documented in `pkg/manifest.json → methods`. Write `reports/acceptance-cases.json` with at least the minimum set.
2. Run:
   ```bash
   "$PY" "$SKILL_ROOT/scripts/verify_mcp_server.py" --server "$PORTAL mcp pkg" --cases reports/acceptance-cases.json --report reports/mcp-verify.json
   ```
   Hosted: also run the `sql` cases through `POST /api/sql` on the running server and save `reports/api-verify.json`.
3. Browser pass: open every page, one screenshot each into `reports/screenshots/`, collect console errors, try an empty filter result and an unknown feature id, check 375 px width and dark mode.
4. Fill `reports/checklist.md` from the quality checklist with `[x]`, `[ ] reason`, or `n/a`.
5. Return to the coordinator: pass/fail per case, open checklist items, console errors, and anything you could not check. The coordinator fixes and reruns Build; you rerun the failed cases (max 6 rounds per case).

Gate for `.pipeline/verify_done` (written by the coordinator): `mcp-verify.json → ok: true`, no open checklist item without an accepted reason, zero console errors.
