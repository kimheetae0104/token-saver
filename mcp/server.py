#!/usr/bin/env python3
"""token-saver MCP 서버 — Desktop Code 탭에서 hooks 대신 능동 계측을 복원한다.

Desktop 앱 Code 탭(Claude Code를 stream-json server/API 모드로 구동)은 hooks가
발화하지 않는다(desktop/desktop#22138, closed as not planned) — 하지만 MCP는 살아있다
(docs/superpowers/specs/2026-08-05-desktop-active-measurement-design.md의 "사전 검증"
섹션에서 실측 확인, 2026-08-05). 이 서버가 measure.py의 계측 로직을 툴로 노출해 그 공백을
best-effort로 메운다.

의존성 없음(mcp/@modelcontextprotocol/sdk 미설치 환경 대응) — JSON-RPC 2.0을
stdin/stdout에 한 줄씩(뉴라인 구분, Content-Length 프레이밍 아님) 손수 구현.
로깅은 전부 stderr(그래야 stdout의 JSON-RPC 스트림이 안 깨짐).

설계: docs/superpowers/specs/2026-08-05-desktop-active-measurement-design.md
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import measure  # noqa: E402


def log(msg):
    print(f"[token-saver-mcp] {msg}", file=sys.stderr, flush=True)


def resolve_project_dir():
    """CLAUDE_PROJECT_DIR이 있으면 우선(플러그인 host가 넘겨줄 것으로 기대 — Desktop에서
    실제로 세팅되는지는 Task 7에서 실측 확인 예정). 없으면 cwd로 폴백해 최소한 로컬
    수동 실행은 항상 동작하게 한다."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _resolve_transcript():
    """공용 트랜스크립트 탐색 — tool_check()·tool_autopsy() 둘 다 같은 '못 찾음' 조건을 쓰게 한다.
    반환: (path, None) 찾음 / (None, 진단_메시지) 못 찾음."""
    project_dir = resolve_project_dir()
    path = measure.latest_session(project_dir=project_dir)
    if not path or not os.path.isfile(path):
        return None, (f"세션 트랜스크립트를 못 찾음 — project_dir={project_dir}, "
                      f"탐색 경로={measure.transcript_dir(project_dir)}")
    return path, None


def tool_check():
    path, err = _resolve_transcript()
    if err:
        return err
    line = measure.check_line(path)
    if line:
        return line
    return f"트랜스크립트는 찾았으나 집계 가능한 턴이 아직 없음 — {os.path.basename(path)}"


def tool_autopsy():
    path, err = _resolve_transcript()
    if err:
        return err
    parts = [measure.autopsy_text(path)]
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    cap = measure.capture_failures_text(path, data_dir=data_dir)
    if cap:
        parts.append(cap)
    return "\n".join(parts)


TOOLS = {
    "token_saver_check": {
        "description": (
            "이 프로젝트의 현재 세션 토큰/비용/캐시적중률/효율점수를 한 줄로 반환한다. "
            "CLI/IDE에서는 시스템 컨텍스트에 '⟢ 턴...' 줄이 이미 자동으로 보이므로(훅 정상 "
            "발화 중) 이 툴을 다시 호출하지 말 것 — Desktop Code 탭처럼 그 줄이 안 보일 때만 호출."
        ),
        "handler": tool_check,
    },
    "token_saver_autopsy": {
        "description": (
            "이 프로젝트 현재 세션의 낭비 신호 부검(컨텍스트 비대·캐시 스래싱·rework 등)을 "
            "반환하고 실패 후보를 로그에 기록한다. 대화가 마무리되는 느낌일 때(사용자의 마무리 "
            "인사·'여기까지'류) 한 번만 호출해 요약을 짧게 보여주고 그 외엔 언급하지 말 것."
        ),
        "handler": tool_autopsy,
    },
}


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
                "serverInfo": {"name": "token-saver", "version": "0.1.0"},
            },
        })
    elif method == "notifications/initialized":
        log("client initialized")
    elif method == "tools/list":
        send({
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "tools": [
                    {"name": name, "description": spec["description"],
                     "inputSchema": {"type": "object", "properties": {}}}
                    for name, spec in TOOLS.items()
                ]
            },
        })
    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        spec = TOOLS.get(name)
        if spec is None:
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": f"unknown tool {name}"}})
            return
        try:
            text = spec["handler"]()
        except Exception as e:
            log(f"tool {name} failed: {e}")
            text = f"내부 오류: {e}"
        send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}]}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    elif mid is not None:
        send({"jsonrpc": "2.0", "id": mid,
              "error": {"code": -32601, "message": f"unknown method {method}"}})
    # else: 미지원 notification -- 조용히 무시(스펙대로).


def main():
    log(f"server started, pid={os.getpid()}, tools={list(TOOLS)}")
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
