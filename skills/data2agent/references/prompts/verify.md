# Verify the scientific release

For a new data release, use a fresh verifier that did not curate it. Give it the project, original inputs, decisions, methods, serving address and actual interface commands, plus [acceptance](../acceptance.md). Do not give it the built tables as its source of expected values.

The verifier should:

1. Derive representative expected dimensions, labels, values, boundaries and failure cases directly from original inputs, with independently implemented arithmetic where relevant.
2. Exercise the actual HTTP/MCP/CLI interfaces supplied by this project. The bundled `verify_mcp_server.py` can run JSON acceptance cases against a custom stdio command; pass `--require-tools` for the domain's actual tool names. No Go binary is required for a Python MCP server. Do not test nonexistent SQL or force matrix tools on a genome API.
3. Check browser interactions, empty/error states, desktop/mobile layout and downloads for the implemented application, or record that the coordinator performed these checks separately.
4. Inspect source/artifact hashes, provenance and update invalidation. Check an independent extraction/working directory for a portable delivery.
5. Return evidence and precise failures without editing data/application artifacts. Numerical tolerances must follow representation/rounding, not be adjusted to conceal a data error.

The coordinator fixes defects and reruns affected checks. Unchanged passing checks need not be repeatedly broadened. Record independent versus self-verification and any unavailable environment checks accurately. Use [quality checklist](../quality-checklist.md) only for applicable capabilities; do not mark unimplemented or untested features as passed.
