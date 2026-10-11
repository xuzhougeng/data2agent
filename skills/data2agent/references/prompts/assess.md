# Stage 2 — Assess, preview, decision

Goal: `reports/assessment.md`, a running preview, and `work/decision.json` written from the user's answer.

## Preview build (mechanical, uncurated)

Run the suggested adapter on the raw files with minimal arguments to get a first package, then a preview site. For scRNA with more than 5,000 cells, subsample first (`--subsample 2000` on `scrna_py`) so the preview builds in seconds.

```bash
"$PY" "$SKILL_ROOT/adapters/bulk_rna_py/run.py" preview/pkg --counts raw/<counts> --samples work/samples.csv \
      --sample-key <column matching count headers> --id <GSE> --title "<series title>" --group <best group column>
"$PY" "$SKILL_ROOT/scripts/validate_package.py" preview/pkg
"$PY" "$SKILL_ROOT/scripts/build_portal.py" preview/pkg --target static --preview-note "Preview build: uncurated labels, subsampled data; numbers are not final"
(cd preview/pkg && python3 -m http.server 8081 >/dev/null 2>&1 &)
```

Open http://localhost:8081/ with the host's browser tool; take screenshots of Home, Samples/Cells, Feature (use `portal.json → example_feature`) into `reports/screenshots/preview-*.png`. If no browser is available, say so in the report.

## Report

Write `reports/assessment.md` following [assessment.md](../assessment.md): data profile (numbers from `inventory.json` and the preview manifest), pages possible, recommended target with reasons, costs, preview location, open questions. Note which annotations will need curation (raw column names, free-text values, missing group column).

## Decision

Ask the user (AskUserQuestion in Claude Code: options "static (recommended)" / "hosted", plus any open question). Write `work/decision.json` exactly as specified, with `decided_by: "user"`. If the user answers in prose, transcribe it faithfully; do not decide for them. Write `.pipeline/assess_done` and `.pipeline/decision_done`.

Keep the preview server running until Build replaces it, or stop it with `fuser -k 8081/tcp`.
