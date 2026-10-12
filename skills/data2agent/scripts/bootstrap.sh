#!/usr/bin/env sh
# Data2Agent stage 0: make the machine ready without asking the user to configure anything.
#
#   sh "$SKILL_ROOT/scripts/bootstrap.sh" "$PROJECT_ROOT" [--profile dataset|project]
#   -> writes PROJECT_ROOT/.d2a/env.json
#
# What it does, idempotently:
#   1. finds or installs `uv` (user-local, no sudo); uv also provides an isolated Python, so a broken system Python is irrelevant
#   2. creates PROJECT_ROOT/.d2a/venv with the skill's requirements.txt and verifies it with check_env.py
#   3. locates the `portal` binary: $PORTAL, next to the skill (bin/), a cached copy, a GitHub release download, or a local Go build
#   4. records every path in .d2a/env.json; later stages read PY and PORTAL from there
# Exit 0 when the selected Python profile is ready. Go portal is optional;
# project-specific services and MCP servers do not depend on its availability.
set -eu
SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_ROOT="$PWD"
PROFILE=dataset
if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then PROJECT_ROOT="$1"; shift; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    *) echo "usage: bootstrap.sh [PROJECT_ROOT] [--profile dataset|project]" >&2; exit 2 ;;
  esac
done
case "$PROFILE" in dataset|project) ;; *) echo "unknown profile: $PROFILE" >&2; exit 2 ;; esac
mkdir -p "$PROJECT_ROOT/.d2a"
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"
D2A="$PROJECT_ROOT/.d2a"
PY_VERSION="${D2A_PYTHON:-3.12}"
PORTAL_VERSION="${D2A_PORTAL_VERSION:-}"   # empty = latest release
REQ="$SKILL_ROOT/requirements.txt"
[ "$PROFILE" = project ] && REQ="$SKILL_ROOT/requirements-core.txt"
log() { printf '[bootstrap] %s\n' "$*" >&2; }
retry() { n=0; until "$@"; do n=$((n+1)); [ "$n" -ge 3 ] && return 1; log "retry $n: $*"; sleep $((n*3)); done; }
install_failed() {
  log "dependency install failed for $REQ (offline, or a pin that cannot resolve); see uv/pip output above"
  printf '{"ok": false, "profile": "%s", "error": "dependency install failed for %s"}\n' "$PROFILE" "$REQ" >"$D2A/check_env.json"
  exit 1
}

# ---- 1. uv
UV="$(command -v uv 2>/dev/null || true)"
[ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
[ -z "$UV" ] && [ -x "$HOME/.cargo/bin/uv" ] && UV="$HOME/.cargo/bin/uv"
if [ -z "$UV" ]; then
  log "installing uv into ~/.local/bin (no sudo)"
  if command -v curl >/dev/null 2>&1; then retry sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' >/dev/null
  elif command -v wget >/dev/null 2>&1; then retry sh -c 'wget -qO- https://astral.sh/uv/install.sh | sh' >/dev/null
  fi
  UV="$HOME/.local/bin/uv"
fi
if [ ! -x "$UV" ]; then
  log "uv unavailable and could not be installed; falling back to python3 -m venv"
  UV=""
fi

# ---- 2. venv + deps
VENV="$D2A/venv"
if [ -n "$UV" ]; then
  [ -x "$VENV/bin/python" ] || retry "$UV" venv --python "$PY_VERSION" "$VENV" >/dev/null 2>&1 || retry "$UV" venv "$VENV" >/dev/null
  retry "$UV" pip install --python "$VENV/bin/python" -q -r "$REQ" || install_failed
else
  [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
  retry "$VENV/bin/python" -m pip install -q -r "$REQ" || install_failed
fi
PY="$VENV/bin/python"
[ -x "$PY" ] || PY="$VENV/Scripts/python.exe"
export MPLCONFIGDIR="${MPLCONFIGDIR:-$D2A/matplotlib}"
if ! "$PY" "$SKILL_ROOT/scripts/check_env.py" --profile "$PROFILE" >"$D2A/check_env.json" 2>"$D2A/check_env.log"; then
  log "environment check failed:"; cat "$D2A/check_env.json" "$D2A/check_env.log" >&2
  exit 1
fi
log "python ready: $PY"

# ---- 2b. vendored DuckDB-WASM extension (static portals then load parquet support from the package, not from a CDN)
if [ "$PROFILE" = dataset ] && ! ls "$SKILL_ROOT/templates/vendor/duckdb-ext"/*/*/parquet.duckdb_extension.wasm >/dev/null 2>&1; then
  log "vendoring DuckDB-WASM parquet extension (~5 MB, one-time)"
  "$PY" "$SKILL_ROOT/scripts/vendor_duckdb_ext.py" >/dev/null 2>&1 || log "vendoring failed (offline?); static portals will fall back to extensions.duckdb.org at runtime"
fi

# ---- 3. portal binary
PORTAL_BIN=""
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"; ARCH="$(uname -m)"
case "$ARCH" in x86_64|amd64) ARCH=amd64 ;; aarch64|arm64) ARCH=arm64 ;; esac
for cand in "${PORTAL:-}" "$SKILL_ROOT/bin/portal" "$HOME/.cache/data2agent/portal" "$SKILL_ROOT/../../portal/portal"; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then PORTAL_BIN="$(cd "$(dirname "$cand")" && pwd)/$(basename "$cand")"; break; fi
done
if [ "$PROFILE" = dataset ] && [ -z "$PORTAL_BIN" ]; then
  mkdir -p "$HOME/.cache/data2agent"
  log "installing portal from GitHub releases"
  if out="$(sh "$SKILL_ROOT/scripts/install_portal.sh" --dest "$HOME/.cache/data2agent" ${PORTAL_VERSION:+--version "$PORTAL_VERSION"} 2>/dev/null)"; then PORTAL_BIN="$out"; fi
fi
if [ "$PROFILE" = dataset ] && [ -z "$PORTAL_BIN" ] && command -v go >/dev/null 2>&1 && [ -d "$SKILL_ROOT/../../portal" ]; then
  log "building portal with local Go toolchain"
  (cd "$SKILL_ROOT/../../portal" && retry go build -o portal ./cmd/portal) && PORTAL_BIN="$(cd "$SKILL_ROOT/../../portal" && pwd)/portal"
fi
if [ -n "$PORTAL_BIN" ]; then log "portal available: $PORTAL_BIN"; else log "optional Go portal unavailable; project-specific HTTP/MCP services remain possible"; fi

# ---- 4. env.json
"$PY" - "$D2A/env.json" "$PY" "$PORTAL_BIN" "$SKILL_ROOT" "$PROJECT_ROOT" "$UV" "$PROFILE" <<'EOF'
import json, sys, platform
out, py, portal, skill, project, uv, profile = sys.argv[1:8]
json.dump({"PY": py, "PORTAL": portal or None, "SKILL_ROOT": skill, "PROJECT_ROOT": project, "UV": uv or None,
           "platform": platform.platform(), "portal_available": bool(portal), "profile": profile}, open(out, "w"), indent=2)
print(open(out).read())
EOF
