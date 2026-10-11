#!/usr/bin/env sh
# Install the Data2Agent `portal` binary for this OS/arch from GitHub Releases. No sudo needed by default.
#
#   sh install_portal.sh [--dest DIR] [--version vX.Y.Z]      # default dest: ~/.local/bin (or /usr/local/bin when writable as root)
#   curl -fsSL https://raw.githubusercontent.com/xuzhougeng/data2agent/main/skills/data2agent/scripts/install_portal.sh | sh
#
# Prints the installed path on success. Verifies checksums.txt when present. Idempotent: re-running updates in place.
set -eu
REPO="${D2A_REPO:-xuzhougeng/data2agent}"
VERSION="latest"; DEST=""
while [ $# -gt 0 ]; do case "$1" in --dest) DEST="$2"; shift 2 ;; --version) VERSION="$2"; shift 2 ;; *) echo "unknown arg $1" >&2; exit 2 ;; esac; done
if [ -z "$DEST" ]; then
  if [ "$(id -u)" = 0 ] && [ -w /usr/local/bin ]; then DEST=/usr/local/bin; else DEST="$HOME/.local/bin"; fi
fi
mkdir -p "$DEST"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"; ARCH="$(uname -m)"
case "$OS" in linux|darwin) ;; mingw*|msys*|cygwin*) OS=windows ;; *) echo "unsupported OS $OS" >&2; exit 1 ;; esac
case "$ARCH" in x86_64|amd64) ARCH=amd64 ;; aarch64|arm64) ARCH=arm64 ;; *) echo "unsupported arch $ARCH" >&2; exit 1 ;; esac
EXT=tar.gz; [ "$OS" = windows ] && EXT=zip
if [ "$VERSION" = latest ]; then BASE="https://github.com/$REPO/releases/latest/download"; else BASE="https://github.com/$REPO/releases/download/$VERSION"; fi
NAME="portal_${OS}_${ARCH}.${EXT}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fetch() { if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"; else wget -qO "$2" "$1"; fi; }
n=0; until fetch "$BASE/$NAME" "$TMP/$NAME"; do n=$((n+1)); [ "$n" -ge 3 ] && { echo "download failed: $BASE/$NAME" >&2; exit 1; }; sleep $((n*3)); done
if fetch "$BASE/checksums.txt" "$TMP/checksums.txt" 2>/dev/null; then
  want="$(grep " $NAME\$" "$TMP/checksums.txt" | cut -d' ' -f1 || true)"
  if [ -n "$want" ]; then
    have="$( (sha256sum "$TMP/$NAME" 2>/dev/null || shasum -a 256 "$TMP/$NAME") | cut -d' ' -f1)"
    [ "$want" = "$have" ] || { echo "checksum mismatch for $NAME" >&2; exit 1; }
  fi
fi
if [ "$EXT" = zip ]; then (cd "$TMP" && unzip -qo "$NAME"); BIN=portal.exe; else tar -xzf "$TMP/$NAME" -C "$TMP"; BIN=portal; fi
install -m 0755 "$TMP/$BIN" "$DEST/$BIN"
echo "$DEST/$BIN"
