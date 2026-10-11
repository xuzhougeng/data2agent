# Stage 6 — Deliver

Goal: a zip that works somewhere else, an accurate `USAGE.md`, recorded hashes.

1. `pkg/USAGE.md` was rendered by `build_portal.py`; read it once and correct anything that does not match this dataset or target (ports, binary name, object-storage URL).
2. Package:
   ```bash
   mkdir -p dist && rm -f "dist/<id>-portal.zip"
   (cd pkg && zip -qr "../dist/<id>-portal.zip" . -x "portal.json" "*.DS_Store")
   sha256sum "dist/<id>-portal.zip" > "dist/<id>-portal.zip.sha256"
   ```
   Keep `reports/`, `work/`, `preview/` out of the zip.
3. Relocation check (independent agent when available): extract the zip into a new temporary directory, serve it (`python3 -m http.server` or `portal serve`), open the Home page, and rerun `verify_mcp_server.py` against the extracted copy with the same cases. Record in `reports/delivery.json`: zip path, SHA-256, extraction path, outcomes.
4. Publishing / running it somewhere is stage 7 ([deploy](deploy.md)): static → GitHub Pages / Cloudflare Pages per USAGE; hosted → `deploy_hosted.sh` installs `portal` on the target. Zenodo DOI only when asked. Registering a DOI: upload the zip, write the DOI into `pkg/manifest.json → doi`, rebuild, re-zip, and note that the data hashes are now locked.
5. Write `.pipeline/deliver_done` after step 3 passes.

Final message: lead with the zip path (and URL if served), then target/tier, pages, validation scope, ontology coverage, limits. Point to `reports/` for evidence instead of pasting it.
