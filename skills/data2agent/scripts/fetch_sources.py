#!/usr/bin/env python
"""Acquire an explicit source plan with checked, resumable provenance.

Usage: python fetch_sources.py --project PATH --plan source-plan.json
Plans are lists of {id, path, url|local_path, [sha256], [bytes], ...metadata}.
`name` is accepted as shorthand for raw/<name>; old AraCell plans are readable.
Existing unrecorded destinations are refused. --refresh re-fetches changed
sources only when their pinned checksum still matches; updating that pin is an
explicit source-plan revision. Replaced files are retained under raw/.history/.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import json
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

from project_io import append_event, atomic_json, now, project_lock, project_path, sha256


def normalize(plan, root):
    rows = plan.get('sources', []) if isinstance(plan, dict) else plan
    if not isinstance(rows, list) or not rows:
        raise ValueError('Source plan must contain at least one source')
    normalized, ids, destinations = [], set(), set()
    for source in rows:
        row = dict(source)
        row.setdefault('id', row.get('name') or row.get('path'))
        row.setdefault('path', 'raw/' + row.get('name', ''))
        if not isinstance(row['id'], str) or not row['id'] or row['id'] in ids:
            raise ValueError('Source IDs must be nonempty and unique')
        destination = project_path(root, row['path'])
        parts = Path(row['path']).parts
        if len(parts) < 2 or parts[0] != 'raw' or parts[1] == '.history':
            raise ValueError('Downloaded inputs belong under raw/')
        if destination.relative_to(root.resolve()).parts[0] != 'raw':
            raise ValueError('A source symlink may not redirect writes outside raw/')
        if any(destination == p or destination in p.parents or p in destination.parents for p in destinations):
            raise ValueError('Source paths collide: ' + row['path'])
        if bool(row.get('url')) == bool(row.get('local_path')):
            raise ValueError('Each source requires exactly one of url or local_path')
        if row.get('url'):
            url = urllib.parse.urlsplit(row['url'])
            if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
                raise ValueError('Use a public HTTP(S) URL without embedded credentials')
        if 'sha256' in row and not re.fullmatch('[0-9a-f]{64}', str(row['sha256'])):
            raise ValueError('Expected sha256 must be 64 lowercase hexadecimal characters')
        if 'bytes' in row and (not isinstance(row['bytes'], int) or row['bytes'] < 0):
            raise ValueError('Expected bytes must be a nonnegative integer')
        ids.add(row['id']); destinations.add(destination); normalized.append(row)
    return normalized


def acquire(root, item, old, refresh=False, max_bytes=None):
    dest = project_path(root, item['path'])
    identity = {k: item.get(k) for k in ('path','url','local_path')}
    current = None
    if dest.exists():
        # fetch_geo.py records listed-only files with sha256=None; those are not acquisitions.
        if not old or not old.get('sha256'):
            raise ValueError(f"Unrecorded destination exists: {item['path']}; register its source explicitly or use a new destination")
        current = sha256(dest)
        if dest.stat().st_size != old['bytes'] or current != old['sha256']:
            if not refresh:
                raise ValueError('Previously recorded input was modified: ' + item['path'] + '; use --refresh to re-fetch it (current bytes are kept under raw/.history/)')
        elif not refresh:
            if any(old.get(k) != v for k, v in identity.items()):
                raise ValueError('Source identity changed; use a new source ID/path or --refresh')
            if item.get('sha256', old['sha256']) != old['sha256'] or item.get('bytes', old['bytes']) != old['bytes']:
                raise ValueError('Source pin changed; use --refresh or a versioned destination')
            # Keep the scientific receipt stable on reuse; verification timestamps
            # belong in the event log, otherwise downstream hashes change on every run.
            return {**old, **{k:v for k,v in item.items() if k not in {'bytes','sha256'}}}, 'reused'
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name('.' + dest.name + '.download')
    try:
        for attempt in range(3):
            try:
                if item.get('url'):
                    request = urllib.request.Request(item['url'], headers={'User-Agent':'Data2Agent/0.2 (research source acquisition)'})
                    source = urllib.request.urlopen(request, timeout=60)
                else:
                    src = Path(item['local_path']).expanduser()
                    if not src.is_absolute():
                        src = root / src
                    source = src.open('rb')
                with source, temporary.open('wb') as output:
                    length = source.headers.get('Content-Length') if hasattr(source, 'headers') else None
                    if max_bytes is not None and length and int(length) > max_bytes:
                        raise ValueError('Source exceeds --max-bytes: ' + item['id'])
                    total = 0
                    while block := source.read(1 << 20):
                        total += len(block)
                        if max_bytes is not None and total > max_bytes:
                            raise ValueError('Source exceeds --max-bytes: ' + item['id'])
                        output.write(block)
                if length and total != int(length):
                    raise IOError('Incomplete HTTP response')
                break
            except ValueError:
                raise
            except urllib.error.HTTPError as error:
                if 400 <= error.code < 500 or attempt == 2:
                    raise
                time.sleep(attempt + 1)
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
        digest, size = sha256(temporary), temporary.stat().st_size
        if item.get('sha256', digest) != digest or item.get('bytes', size) != size:
            raise ValueError('Downloaded bytes do not match source-plan pin: ' + item['id'])
        if dest.name.endswith('.gz'):
            with gzip.open(temporary, 'rb') as stream:
                while stream.read(1 << 20):
                    pass
        if dest.exists():
            backup = project_path(root, 'raw/.history/' + current + '/' + dest.name)
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copy2(dest, backup)
        temporary.replace(dest)
        return {**item, 'bytes':size, 'sha256':digest, 'status':'acquired', 'retrieved_at':now()}, 'acquired'
    finally:
        temporary.unlink(missing_ok=True)


def run(root, plan_path, workers=3, refresh=False, max_bytes=None):
    root = Path(root).resolve()
    rows = normalize(json.loads(Path(plan_path).read_text()), root)
    receipts_path = project_path(root, 'work/sources.json')
    with project_lock(root, 'sources'):
        existing = json.loads(receipts_path.read_text()) if receipts_path.exists() else []
        known = {x.get('id', x.get('name')):x for x in existing}
        # A different ID may not adopt a previously recorded destination.
        owner = {x['path']:key for key,x in known.items()}
        if any(s['path'] in owner and owner[s['path']] != s['id'] for s in rows):
            raise ValueError('A source destination already belongs to a different source ID')
        failures = []
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
            pending = {pool.submit(acquire, root, s, known.get(s['id']), refresh, max_bytes):s for s in rows}
            for future in as_completed(pending):
                source = pending[future]
                try:
                    record, operation = future.result()
                    known[source['id']] = record
                    atomic_json(receipts_path, list(known.values()))
                    append_event(project_path(root, '.pipeline/sources.jsonl'), {**record,'operation':operation,'verified_at':now()})
                    print(json.dumps({'id':source['id'],'status':operation,'bytes':record['bytes']}), flush=True)
                except Exception as error:
                    failure = {'id':source['id'],'error':str(error)}
                    failures.append(failure)
                    append_event(project_path(root, '.pipeline/sources.jsonl'), {**failure,'status':'failed','at':now()})
        report = {'ok':not failures,'sources':len(rows),'failures':failures}
        atomic_json(project_path(root, 'reports/acquisition.json'), report)
        return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--plan', type=Path, default=Path('source-plan.json'), help='Relative to --project unless absolute')
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--max-bytes', type=int, help='Optional per-file limit, chosen for this task')
    ap.add_argument('--refresh', action='store_true')
    args = ap.parse_args()
    plan = args.plan if args.plan.is_absolute() else args.project / args.plan
    try:
        report = run(args.project, plan, args.workers, args.refresh, args.max_bytes)
    except Exception as error:
        report = {'ok':False,'error':str(error)}
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
