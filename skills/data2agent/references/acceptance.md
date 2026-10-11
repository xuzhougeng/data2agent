# Acceptance cases (stage 5)

The verifier proves the package says what the raw data says. Expected values are computed **from `raw/`** (the original matrix, sample sheet, h5ad, DE tables), never read back from `pkg/`. The cases then run through the real interfaces: `portal mcp` over stdio, and for hosted targets the HTTP API.

## File: `reports/acceptance-cases.json`

Same shape as `scripts/verify_mcp_server.py` expects (see `references/examples/mcp-cases.*.json`):

```json
[{"name": "cells per group", "tool": "sql",
  "arguments": {"query": "select louvain, count(*) as n from obs group by 1 order by n desc limit 1"},
  "expect_json_subset": {"rows": [{"louvain": "CD4 T cells", "n": 1144}]}}]
```

Checks available: `expect_json_subset` (recursive; arrays are prefix, element-wise subsets), `expect_contains`, `expect_error: true`.

## Minimum set (add more when the dataset offers more)

| # | Case | Expected value derived from |
| --- | --- | --- |
| 1 | `describe_tables` returns the dataset id and `stats.n_obs`, `stats.n_features` | count rows in the raw matrix / h5ad |
| 2 | `sql`: count of observations per primary group, top group | raw sample sheet / `obs` of the h5ad |
| 3 | `sql`: mean display value of one feature in one group (round to 2–3 decimals) | recompute from the raw matrix with the same transform the adapter documents (e.g. log2 CPM) |
| 4 | `search_features` resolves a symbol to the expected feature id | raw feature annotation |
| 5 | `get_obs` for one id returns its raw annotations | raw sample sheet / obs |
| 6 | `sql` write statement is rejected (`expect_error: true`) | — |
| 7 | `feature_summary` of a feature lists the expected hit in each result table (rank / contrast / sign of effect) | raw DE / marker table |
| 8 | (embeddings) `sql` count of rows in `emb_<name>` equals `n_obs` | — |
| 9 | (matrix) `sql` count of non-zero entries equals the manifest `nnz` and the raw matrix's non-zero count | raw matrix |

Choose features and ids that are informative (a known marker, a sample with distinctive metadata), not the first row.

## Running

```bash
"$PY" "$SKILL_ROOT/scripts/verify_mcp_server.py" --server "$PORTAL mcp pkg" \
  --cases reports/acceptance-cases.json --report reports/mcp-verify.json
```

Hosted target, additionally start `"$PORTAL" serve pkg --addr 127.0.0.1:8099` and run every `sql` case through `POST /api/sql` (`curl -s -X POST http://127.0.0.1:8099/api/sql -d '{"query": "..."}'`), comparing the same expectations; record the outcomes in `reports/api-verify.json`.

## Browser checks

Open every page with the host's browser tool (or Playwright) against `python3 -m http.server` on `pkg/` (static) or `portal serve` (hosted). Record console errors and one screenshot per page in `reports/screenshots/`. Tick [quality-checklist.md](quality-checklist.md) into `reports/checklist.md`.

## Reporting

Return: cases passed/failed with reasons, checklist items left open, console errors, and which checks could not be run (no browser, no `portal` binary). Never edit `pkg/` to make a case pass; send failures back to the coordinator.
