# Stage 4 — Build

Goal: `pkg/` is a complete portal for the decided target.

```bash
# static (tiers S, M)
"$PY" "$SKILL_ROOT/scripts/build_portal.py" pkg --target static --data-base-url "<from decision: data/ or object-storage URL>"

# hosted (tiers L, XL)
"$PY" "$SKILL_ROOT/scripts/build_portal.py" pkg --target hosted --api-base-url "<from decision: api>"
cp "$PORTAL" pkg/portal        # ship the binary next to the data when the user wants a single directory
```

Then:
1. `"$PY" "$SKILL_ROOT/scripts/validate_package.py" pkg` must still pass (build adds HTML/assets only; data hashes unchanged).
2. Tier M: upload `pkg/data/` to the object storage named in the decision, confirm CORS + HTTP Range work (`curl -I -H "Range: bytes=0-99" <url>` returns 206), and keep `data_base_url` pointing there.
3. Stop the preview server; serve the real build: static → `python3 -m http.server 8082` in `pkg/`; hosted → `"$PORTAL" serve pkg --addr 127.0.0.1:8082`.
4. Record the manifest hash in `.pipeline/workflow.json`; write `.pipeline/build_done`.

If the user changes the decision later, rerun only this stage and the two after it.
