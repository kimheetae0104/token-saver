#!/usr/bin/env python3
"""token_saver_check MCP 툴 중복 호출 결정론적 차단.

배경(실험11, experiments/PROTOCOL.md, HANDOFF.md): hooks가 정상 발화 중이라 `⟢` 효율
줄이 이미 컨텍스트에 있는데도, 모델이 token_saver_check를 중복 호출하는 사례가 실사용
트랜스크립트에서 실측됐다. 원인은 skills/rules/SKILL.md의 "⟢ 줄이 보이면 호출하지 마라"가
프롬프트 수준 자기감지 지시였다는 것 — 실전에서 안 지켜졌다(Desktop auto-mode 안전성
체크 단계에서 529로 실패까지 함, 순전히 낭비).

이 훅은 그 판단을 프롬프트에서 코드로 옮긴다: **이 PreToolUse 훅 자체가 실행됐다는 사실이
곧 이 환경에서 hooks가 살아있다는 결정론적 증거**다 — UserPromptSubmit(measure.py --check)이
같은 hooks.json 배선을 타고 같은 턴에 이미 먼저 발화해 `⟢` 줄을 컨텍스트에 넣었을 것이므로,
token_saver_check 호출은 그 줄을 그대로 반복할 뿐이다. 그래서 무조건 deny한다.

hooks가 아예 안 뜨는 환경(원 GitHub 이슈 재현 환경인 Windows Desktop Code 탭 등,
desktop/desktop#22138)에서는 이 PreToolUse 훅 자체가 호출되지 않으므로 자동으로
fail-open — token_saver_check 호출이 그대로 통과해 원래 설계대로(mcp/server.py
docstring) "hooks 없는 환경의 유일한 사람이 보는 경로" 역할을 계속한다. 별도 분기 불필요.

token_saver_suggest_tier·token_saver_autopsy는 이 훅의 matcher 대상이 아니다 —
전자는 ladder_gate.py가 이미 강제하는 별개 목적, 후자는 세션 종료 요약이라 `⟢` 줄과
중복이 아니다.

LLM 호출 없음, 결정론. stdlib만 사용.
킬스위치: TOKEN_SAVER_DISABLE_CHECK_GATE=1이면 무조건 허용.
DIY 설정: config.json(config_store.py)의 check_gate.disabled로도 끌 수 있음. env
킬스위치가 항상 config보다 우선.
fail-safe: config.json 손상/파싱 실패 -> "비활성화 안 됨"으로 취급해 게이트 유지
(ladder_gate.py와 동일 원칙 — 설정 손상으로 안전장치가 조용히 풀리면 안 됨).
fail-open: stdin이 없거나 파싱 실패 -> 무조건 허용(도구 호출을 절대 깨뜨리지 않는다).
"""
import json
import os
import sys
import tempfile


def config_path():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    return os.path.join(data_dir, "config.json") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-config.json")


def load_config():
    try:
        with open(config_path(), "r") as f:
            return json.load(f).get("check_gate", {})
    except Exception:
        return {}


def gate_disabled():
    if os.environ.get("TOKEN_SAVER_DISABLE_CHECK_GATE") == "1":
        return True
    return bool(load_config().get("disabled"))


def allow():
    sys.exit(0)


def deny():
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "이 훅이 지금 실행됐다는 사실 자체가 이 환경에서 hooks가 정상 발화 중이라는 "
                "증거입니다 — UserPromptSubmit hook이 이번 턴에 이미 실행돼 '⟢' 효율 줄이 "
                "컨텍스트에 들어가 있습니다. token_saver_check는 그 줄과 동일한 내용을 "
                "반복할 뿐이라 호출을 막습니다 — 이미 보이는 '⟢' 줄을 그대로 재사용하세요."
            ),
        }
    }))
    sys.exit(0)


def main():
    if gate_disabled():
        return allow()
    try:
        json.load(sys.stdin)
    except Exception:
        return allow()
    return deny()


if __name__ == "__main__":
    main()
