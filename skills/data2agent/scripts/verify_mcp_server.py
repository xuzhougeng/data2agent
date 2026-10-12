#!/usr/bin/env python
"""Verify a Go or project-specific MCP server over real stdio. No dependencies.

usage: verify_mcp_server.py --server "./portal/portal mcp out/pbmc3k" [--cases cases.json] [--report report.json]
                            [--require-tools describe_tables,sql,search_features,get_obs,feature_summary]
                            [--cwd project_dir] [--timeout 60]
Use --server-argv '["/path/to/python", "-m", "app.mcp"]' for a structured command.

cases.json: [{"name": "...", "tool": "sql", "arguments": {...}, "expect_contains": "text", "expect_json_subset": {...}, "expect_error": false}]
  expect_contains   - the concatenated text content must contain this substring
  expect_json_subset - text content parsed as JSON must contain these keys/values (recursive subset; arrays: prefix, element-wise subset)
Exit 0 only when the handshake works, every required tool is listed, and every case passes.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
import queue
import threading
from collections import deque
from pathlib import Path


class Stdio:
    def __init__(self, cmd: list[str], cwd=None, timeout=60.0):
        self.p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        self.n = 0
        self.timeout = timeout
        self.responses = queue.Queue()
        self.errors = deque(maxlen=4)
        def read_stdout():
            for line in self.p.stdout:
                try:
                    self.responses.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
            self.responses.put(None)
        def read_stderr():
            while chunk := self.p.stderr.read(2048):
                self.errors.append(chunk)
        self.readers = [threading.Thread(target=read_stdout, daemon=True), threading.Thread(target=read_stderr, daemon=True)]
        for reader in self.readers:
            reader.start()

    def request(self, method: str, params: dict | None = None, timeout=None) -> dict:
        self.n += 1
        msg = {"jsonrpc": "2.0", "id": self.n, "method": method}
        if params is not None:
            msg["params"] = params
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while time.monotonic() < deadline:
            try:
                obj = self.responses.get(timeout=max(0, deadline-time.monotonic()))
            except queue.Empty:
                self.p.kill()
                raise TimeoutError(method) from None
            if obj is None:
                raise RuntimeError(f"server closed stdout; stderr: {''.join(self.errors)[-2000:]}")
            if obj.get("id") == self.n:
                if "error" in obj:
                    raise RuntimeError(f"{method}: {obj['error']}")
                return obj["result"]
        self.p.kill()
        raise TimeoutError(method)

    def notify(self, method: str, params: dict | None = None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()
            self.p.wait()
        finally:
            for reader in self.readers:
                reader.join(timeout=1)
            self.p.stdout.close()
            self.p.stderr.close()


def subset(actual, expected, path="$") -> str | None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return f"{path}: expected object"
        for k, v in expected.items():
            if k not in actual:
                return f"{path}.{k}: missing"
            if (err := subset(actual[k], v, f"{path}.{k}")):
                return err
        return None
    if isinstance(expected, list):  # prefix subset: expected[i] must be a subset of actual[i]
        if not isinstance(actual, list) or len(actual) < len(expected):
            return f"{path}: expected list with >= {len(expected)} items"
        for i, item in enumerate(expected):
            if (err := subset(actual[i], item, f"{path}[{i}]")):
                return err
        return None
    if isinstance(expected, float) and isinstance(actual, (int, float)):
        return None if abs(actual - expected) <= 1e-6 * max(1, abs(expected)) else f"{path}: {actual} != {expected}"
    return None if actual == expected else f"{path}: {actual!r} != {expected!r}"


def main():
    ap = argparse.ArgumentParser()
    command = ap.add_mutually_exclusive_group(required=True)
    command.add_argument("--server", help="command line that starts the stdio MCP server")
    command.add_argument("--server-argv", help="JSON argv array; avoids quoting issues in paths")
    ap.add_argument("--cwd", type=Path, help="working directory of the server process")
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds per request")
    ap.add_argument("--cases", type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--require-tools", default="", help="comma-separated tool names the server must expose; e.g. describe_tables,sql,search_features,get_obs,feature_summary for the bundled Go portal")
    a = ap.parse_args()

    report = {"server": a.server or a.server_argv, "ok": False, "tools": [], "cases": []}
    s = None
    try:
        argv = json.loads(a.server_argv) if a.server_argv else shlex.split(a.server)
        if not isinstance(argv, list) or not argv or not all(isinstance(x,str) and x for x in argv) or a.timeout <= 0:
            raise ValueError('Expected a nonempty argv array and positive timeout')
        s = Stdio(argv, cwd=a.cwd, timeout=a.timeout)
        init = s.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "verify_mcp_server", "version": "0"}})
        s.notify("notifications/initialized")
        report["server_info"] = init.get("serverInfo")
        tools = s.request("tools/list").get("tools", [])
        report["tools"] = [{"name": t["name"], "required": sorted((t.get("inputSchema") or {}).get("required", []))} for t in tools]
        names = {t["name"] for t in tools}
        missing = [t for t in a.require_tools.split(",") if t and t not in names]
        report["missing_tools"] = missing

        cases = json.loads(a.cases.read_text()) if a.cases else []
        for c in cases:
            rec = {"name": c["name"], "tool": c["tool"], "ok": False}
            try:
                res = s.request("tools/call", {"name": c["tool"], "arguments": c.get("arguments", {})})
                textv = "".join(x.get("text", "") for x in res.get("content", []) if x.get("type") == "text")
                is_err = bool(res.get("isError"))
                rec["is_error"] = is_err
                rec["chars"] = len(textv)
                if c.get("expect_error", False) != is_err:
                    rec["reason"] = f"isError={is_err}, expected {c.get('expect_error', False)}: {textv[:200]}"
                elif "expect_contains" in c and c["expect_contains"] not in textv:
                    rec["reason"] = f"text lacks {c['expect_contains']!r}: {textv[:200]}"
                elif "expect_json_subset" in c:
                    try:
                        parsed = json.loads(textv)
                    except json.JSONDecodeError:
                        rec["reason"] = f"not JSON: {textv[:120]}"
                    else:
                        err = subset(parsed, c["expect_json_subset"])
                        if err:
                            rec["reason"] = err
                        else:
                            rec["ok"] = True
                else:
                    rec["ok"] = True
            except Exception as e:  # noqa: BLE001
                rec["reason"] = str(e)
            report["cases"].append(rec)
        report["ok"] = not missing and all(r["ok"] for r in report["cases"])
    except Exception as e:  # noqa: BLE001
        report["error"] = str(e)
    finally:
        if s is not None:
            s.close()

    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(text + "\n")
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
