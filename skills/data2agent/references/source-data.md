# Source data and supplementary workbooks

Journals ship the numbers behind figure panels as workbooks (Nature "Source Data": one file per figure, one sheet per
panel; Supplementary Tables S1…; sometimes a statistics workbook with one block per panel). The layouts are made for
humans: title rows, merged headers, labels filled down only on the first row, two tables side by side, several blocks
down one sheet, replicate values across columns. No heuristic reshapes them reliably. **You do the reading; the
adapter does the reshaping.** Values are never recomputed: every number in a panel parquet is a workbook cell.

## Workflow

```bash
"$PY" "$SKILL_ROOT/adapters/source_data_py/run.py" probe raw/ --out work/source_data.draft.json
#   -> every sheet with its shape, a 6-row preview and a guessed recipe (layout, skip_rows, label columns)
#   read it; write work/source_data.json (start from the draft, see below)
"$PY" "$SKILL_ROOT/adapters/source_data_py/run.py" apply pkg work/source_data.json --init --id <id> --title "..."
#   --init creates a figures-only package when there is no omics matrix; without --init it adds to an existing pkg
"$PY" "$SKILL_ROOT/scripts/validate_package.py" pkg && "$PY" "$SKILL_ROOT/scripts/build_portal.py" pkg
```

`apply` prints, per panel, the tidy columns and row count and lists panels that failed (exit 1). Open the portal,
look at every panel type once, fix the recipe, re-run with `--replace`. Three rounds are normal.

## Writing the recipe (what the agent decides)

1. **Which workbook is which figure.** File names such as `MOESM13_ESM.xlsx` say nothing; sheet names (`Fig.1c`),
   the statistics workbook's block titles (`Extended Data Fig.1a-PXO99A`) and the paper's figure legends do. Sheets
   named `Fig.1a` inside the *Extended Data* workbook are `edfig1_1a`, not `fig1_1a`.
2. **What each label column means.** `Repeat 1-Shanghai_2021 | SKZ | 0.5 | …` is `repeat, genotype`; `PXO61 | Repeat 1 | Xa21 | …`
   is `strain, repeat, genotype`; `SKZ | Repeat 1 | PXO99A | …` is `genotype, repeat, strain`. Name them with the
   paper's vocabulary (genotype, strain, treatment, tissue, construct, condition, site, year, block, plant), never
   `label1`. Use `split` to derive `repeat_no / site / year` from `Repeat 1-Shanghai_2021`.
3. **The measured variable and its unit**, from the sheet title or the legend (`lesion_length`, cm). When the sheet
   does not say the unit, leave it out; do not guess.
4. **Blocks.** Two tables side by side → two panels with `cols`; several repeats stacked → `wide_rows` with the repeat
   as a label column; a statistics workbook → `layout: stacked` (blocks are split on their title rows and attached as
   `related` to the data panel with the same figure/panel letters). The right-hand block of a side-by-side sheet has no
   title row, so its `skip_rows` is usually one less.
5. **Chart.** `strip` (points + mean bar) when ≤ 40 values per group, `box` above that; `line` for time/voltage series
   (`x` numeric, `color` = condition); `scatter` for two measured variables; `table` for statistics and lists.
   `facet` = the variable the paper shows as separate panels or repeats (repeat, site_year); `color` = the variable it
   shows as colour/legend. The Figures page offers a selector per facet value and prints n per group.
6. **Captions.** One sentence per panel in the legend's words; one sentence per figure for the Home page. The text found
   above a table is kept as `sheet_caption`.
7. **Skip** duplicate downloads (`… (2).xlsx`) and empty sheets with `"skip": true`.

Shared recipes go under `layouts` and panels reference them with `like`; per-panel keys override. A worked example for a
Nature paper with 25 workbooks (lesion assays, bacterial counts, field trials, electrophysiology traces, qPCR, a
statistics workbook and Tables S1–S8) is `references/examples/source-data.xa48.json`.

## Recipe keys

| key | meaning |
| --- | --- |
| `file`, `sheet` | workbook (relative to `source_dir`) and sheet |
| `skip_rows` | title rows above the table; their text becomes `sheet_caption` |
| `rows`, `cols` | `[start, end]` 0-based, end exclusive, `null` = open; cut one block |
| `layout` | `wide_rows` · `grouped_columns` · `columns` · `long` · `table` · `stacked` |
| `labels`, `ffill` | wide_rows: names of the leading label columns; which to fill down |
| `header_row`, `sub_header`, `index`, `group` | header position; second header row; name of the first (x) column; name of the group variable |
| `melt` | long: `{"pattern" \| "columns", "name", "value"}` wide measurement columns → rows |
| `value`, `unit` | name of the measured variable (default `value`) and its unit |
| `split` | `{"col": {"pattern": regex, "into": [names]}}` derive columns from a label |
| `rename`, `drop` | after tidying (long/table/stacked: rename applies before `ffill`/`melt`) |
| `caption`, `chart`, `related`, `feature_col`, `features`, `image` | presentation; `chart` = `{type, x, y, color, facet, value_label}` |
| `block_pattern` | stacked: regex that starts a block (default `^(Extended Data \|ED )?Fig`) |

## Quality checks before delivery

- Every panel of every figure in the paper is present or listed as missing in the report, with the reason.
- n per group on the Figures page matches the legend (the page prints it under the chart).
- A value spot-checked in the workbook equals the value in the panel table (pick one per layout type).
- Statistics blocks appear under their data panels; orphan blocks are listed in the report.
- Captions are the legend's sentences, not restatements of the chart.
