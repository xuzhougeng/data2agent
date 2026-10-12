#!/usr/bin/env python
"""Download a GEO series' matrix file(s) and supplementary files; record provenance.

usage: fetch_geo.py GSE60450 --out raw [--sources work/sources.json] [--pattern REGEX] [--max-mb 2000] [--no-suppl]
       fetch_geo.py --add path/to/local/file --sources work/sources.json     # register a user-supplied file

sources.json: [{"name", "url", "path", "bytes", "sha256", "downloaded": bool, "note"}]
Pure stdlib; honours http(s)_proxy env vars. Retries 3x per file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

UA = {"User-Agent": "data2agent/0.1 (+https://github.com/xuzhougeng/data2agent)"}


def series_dir(gse: str) -> str:
    stem = gse[:-3] + "nnn"
    return f"https://ftp.ncbi.nlm.nih.gov/geo/series/{stem}/{gse}"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v and not v.startswith(("?", "/", "../", "http://", "https://", "ftp://", "mailto:")):
                    self.hrefs.append(v)


def listing(url: str) -> list[str]:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                p = Links()
                p.feed(r.read().decode("utf-8", "replace"))
                return p.hrefs
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                print(f"listing failed {url}: {e}", file=sys.stderr)
                return []
            time.sleep(2 * (attempt + 1))
    return []


def head_size(url: str) -> int | None:
    try:
        req = urllib.request.Request(url, headers=UA, method="HEAD")
        with urllib.request.urlopen(req, timeout=60) as r:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl else None
    except Exception:  # noqa: BLE001
        return None


def download(url: str, dest: Path) -> tuple[int, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(3):
        try:
            h = hashlib.sha256()
            n = 0
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    n += len(chunk)
            tmp.replace(dest)
            return n, h.hexdigest()
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise
            print(f"retry {attempt + 1} for {url}: {e}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_sources(path: Path | None) -> list[dict]:
    if not (path and path.exists()):
        return []
    items = json.loads(path.read_text())
    for i in items:  # records written by fetch_sources.py carry id/status instead of name/downloaded
        i.setdefault("name", i.get("id") or Path(i.get("path") or "").name)
        i.setdefault("downloaded", i.get("status") in {"acquired", "downloaded"})
    return items


def save_sources(path: Path | None, items: list[dict]):
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("accession", nargs="?", help="GSE accession")
    ap.add_argument("--out", type=Path, default=Path("raw"))
    ap.add_argument("--sources", type=Path, default=Path("work/sources.json"))
    ap.add_argument("--pattern", help="regex; only supplementary files whose name matches are downloaded")
    ap.add_argument("--max-mb", type=float, default=2000, help="larger supplementary files are listed, not downloaded")
    ap.add_argument("--no-suppl", action="store_true")
    ap.add_argument("--add", type=Path, action="append", default=[], help="register a local file (copied into --out)")
    a = ap.parse_args()

    items = load_sources(a.sources)
    known = {i["name"] for i in items}

    for p in a.add:
        dest = a.out / p.name
        if p.resolve() != dest.resolve():
            a.out.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        rec = {"name": p.name, "url": None, "path": str(dest), "bytes": dest.stat().st_size, "sha256": sha256_file(dest), "downloaded": True, "note": "user-supplied"}
        items = [i for i in items if i["name"] != p.name] + [rec]
        print(json.dumps(rec))

    if a.accession:
        gse = a.accession.upper()
        if not re.fullmatch(r"GSE\d+", gse):
            sys.exit("accession must look like GSE12345")
        base = series_dir(gse)
        for name in listing(base + "/matrix/"):
            if not name.endswith("_series_matrix.txt.gz"):
                continue
            url = base + "/matrix/" + name
            dest = a.out / name
            n, sha = download(url, dest)
            rec = {"name": name, "url": url, "path": str(dest), "bytes": n, "sha256": sha, "downloaded": True, "note": "series matrix"}
            items = [i for i in items if i["name"] != name] + [rec]
            print(json.dumps(rec))
        if not a.no_suppl:
            for name in listing(base + "/suppl/"):
                if name.endswith("/") or name in known:
                    continue
                url = base + "/suppl/" + name
                if a.pattern and not re.search(a.pattern, name):
                    items.append({"name": name, "url": url, "path": None, "bytes": head_size(url), "sha256": None, "downloaded": False, "note": "skipped by --pattern"})
                    continue
                size = head_size(url)
                if size and size > a.max_mb * 1024 * 1024:
                    rec = {"name": name, "url": url, "path": None, "bytes": size, "sha256": None, "downloaded": False, "note": f"larger than --max-mb {a.max_mb}; download on request"}
                else:
                    dest = a.out / name
                    try:
                        n, sha = download(url, dest)
                        rec = {"name": name, "url": url, "path": str(dest), "bytes": n, "sha256": sha, "downloaded": True, "note": "supplementary"}
                    except Exception as e:  # noqa: BLE001
                        rec = {"name": name, "url": url, "path": None, "bytes": size, "sha256": None, "downloaded": False, "note": f"download failed: {e}"}
                items = [i for i in items if i["name"] != name] + [rec]
                print(json.dumps(rec))
        # series-level page for humans
        items = [i for i in items if i["name"] != "_geo_page"] + [{"name": "_geo_page", "url": f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse}", "path": None, "bytes": None, "sha256": None, "downloaded": False, "note": "GEO record"}]

    save_sources(a.sources, items)
    print(json.dumps({"files": len([i for i in items if i["downloaded"]]), "listed_only": len([i for i in items if not i["downloaded"]]), "sources": str(a.sources)}), file=sys.stderr)


if __name__ == "__main__":
    main()
