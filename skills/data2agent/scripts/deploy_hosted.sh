#!/usr/bin/env sh
# Deploy a hosted-target package: install `portal`, place the package, run it as a service. Three modes:
#
#   sh deploy_hosted.sh <pkg_dir> --local  [--addr 127.0.0.1:8080] [--service]        # this machine (systemd user/system unit with --service)
#   sh deploy_hosted.sh <pkg_dir> --remote user@host [--path /srv/<id>] [--addr 127.0.0.1:8080] [--service]   # over ssh + rsync/scp
#   sh deploy_hosted.sh <pkg_dir> --docker [--name <id>-portal] [--port 8080]            # docker compose on this machine
#
# Idempotent. Prints a JSON line with mode, url, portal path, service name. Exit non-zero on failure.
# TLS / public hostname: put Caddy or nginx in front (see the printed hint); this script binds to 127.0.0.1 by default.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
PKG=""; MODE=""; HOST=""; RPATH=""; ADDR="127.0.0.1:8080"; SERVICE=0; NAME=""; PORT=8080
while [ $# -gt 0 ]; do
  case "$1" in
    --local) MODE=local; shift ;;
    --remote) MODE=remote; HOST="$2"; shift 2 ;;
    --docker) MODE=docker; shift ;;
    --path) RPATH="$2"; shift 2 ;;
    --addr) ADDR="$2"; shift 2 ;;
    --service) SERVICE=1; shift ;;
    --name) NAME="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    -*) echo "unknown arg $1" >&2; exit 2 ;;
    *) PKG="$1"; shift ;;
  esac
done
[ -n "$PKG" ] && [ -f "$PKG/manifest.json" ] || { echo "usage: deploy_hosted.sh <pkg_dir> --local|--remote user@host|--docker" >&2; exit 2; }
[ -n "$MODE" ] || { echo "choose --local, --remote or --docker" >&2; exit 2; }
PKG="$(cd "$PKG" && pwd)"
ID="$(sed -n 's/^[[:space:]]*"id":[[:space:]]*"\([^"]*\)".*/\1/p' "$PKG/manifest.json" | head -1)"
[ -n "$NAME" ] || NAME="${ID}-portal"
json() { printf '{"mode":"%s","url":"%s","portal":"%s","service":"%s","path":"%s"}\n' "$1" "$2" "$3" "$4" "$5"; }

install_service() { # $1 = portal bin, $2 = pkg path, $3 = addr, $4 = unit name
  if [ "$(id -u)" = 0 ]; then UNIT_DIR=/etc/systemd/system; SCTL="systemctl"; else UNIT_DIR="$HOME/.config/systemd/user"; SCTL="systemctl --user"; fi
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/$4.service" <<EOF
[Unit]
Description=Data2Agent portal: $4
After=network.target

[Service]
ExecStart=$1 serve $2 --addr $3
Restart=on-failure
WorkingDirectory=$2

[Install]
WantedBy=default.target
EOF
  $SCTL daemon-reload && $SCTL enable --now "$4.service" >/dev/null 2>&1 && $SCTL is-active "$4.service" >/dev/null
}

case "$MODE" in
  local)
    BIN="$(command -v portal 2>/dev/null || true)"
    [ -n "$BIN" ] || BIN="$(sh "$HERE/install_portal.sh")"
    if [ "$SERVICE" = 1 ] && command -v systemctl >/dev/null 2>&1; then
      install_service "$BIN" "$PKG" "$ADDR" "$NAME"; SVC="$NAME.service"
    else
      nohup "$BIN" serve "$PKG" --addr "$ADDR" >"$PKG/../portal.log" 2>&1 & SVC="nohup pid $!"
      sleep 1
    fi
    json local "http://$ADDR/" "$BIN" "$SVC" "$PKG" ;;
  remote)
    [ -n "$RPATH" ] || RPATH="/srv/$ID"
    ssh "$HOST" "mkdir -p '$RPATH'"
    if command -v rsync >/dev/null 2>&1; then rsync -a --delete --exclude portal.json "$PKG/" "$HOST:$RPATH/"; else scp -rq "$PKG/." "$HOST:$RPATH/"; fi
    scp -q "$HERE/install_portal.sh" "$HOST:$RPATH/.install_portal.sh"
    REMOTE_BIN="$(ssh "$HOST" "command -v portal 2>/dev/null || sh '$RPATH/.install_portal.sh'")"
    if [ "$SERVICE" = 1 ]; then
      ssh "$HOST" "$(declare -f install_service 2>/dev/null || sed -n '/^install_service()/,/^}/p' "$0"); install_service '$REMOTE_BIN' '$RPATH' '$ADDR' '$NAME'"
      SVC="$NAME.service"
    else
      ssh "$HOST" "nohup '$REMOTE_BIN' serve '$RPATH' --addr '$ADDR' >'$RPATH/../$NAME.log' 2>&1 &"; SVC="nohup"
    fi
    ssh "$HOST" "curl -fsS http://$ADDR/api/obs/count >/dev/null" && json remote "http://$ADDR/ (on $HOST)" "$REMOTE_BIN" "$SVC" "$RPATH" ;;
  docker)
    [ -f "$PKG/Dockerfile" ] || { echo "package has no Dockerfile: rebuild with build_portal.py --target hosted" >&2; exit 1; }
    (cd "$PKG" && docker build -q -t "$NAME" . >/dev/null && (docker rm -f "$NAME" >/dev/null 2>&1 || true) && docker run -d --name "$NAME" --restart unless-stopped -p "127.0.0.1:$PORT:8080" "$NAME" >/dev/null)
    sleep 2; curl -fsS "http://127.0.0.1:$PORT/api/obs/count" >/dev/null
    json docker "http://127.0.0.1:$PORT/" "container:$NAME" "docker" "$PKG" ;;
esac
echo "hint: for a public hostname with TLS put Caddy in front:  caddy reverse-proxy --from portal.example.org --to $ADDR" >&2
