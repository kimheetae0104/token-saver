#!/usr/bin/env python3
"""라우팅 사다리 강제 게이트 — 서브에이전트(Agent 도구) 위임 전에 `token_saver_suggest_tier`
MCP 툴을 반드시 먼저 호출하게 강제한다. CLAUDE.md의 사다리 규칙("Haiku→오라클 검증→...")은
지금까지 어시스턴트가 매번 기억해서 지키는 프롬프트 정책이었을 뿐 강제 수단이 없었다 —
이 훅은 "어떤 티어가 맞는지"는 여전히 판단해주지 않지만(그건 결정론 코드가 못 하는 부분,
실험9: 프로즈 분류의 위양성·위음성 실측), "판단 자체를 빼먹지 못하게" 강제는 할 수 있다.

세 가지 모드를 한 파일에 담는다(hooks.json에서 이벤트별로 다른 인자로 호출):
  --reset          UserPromptSubmit: 매 턴 시작 시 consulted=False로 리셋.
  --mark-consulted PostToolUse(matcher: token_saver_suggest_tier MCP 툴): consulted=True.
  (인자 없음)       PreToolUse(matcher: Agent): consulted가 False면 deny.

matcher 이름 근거: MCP 툴 이름은 공식 문서(code.claude.com/docs/en/hooks)의 플러그인 번들
서버 규약 mcp__plugin_<plugin-name>_<server-name>__<tool> 그대로(2026-08-11 WebFetch로
직접 확인) — 이 플러그인은 name="token-saver", mcp 서버도 "token-saver"라
`mcp__plugin_token-saver_token-saver__token_saver_suggest_tier`가 된다. "Agent" 도구
이름은 이 세션 자신의 도구 목록과 tests/test_measure_refactor.py의 실제 tool_use 픽스처
양쪽에서 확인.

prompt_gate.py와 다른 점: prompt_gate는 "1회만 막고 그 뒤로는 계속 허용"(1회성 트립)이지만,
이건 "consulted 될 때까지 매번 막고, 된 뒤로는 이번 턴 내내 계속 허용" — 여러 Agent 호출을
병렬로 배치할 때(CLAUDE.md 권장 패턴) 전부 동일하게 판정돼야 하므로 prompt_gate처럼 "정확히
1개 프로세스만 트립" 같은 원자적 클레임이 필요 없다(단순 플래그 읽기로 충분, 경합 위험 없음).

LLM 호출 없음, 결정론. stdlib만 사용.
킬스위치: TOKEN_SAVER_DISABLE_LADDER_GATE=1이면 무조건 허용.
fail-open: session_id 없음, 상태파일 없음/손상, 어떤 예외든 조용히 허용 — 도구 호출을
절대 깨뜨리지 않는다.
DIY 설정: config.json(config_store.py)의 ladder_gate.disabled로도 끌 수 있음. env
킬스위치가 항상 config보다 우선.
"""
import json
import os
import sys
import tempfile

STATE_MAX_AGE_SEC = 24 * 60 * 60


def state_dir():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    d = os.path.join(data_dir, "ladder_gate") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-ladder-gate")
    os.makedirs(d, exist_ok=True)
    return d


def state_path(session_id):
    return os.path.join(state_dir(), f"{session_id}.json")


def config_path():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    return os.path.join(data_dir, "config.json") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-config.json")


def load_config():
    try:
        with open(config_path(), "r") as f:
            return json.load(f).get("ladder_gate", {})
    except Exception:
        return {}


def write_state(session_id, state):
    try:
        path = state_path(session_id)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except Exception:
        pass


def read_state(session_id):
    try:
        with open(state_path(session_id), "r") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def allow():
    sys.exit(0)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def gate_disabled():
    if os.environ.get("TOKEN_SAVER_DISABLE_LADDER_GATE") == "1":
        return True
    cfg = load_config()
    if not isinstance(cfg, dict):
        return True  # 손상/비정상 config -> fail-open(prompt_gate.py와 동일 원칙)
    return bool(cfg.get("disabled"))


def main():
    if gate_disabled():
        return allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return allow()

    session_id = payload.get("session_id")
    if not session_id:
        return allow()

    if "--reset" in sys.argv:
        write_state(session_id, {"consulted": False})
        return allow()

    if "--mark-consulted" in sys.argv:
        write_state(session_id, {"consulted": True})
        return allow()

    # 기본 모드: PreToolUse(matcher: Agent) 게이트 판정.
    state = read_state(session_id)
    if state.get("consulted"):
        return allow()
    return deny(
        "서브에이전트로 위임하기 전에 token_saver_suggest_tier MCP 툴을 먼저 호출해 "
        "모델 티어(haiku/sonnet/opus)를 확인하세요 — 호출 후 다시 시도하면 통과합니다."
    )


if __name__ == "__main__":
    main()
