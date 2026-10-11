#!/usr/bin/env sh
# Data2Agent stage 0: make the machine ready without asking the user to configure anything.
#
#   sh "$SKILL_ROOT/scripts/bootstrap.sh" "$PROJECT_ROOT"      -> writes PROJECT_ROOT/.d2a/env.json
#
# What it does, idempotently:
#   1. finds or installs `uv` (user-local, no sudo); uv also provides an isolated Python, so a broken system Python is irrelevant
#   2. creates PROJECT_ROOT/.d2a/venv with the skill's requirements.txt and verifies it with check_env.py
#   3. locates the `portal` binary: $PORTAL, next to the skill (bin/), a cached copy, a GitHub release download, or a local Go build
#   4. records every path in .d2a/env.json; later stages read PY and PORTAL from there
# Exit 0 when Python is ready (portal may be "unavailable": the agent then skips MCP verification / hosted target and says so).
set -u
SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_ROOT="${1:-$PWD}"
mkdir -p "$PROJECT_ROOT/.d2a"
D2A="$PROJECT_ROOT/.d2a"
PY_VERSION="${D2A_PYTHON:-3.12}"
PORTAL_VERSION="${D2A_PORTAL_VERSION:-latest}"
log() { printf '[bootstrap] %s\n' "$*" >&2; }
retry() { n=0; until "$@"; do n=$((n+1)); [ "$n" -ge 3 ] && return 1; log "retry $n: $*"; sleep $((n*3)); done; }

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
  retry "$UV" pip install --python "$VENV/bin/python" -q -r "$SKILL_ROOT/requirements.txt"
else
  [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
  retry "$VENV/bin/python" -m pip install -q -r "$SKILL_ROOT/requirements.txt"
fi
PY="$VENV/bin/python"
[ -x "$PY" ] || PY="$VENV/Scripts/python.exe"
if ! "$PY" "$SKILL_ROOT/scripts/check_env.py" >"$D2A/check_env.json" 2>&1; then
  log "environment check failed:"; cat "$D2A/check_env.json" >&2
  exit 1
fi
log "python ready: $PY"

# ---- 3. portal binary
PORTAL_BIN=""
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"; ARCH="$(uname -m)"
case "$ARCH" in x86_64|amd64) ARCH=amd64 ;; aarch64|arm64) ARCH=arm64 ;; esac
for cand in "${PORTAL:-}" "$SKILL_ROOT/bin/portal" "$HOME/.cache/data2agent/portal" "$SKILL_ROOT/../../portal/portal"; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then PORTAL_BIN="$(cd "$(dirname "$cand")" && pwd)/$(basename "$cand")"; break; fi
done
if [ -z "$PORTAL_BIN" ] && command -v curl >/dev/null 2>&1; then
  mkdir -p "$HOME/.cache/data2agent"
  url="https://github.com/xuzhougeng/data2agent/releases/${PORTAL_VERSION}/download/portal_${OS}_${ARCH}.tar.gz"
  [ "$PORTAL_VERSION" != "latest" ] && url="https://github.com/xuzhougeng/data2agent/releases/download/${PORTAL_VERSION}/portal_${OS}_${ARCH}.tar.gz"
  log "trying release download: $url"
  if curl -fsSL "$url" -o "$D2A/portal.tgz" 2>/dev/null && tar -xzf "$D2A/portal.tgz" -C "$HOME/.cache/data2agent" portal 2>/dev/null; then
    chmod +x "$HOME/.cache/data2agent/portal"; PORTAL_BIN="$HOME/.cache/data2agent/portal"
  fi
  rm -f "$D2A/portal.tgz"
fi
if [ -z "$PORTAL_BIN" ] && command -v go >/dev/null 2>&1 && [ -d "$SKILL_ROOT/../../portal" ]; then
  log "building portal with local Go toolchain"
  (cd "$SKILL_ROOT/../../portal" && retry go build -o portal ./cmd/portal) && PORTAL_BIN="$(cd "$SKILL_ROOT/../../portal" && pwd)/portal"
fi
if [ -n "$PORTAL_BIN" ]; then log "portal ready: $PORTAL_BIN"; else log "portal unavailable: MCP verification and the hosted target are disabled for this run"; fi

# ---- 4. env.json
"$PY" - "$D2A/env.json" "$PY" "$PORTAL_BIN" "$SKILL_ROOT" "$PROJECT_ROOT" "$UV" <<'EOF'
import json, sys, platform
out, py, portal, skill, project, uv = sys.argv[1:7]
json.dump({"PY": py, "PORTAL": portal or None, "SKILL_ROOT": skill, "PROJECT_ROOT": project, "UV": uv or None,
           "platform": platform.platform(), "portal_available": bool(portal)}, open(out, "w"), indent=2)
print(open(out).read())
EOF
