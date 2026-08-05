#!/usr/bin/env python3
"""Minimal hand-rolled stdio MCP server -- Desktop Code-tab MCP connectivity probe.

No SDK dependency (the `mcp` / `@modelcontextprotocol/sdk` packages aren't
installed in this environment) -- implements just enough of the MCP stdio
transport to answer one question empirically: does Claude Desktop's Code tab
(which runs Claude Code in stream-json server/API mode, where hooks are
confirmed broken -- desktop/desktop#22138, closed as not planned) actually
spawn a project-scoped `.mcp.json` stdio server and invoke its tool?

This is NOT the final design. It's the cheapest oracle before building
anything real (project rule: "완료/커밋 선언 전 가장 값싼 오라클 먼저").
Result goes in experiments/PROTOCOL.md, not assumed from blog posts.

Protocol: JSON-RPC 2.0, one message per line on stdin/stdout, no
Content-Length framing (that's LSP, not MCP stdio). All logging goes to
stderr so it never corrupts the JSON-RPC stream on stdout.
"""
import json
import os
import secrets
import sys
import time

COUNTER_PATH = os.path.join(os.path.dirname(__file__), "call_count.txt")


def log(msg):
    print(f"[probe] {msg}", file=sys.stderr, flush=True)


def bump_counter():
    n = 0
    if os.path.exists(COUNTER_PATH):
        try:
            n = int(open(COUNTER_PATH).read().strip() or "0")
        except ValueError:
            n = 0
    n += 1
    with open(COUNTER_PATH, "w") as f:
        f.write(str(n))
    return n


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(msg):
    mid = msg.get("id")
    method = msg.get("method")

    if method == "initialize":
        send({
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": msg.get("params", {}).get("protocolVersion", "2026-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "token-saver-desktop-probe", "version": "0.0.1"},
            },
        })
    elif method == "notifications/initialized":
        log("client sent initialized notification")
    elif method == "tools/list":
        send({
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "tools": [{
                    "name": "token_saver_probe",
                    "description": (
                        "Connectivity probe for token-saver. Call this once to prove "
                        "the Desktop Code tab actually spawned and invoked a "
                        "project-scoped stdio MCP server."
                    ),
                    "inputSchema": {"type": "object", "properties": {}},
                }]
            },
        })
    elif method == "tools/call":
        params = msg.get("params", {})
        if params.get("name") == "token_saver_probe":
            n = bump_counter()
            payload = {
                "call_count": n,
                "nonce": secrets.token_hex(4),
                "pid": os.getpid(),
                "unix_time": int(time.time()),
                "cwd": os.getcwd(),
            }
            send({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
            })
        else:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown tool"}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    elif mid is not None:
        # Unknown request -- still must respond, or the client hangs waiting.
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}})
    # else: unknown notification -- ignore silently, per spec.


def main():
    log(f"probe server started, pid={os.getpid()}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log(f"bad json: {line!r}")
            continue
        try:
            handle(msg)
        except Exception as e:
            log(f"handler error: {e}")


if __name__ == "__main__":
    main()
