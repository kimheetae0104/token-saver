#!/usr/bin/env python3
"""PreToolUse hook(matcher 없음 — 전체 도구. 선례: 공식 hookify 플러그인
~/.claude/plugins/marketplaces/claude-plugins-official/plugins/hookify/hooks/hooks.json이
동일하게 matcher 생략으로 전체 도구에 적용됨, 2026-08-09 실측 확인) — 모호한 요청으로
판단된 턴의 첫 도구 호출을 1회만 막아 Claude가 뭔가 말하고 나서 시작하게 유도한다
("1회성 트립 게이트", docs/superpowers/specs/2026-08-09-4slot-prompt-gate-design.md).

hooks/intent_gate.py(UserPromptSubmit)가 매 턴 상태파일에 {"flagged": bool, "tripped":
false}를 쓴다. 이 훅은 그 상태만 읽는다 — transcript_path는 쓰지 않는다(PreToolUse는 이
턴에 Claude가 이미 낸 텍스트를 payload로 못 받고, hooks/read_guard.py도 같은 이유로 자체
상태파일만 쓴다 — 그 선례를 그대로 재사용). 내용 검증은 하지 않는다(존재 여부조차 확인
불가) — deny 사유를 본 Claude가 자연스럽게 설명하며 재시도하는 구조로 같은 효과를 유도한다.

LLM 호출 없음, 결정론. stdlib만 사용.
킬스위치: TOKEN_SAVER_DISABLE_PROMPT_GATE=1 이면 무조건 허용.
fail-open: session_id 없음, 상태파일 없음/손상, 어떤 예외든 조용히 허용 — 도구 호출을
절대 깨뜨리지 않는다.
DIY 설정: config.json(config_store.py)의 prompt_gate.disabled로도 끌 수 있음. env
킬스위치가 항상 config보다 우선.
"""
import json
import os
import sys
import tempfile
import time

STATE_MAX_AGE_SEC = 24 * 60 * 60


def state_dir():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    d = os.path.join(data_dir, "prompt_gate") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-prompt-gate")
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
            return json.load(f).get("prompt_gate", {})
    except Exception:
        return {}


def load_state(session_id):
    try:
        with open(state_path(session_id), "r") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else None
    except Exception:
        return None


def write_state(session_id, state):
    try:
        path = state_path(session_id)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except Exception:
        pass


def _cleanup_old(d):
    try:
        now = time.time()
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if now - os.path.getmtime(p) > STATE_MAX_AGE_SEC:
                os.remove(p)
    except Exception:
        pass


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


def main():
    cfg = load_config()
    if not isinstance(cfg, dict):
        return allow()
    if os.environ.get("TOKEN_SAVER_DISABLE_PROMPT_GATE") == "1" or cfg.get("disabled"):
        return allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return allow()

    session_id = payload.get("session_id")
    if not session_id:
        return allow()

    state = load_state(session_id)
    if not state or not state.get("flagged"):
        return allow()
    if state.get("tripped"):
        return allow()

    write_state(session_id, {"flagged": True, "tripped": True})
    _cleanup_old(state_dir())
    return deny(
        "모호한 요청으로 판단됨 — 먼저 의도·제약·성공기준·위임경계 파싱본을 텍스트로 "
        "밝히고 나서 다시 시도하세요."
    )


if __name__ == "__main__":
    main()
