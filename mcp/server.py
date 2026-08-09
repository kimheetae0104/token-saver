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
import config_store  # noqa: E402


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


def tool_check(args=None):
    """statusline_text()(check_line()이 아님) 사용 — Desktop Code 탭은 statusLine hook도
    안 뜨므로, 이 MCP 툴이 사람이 실제로 보는 유일한 경로다. check_line()은 어시스턴트
    컨텍스트 전용 비가시 채널이라 캐시절감·차단절감 세그먼트가 빠져 있어 여기엔 안 맞는다."""
    path, err = _resolve_transcript()
    if err:
        return err
    return measure.statusline_text(path)


def tool_autopsy(args=None):
    path, err = _resolve_transcript()
    if err:
        return err
    parts = [measure.autopsy_text(path)]
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    cap = measure.capture_failures_text(path, data_dir=data_dir)
    if cap:
        parts.append(cap)
    return "\n".join(parts)


def tool_config_get(args=None):
    """read_guard·grep_trim·bash_trim·prompt_gate의 현재 유효 설정(기본값 + DIY 오버라이드)을 사람이
    읽을 수 있게 요약한다. Desktop Code 탭은 hooks가 안 뜨므로, 값을 바꿔도 CLI/IDE 세션에서
    그 hook이 다음번 실행될 때 반영된다 — Desktop 자체의 자동 동작에는 영향 없음을 명시."""
    overrides = config_store.load_raw()
    lines = ["read_guard·grep_trim·bash_trim·prompt_gate 현재 설정(*=DIY로 바뀐 값, 나머지는 기본값):"]
    for hook_name, cfg in config_store.get_all().items():
        changed = overrides.get(hook_name, {})
        parts = [f"{k}={v}{'*' if k in changed else ''}" for k, v in cfg.items()]
        lines.append(f"  {hook_name}: " + ", ".join(parts))
    lines.append(f"설정 파일: {config_store.config_path()}")
    lines.append(
        "참고: Desktop Code 탭은 hooks가 안 뜨므로 이 값은 CLI/IDE 세션에서만 실제로 "
        "적용된다(env kill switch TOKEN_SAVER_DISABLE_*가 항상 최우선)."
    )
    return "\n".join(lines)


def tool_config_set(args):
    """token_saver_config_set(hook, key, value) — 임계값·kill switch 하나를 변경한다."""
    args = args or {}
    ok, result = config_store.set_value(args.get("hook"), args.get("key"), args.get("value"))
    if not ok:
        return f"설정 실패: {result}"
    return f"적용됨: {args.get('hook')}.{args.get('key')} = {result}"


def tool_config_reset(args=None):
    """token_saver_config_reset(hook?) — hook 지정 시 그 hook만, 없으면 전체를 기본값으로."""
    hook_name = (args or {}).get("hook")
    config_store.reset(hook_name)
    return f"{hook_name or '전체'} 설정을 기본값으로 복원했습니다."


EMPTY_SCHEMA = {"type": "object", "properties": {}}

TOOLS = {
    "token_saver_check": {
        "description": (
            "이 프로젝트의 현재 세션 토큰/비용/캐시적중률/효율점수를 한 줄로 반환한다. "
            "CLI/IDE에서는 시스템 컨텍스트에 '⟢ 턴...' 줄이 이미 자동으로 보이므로(훅 정상 "
            "발화 중) 이 툴을 다시 호출하지 말 것 — Desktop Code 탭처럼 그 줄이 안 보일 때만 호출."
        ),
        "handler": tool_check,
        "input_schema": EMPTY_SCHEMA,
    },
    "token_saver_autopsy": {
        "description": (
            "이 프로젝트 현재 세션의 낭비 신호 부검(컨텍스트 비대·캐시 스래싱·rework 등)을 "
            "반환하고 실패 후보를 로그에 기록한다. 대화가 마무리되는 느낌일 때(사용자의 마무리 "
            "인사·'여기까지'류) 한 번만 호출해 요약을 짧게 보여주고 그 외엔 언급하지 말 것."
        ),
        "handler": tool_autopsy,
        "input_schema": EMPTY_SCHEMA,
    },
    "token_saver_config_get": {
        "description": (
            "read_guard(재독 차단)·grep_trim·bash_trim(긴 출력 트림)·prompt_gate의 현재 임계값과 "
            "on/off 상태를 조회한다. 인자 없음. 사용자가 '너무 자주 막는다/너무 안 막는다' "
            "류로 조정을 원할 때 먼저 호출해 현재값을 보여줄 것."
        ),
        "handler": tool_config_get,
        "input_schema": EMPTY_SCHEMA,
    },
    "token_saver_config_set": {
        "description": (
            "read_guard·grep_trim·bash_trim·prompt_gate 중 하나의 임계값 또는 kill switch를 "
            "DIY로 변경한다. hook: 'read_guard'|'grep_trim'|'bash_trim'|'prompt_gate'. key: "
            "read_guard는 'disabled'|'large_file_lines', grep_trim은 'disabled'|"
            "'match_threshold'|'keep_head'|'keep_tail', bash_trim은 'disabled'|"
            "'line_threshold'|'keep_head'|'keep_tail', prompt_gate는 'disabled'만. value: "
            "숫자 또는 true/false. 변경 즉시 config.json에 저장되고 해당 hook의 다음 "
            "실행부터 반영된다(현재 실행 중인 호출엔 소급 적용 안 됨)."
        ),
        "handler": tool_config_set,
        "input_schema": {
            "type": "object",
            "properties": {
                "hook": {"type": "string",
                          "enum": ["read_guard", "grep_trim", "bash_trim", "prompt_gate"]},
                "key": {"type": "string"},
                "value": {},
            },
            "required": ["hook", "key", "value"],
        },
    },
    "token_saver_config_reset": {
        "description": (
            "token_saver_config_set으로 바꾼 값을 기본값으로 되돌린다. hook을 지정하면 "
            "그 hook만, 생략하면 전체(read_guard·grep_trim·bash_trim·prompt_gate 모두)를 "
            "초기화한다."
        ),
        "handler": tool_config_reset,
        "input_schema": {
            "type": "object",
            "properties": {"hook": {"type": "string",
                                     "enum": ["read_guard", "grep_trim", "bash_trim", "prompt_gate"]}},
        },
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
                     "inputSchema": spec.get("input_schema", EMPTY_SCHEMA)}
                    for name, spec in TOOLS.items()
                ]
            },
        })
    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments") or {}
        spec = TOOLS.get(name)
        if spec is None:
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": f"unknown tool {name}"}})
            return
        try:
            text = spec["handler"](arguments)
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
