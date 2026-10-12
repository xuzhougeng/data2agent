"""Small stdlib primitives shared by source acquisition and task receipts."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ponytail: process-global (path, size, mtime_ns) -> sha cache, like git's index; the runner
# persists it in .pipeline/hash-cache.json so no-op runs do not reread multi-GB artifacts.
HASH_CACHE = {}


def sha256(path):
    path = Path(path)
    stat = path.stat()
    key = f'{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}'
    if key in HASH_CACHE:
        return HASH_CACHE[key]
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    HASH_CACHE[key] = digest.hexdigest()
    return HASH_CACHE[key]


def load_hash_cache(root):
    path = project_path(root, '.pipeline/hash-cache.json')
    if path.exists():
        try:
            HASH_CACHE.update(json.loads(path.read_text()))
        except (ValueError, OSError):
            pass


def save_hash_cache(root):
    atomic_json(project_path(root, '.pipeline/hash-cache.json'), HASH_CACHE)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def project_path(root, relative):
    """Resolve a project-local path; reject traversal, root itself and escaping symlinks."""
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError(f'Expected a relative project path: {relative!r}')
    path = (root / relative).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError(f'Path escapes project: {relative!r}')
    return path


def artifact(path):
    """Content fingerprint including directory member names; no timestamps as evidence."""
    path = Path(path)
    if path.is_file():
        return {'kind': 'file', 'bytes': path.stat().st_size, 'sha256': sha256(path)}
    if not path.is_dir():
        raise FileNotFoundError(f'Missing artifact: {path}')
    files = []
    for child in sorted(path.rglob('*')):
        if child.is_symlink():
            raise ValueError(f'Directory artifacts must not contain symlinks: {child}')
        if child.is_file():
            files.append({'path': child.relative_to(path).as_posix(), 'bytes': child.stat().st_size, 'sha256': sha256(child)})
        elif not child.is_dir():
            raise ValueError(f'Unsupported artifact member: {child}')
    return {'kind': 'directory', 'files': len(files), 'bytes': sum(f['bytes'] for f in files), 'sha256': canonical_hash(files)}


def append_event(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def project_lock(root, name):
    """Process-scoped advisory lock on POSIX; no stale-PID guessing or process killing."""
    try:
        import fcntl
    except ImportError:
        raise RuntimeError('This runner requires POSIX locking; use WSL or a POSIX execution host.') from None
    path = project_path(root, '.pipeline/' + name + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f'Another {name} operation is active for this project') from None
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
