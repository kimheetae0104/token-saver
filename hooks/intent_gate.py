#!/usr/bin/env python3
"""UserPromptSubmit hook: 모호한 착수형 요청에 4슬롯(CLAUDE.md "왕복 최소화" —
의도·제약·성공기준·위임경계) 리마인더 주입. 결정론 휴리스틱만 사용(LLM 호출 없음 —
AI-YAGNI). 사소한 요청은 침묵.

2026-08-09 확장: 기존엔 성공기준·범위(≈제약) 2개만 봤다 — "더 강화시켜"·"그것도 강화해"
같은, 실제로 이 세션에서 되물어야 했던 초단문 지시형 요청을 놓쳤음(ACTION_WORDS에
"강화"류 동사 자체가 없었고, 대상이 대명사/생략인 경우를 보는 축이 없었음). 4슬롯 전체를
보도록 의도(초단문+대상 생략 프록시)·위임경계(광범위 작업인데 직접/위임 언급 없음)를 추가.
"""
import json
import os
import re
import sys
import tempfile

ACTION_WORDS = (r"(만들|구현|개발|작성|추가|리팩터|고쳐|수정|바꿔|변경|설계|빌드|생성"
                r"|강화|개선|향상|최적화|정리해|올려|늘려)")
CONSTRAINT_WORDS = (r"(파일|모듈|디렉터리|폴더|전체|~까지|만\b|만큼|범위"
                    r"|하지\s?말|빼고|말고|반드시|절대|필수|이내로|건드리지\s?말|유지해)")
SUCCESS_WORDS = r"(기준|완료되면|성공|테스트|검증|확인되면|되면 끝|승인)"
BROAD_WORDS = r"(전체|모든|전부|대량|여러|일괄)"
DELEGATION_WORDS = r"(서브에이전트|위임|직접|네가\s?다|전부\s?네가|병렬로|worktree|브랜치)"

WORD_COUNT_MAX = 25   # 이보다 길면 이미 맥락이 충분하다고 간주
SHORT_INTENT_MAX = 3  # 이하 단어수면 대상이 이전 대화에 암묵적으로 의존할 가능성 높음
                      # (실측 근거: "더 강화시켜"=2단어, "그것도 강화해"=2단어 — 둘 다
                      # 실제로 AskUserQuestion 되묻기가 필요했던 케이스)


def state_dir():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    d = os.path.join(data_dir, "prompt_gate") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-prompt-gate")
    os.makedirs(d, exist_ok=True)
    return d


def state_path(session_id):
    return os.path.join(state_dir(), f"{session_id}.json")


def write_flag_state(session_id, flagged):
    """hooks/prompt_gate.py(PreToolUse)가 읽는 상태파일 — 매 턴 덮어써서 이전 턴 상태가
    새 턴에 새지 않게 한다. session_id 없으면 아무것도 안 씀(fail-open)."""
    if not session_id:
        return
    try:
        path = state_path(session_id)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"flagged": flagged, "tripped": False}, f)
        os.replace(tmp, path)
    except Exception:
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    session_id = payload.get("session_id")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        write_flag_state(session_id, False)
        return
    prompt = prompt.strip()
    if not prompt:
        write_flag_state(session_id, False)
        return

    words = re.findall(r"\S+", prompt)
    if len(words) > WORD_COUNT_MAX:
        write_flag_state(session_id, False)
        return

    has_action = re.search(ACTION_WORDS, prompt) is not None
    if not has_action:
        write_flag_state(session_id, False)
        return

    has_constraint = re.search(CONSTRAINT_WORDS, prompt) is not None
    has_success = re.search(SUCCESS_WORDS, prompt) is not None
    is_broad = re.search(BROAD_WORDS, prompt) is not None
    has_delegation = re.search(DELEGATION_WORDS, prompt) is not None

    missing = []
    if len(words) <= SHORT_INTENT_MAX:
        missing.append("의도(무엇을 대상으로)")
    if not has_constraint:
        missing.append("제약(하지 말아야 할 것·범위)")
    if not has_success:
        missing.append("성공기준(뭐가 되면 끝)")
    if is_broad and not has_delegation:
        missing.append("위임경계(직접 할지 위임할지)")

    write_flag_state(session_id, len(words) <= SHORT_INTENT_MAX)
    if not missing:
        return

    print(f"💡 착수 전 확인: {', '.join(missing)}이 불명확하면 되묻고, 명확하면 파싱본 echo 후 진행 권장.")


if __name__ == "__main__":
    main()
