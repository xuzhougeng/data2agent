# Stage 7 — Deploy (hosted target; static targets follow USAGE's publish section)

Goal: the portal runs on the machine the user named, with `portal` installed by you, not by the user.

Ask once where it should run; the answer is one of:

| Where | Command (from `PROJECT_ROOT`) | What it does |
| --- | --- | --- |
| this machine | `sh "$SKILL_ROOT/scripts/deploy_hosted.sh" pkg --local --addr 127.0.0.1:8080 --service` | installs `portal` to `~/.local/bin` (release download), systemd user unit `<id>-portal.service` |
| a server over ssh | `sh "$SKILL_ROOT/scripts/deploy_hosted.sh" pkg --remote user@host --path /srv/<id> --addr 127.0.0.1:8080 --service` | rsync the package, install `portal` there, systemd unit on the server |
| Docker here | `sh "$SKILL_ROOT/scripts/deploy_hosted.sh" pkg --docker --port 8080` | builds the image from the package's Dockerfile, runs the container |

The script prints one JSON line (`mode, url, portal, service, path`); save it to `reports/deploy.json`.

Then:
1. Smoke test from where the server runs: `curl -fsS <url>api/obs/count` and `curl -fsS <url>index.html | head -c 200`.
2. Rerun the `sql` acceptance cases against `<url>api/sql` (POST); record outcomes in `reports/api-verify.json`.
3. Public hostname / TLS: the script binds to `127.0.0.1`. If the user wants it reachable from outside, put a reverse proxy in front; the one-liner the script prints (`caddy reverse-proxy --from <host> --to 127.0.0.1:8080`) is enough for a single site. Do not open the port to `0.0.0.0` without a proxy.
4. Updates: rerun the same command after a rebuild; rsync/`--delete` and the Docker rebuild replace the package in place, the unit restarts.

Report: the URL, where `portal` was installed, the service name and how to stop it (`systemctl --user stop <id>-portal`, `docker rm -f <id>-portal`), and what was not verified (no public DNS, no TLS).

If `deploy_hosted.sh` cannot download a release (offline server, no release yet), copy the local `$PORTAL` binary to the target (`scp "$PORTAL" user@host:~/.local/bin/portal`) and rerun; say so in the report.
