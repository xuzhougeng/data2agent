# Acceptance from original evidence

The verifier proves that the scientific queries and application agree with the source, not merely that files exist. Derive expected values from original inputs and documented transforms, independently of built tables and implementation constants.

## Select checks for the actual domain

| Capability | Examples of independent evidence |
| --- | --- |
| Study/catalog coverage | Original repository records, inclusion rules, duplicate/reanalysis relationships, catalog-only versus queryable status |
| Matrix observations/features | Original axis IDs and dimensions, unique sparse coordinates, matched annotations, namespaced cell/sample identities |
| Expression summaries | Recomputed representative values and group sizes, zero-expression denominator, normalized versus raw units, not-measured genes |
| Genome annotation | FASTA contig lengths, GFF relationships, assembly agreement, interval boundaries and strand-correct subsequences |
| Signal/peak access | Source intervals/values, coordinate conventions, summary resolution, signal units and missingness |
| Identifier resolution | Source names and aliases; ambiguity and unknown IDs handled without selecting a wrong entity silently |
| Serving interfaces | Real HTTP/MCP/CLI calls for the named queries, missing/invalid requests, implemented resource/write boundaries |
| Updates and delivery | Changed-input invalidation, intact-output reuse, independently extracted startup, valid downloads/indexes |

Choose informative cases, including a boundary/zero/missing value and a substantive metadata join. Hashes and structural validation complement these checks, not replace them. Numerical tolerances must reflect documented arithmetic/storage precision; do not compare independently rounded values at an unstable boundary or widen tolerance to hide a semantic error.

## Stdio MCP helper

For a server that actually implements MCP, the bundled verifier supports JSON cases:

```json
[
  {"name":"known identifier", "tool":"lookup_gene", "arguments":{"id":"source-gene-id"}, "expect_json_subset":{"id":"source-gene-id"}},
  {"name":"unknown identifier", "tool":"lookup_gene", "arguments":{"id":"missing-id"}, "expect_error":true}
]
```

Replace example tools/IDs and expected behavior with the project's interface and raw-derived facts. An interface may return a documented empty result rather than an error; test its contract.

```sh
"$PY" "$SKILL_ROOT/scripts/verify_mcp_server.py" \
  --server-argv "[\"$PY\", \"-m\", \"app.mcp\"]" --cwd "$PROJECT_ROOT" \
  --require-tools lookup_gene,region_annotations \
  --cases "$PROJECT_ROOT/reports/acceptance-cases.json" \
  --report "$PROJECT_ROOT/reports/mcp-verify.json"
```

`--server-argv` takes a JSON array so a `PROJECT_ROOT` containing spaces is not split. `--require-tools` has no default; use `describe_tables,sql,search_features,get_obs,feature_summary` for the bundled Go dataset portal. A genome service need not expose matrix tools or SQL. MCP inventory/handshake without substantive cases is a smoke check, not scientific acceptance. HTTP verification should exercise equivalent domain queries with a project-specific verifier. Do not silently skip a required interface because the bundled Go executable is absent.

## Browser and deployment

Exercise every implemented primary user task against a real server: navigation, representative query, filters, empty/unknown state, plot units/legends, downloads and mobile layout. Distinguish author and recomputed content in what users actually see. Check relevant console/network errors; an intentionally handled negative-request response is not an unhandled application error.

For delivery, inspect a copy/extraction outside the original working directory. Start its actual server and query actual data. Validate Range responses or data indexes if relevant. Report whether verification used the same runtime/OS, native execution, a container, or a public endpoint. Do not infer an untested deployment method from another one.

The verifier writes evidence and precise failures, without modifying the release artifacts. The coordinator repairs and reruns affected checks. Record unavailable independence/browser/container/remote checks and their limits; do not downgrade a required scientific failure into a passing marker.
