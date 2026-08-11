#!/usr/bin/env python3
"""라우팅 사다리 강제 게이트 — 서브에이전트(Agent 도구) 위임 전에 `token_saver_suggest_tier`
MCP 툴을 반드시 먼저 호출하게 강제한다. CLAUDE.md의 사다리 규칙("Haiku→오라클 검증→...")은
지금까지 어시스턴트가 매번 기억해서 지키는 프롬프트 정책이었을 뿐 강제 수단이 없었다 —
이 훅은 "어떤 티어가 맞는지"는 여전히 판단해주지 않지만(그건 결정론 코드가 못 하는 부분,
실험9: 프로즈 분류의 위양성·위음성 실측), "판단 자체를 빼먹지 못하게" 강제는 할 수 있다.

세 가지 모드를 한 파일에 담는다(hooks.json에서 이벤트별로 다른 인자로 호출):
  --reset          UserPromptSubmit: 매 턴 시작 시 consulted=False로 리셋.
  --mark-consulted PostToolUse(matcher: token_saver_suggest_tier MCP 툴): consulted=True +
                   추천 티어를 응답 텍스트에서 파싱해 저장(가능하면).
  (인자 없음)       PreToolUse(matcher: Agent): consulted가 False면 deny. consulted=True여도
                   호출측이 명시한 model이 추천 티어와 다르면 1회만 다시 확인시킨다(강화,
                   2026-08-11) — "정말 그 티어로 할 거냐"만 묻고 강제로 막지는 않는다(정당한
                   이유로 추천과 다르게 고를 수도 있어서, 판단 자체는 여전히 Claude 몫).

강화 지점의 설계 원칙: 추천 티어 파싱은 내가 직접 생성한 고정 포맷 문자열("추천: <tier>(...")
을 정규식으로 읽는 것뿐이다 — 사용자의 자유 서술 태스크를 오라클 유무·의미론적 위험 등으로
자동 분류하려는 시도가 **아니다**(그건 실험9에서 위양성·위음성이 실측된 함정, 여전히 안 함).
여기서 비교하는 두 값(추천 티어 문자열, Agent 호출의 model 파라미터)은 둘 다 이미 결정된
값이라 단순 문자열 비교로 충분하다.

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

실측 로깅(2026-08-11 추가): "이게 실제로 쓰이긴 하냐"에 답하려면 지어낸 절감 추정치가
아니라 진짜 관측 이벤트가 필요하다 — Agent 호출이 최종 allow될 때마다 추천 티어·실제
model·둘이 일치했는지를 `ladder_gate_events/<session_id>.jsonl`에 남긴다(measure.py의
`ladder_gate_summary_for_session()`이 읽어 리포트에 합산). **의도적으로 안 하는 것**: "이걸
Sonnet으로 돌렸으면 얼마였을까" 같은 $ 환산은 안 한다 — 실제로 일어나지 않은 대안 실행의
비용을 추정하는 건 반증사례(RTK: 허수 counterfactual로 절감 카운터 조작, CLAUDE.md/README
"시장 비교" 참고)와 같은 함정이라 하지 않는다. 여기 남기는 건 전부 실제로 일어난 사실
(추천이 뭐였는지, 실제 model이 뭐였는지)뿐이다 — $ 합산은 이 로그가 쌓인 뒤 실제 서브에이전트
transcript의 실측 토큰(`actor_breakdown()`, 이미 존재)과 대조해서 낼 것.
"""
import json
import os
import re
import sys
import tempfile
import time

STATE_MAX_AGE_SEC = 24 * 60 * 60

# measure.py의 BASE_IN 키와 동일 — 훅은 self-contained 관례(config_store.py 참고)라
# import 대신 값만 짧게 중복. 순서는 무관(부분 문자열 매치라 먼저 맞는 것으로 충분).
_TIERS = ("opus", "sonnet", "haiku", "fable")
_RECOMMEND_RE = re.compile(r"^추천:\s*([a-z]+)", re.IGNORECASE)
_RESPONSE_FIELD_CANDIDATES = ("tool_output", "tool_response", "output")


def _tier_of(model):
    m = (model or "").lower()
    for t in _TIERS:
        if t in m:
            return t
    return None


def _extract_recommended_tier(payload):
    """PostToolUse payload에서 suggest_tier 응답 텍스트를 찾아 추천 티어를 뽑는다.
    필드명이 문서와 실제 배선에서 다를 수 있어(grep_trim.py의 OUTPUT_FIELD_CANDIDATES와
    동일 이유) 후보를 순서대로 시도, MCP 응답은 {"content":[{"type":"text","text":...}]}
    형태일 수도 있어 그 경로도 함께 시도. 못 찾으면 None(그래도 consulted 자체는 기록됨 —
    이 부가정보는 있으면 강화, 없어도 기본 게이트는 그대로 동작하는 fail-open 설계)."""
    for field in _RESPONSE_FIELD_CANDIDATES:
        val = payload.get(field)
        text = None
        if isinstance(val, str):
            text = val
        elif isinstance(val, dict):
            content = val.get("content")
            if isinstance(content, list) and content and isinstance(content[0], dict):
                text = content[0].get("text")
        if isinstance(text, str):
            m = _RECOMMEND_RE.match(text.strip())
            if m:
                return m.group(1).lower()
    return None


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


def events_dir():
    """measure.py의 ladder_gate_log_dir()와 정확히 같은 경로 규약(gate_events와는 별도
    디렉터리 — prompt_gate_trip 카운트 로직을 안 건드리려고 일부러 분리, 2026-08-11)."""
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    d = os.path.join(data_dir, "ladder_gate_events") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-ladder-gate-events")
    os.makedirs(d, exist_ok=True)
    return d


def log_resolution(session_id, recommended, requested, matched):
    try:
        path = os.path.join(events_dir(), f"{session_id}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps({
                "event": "ladder_gate_resolution",
                "recommended_tier": recommended,
                "requested_tier": requested,
                "matched": matched,
                "ts": time.time(),
            }) + "\n")
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
        state = {"consulted": True}
        recommended = _extract_recommended_tier(payload)
        if recommended:
            state["recommended_tier"] = recommended
        write_state(session_id, state)
        return allow()

    # 기본 모드: PreToolUse(matcher: Agent) 게이트 판정.
    state = read_state(session_id)
    if not state.get("consulted"):
        return deny(
            "서브에이전트로 위임하기 전에 token_saver_suggest_tier MCP 툴을 먼저 호출해 "
            "모델 티어(haiku/sonnet/opus)를 확인하세요 — 호출 후 다시 시도하면 통과합니다."
        )

    recommended = state.get("recommended_tier")
    requested = _tier_of((payload.get("tool_input") or {}).get("model"))
    if recommended and requested and recommended != requested and not state.get("mismatch_acknowledged"):
        state["mismatch_acknowledged"] = True
        write_state(session_id, state)
        return deny(
            f"방금 추천은 {recommended}였는데 model={requested}로 위임하려 합니다 — "
            f"의도적이면 그대로 다시 시도하세요(통과합니다), 아니면 model을 {recommended}로 바꾸세요."
        )
    if recommended:
        log_resolution(session_id, recommended, requested,
                        matched=(recommended == requested) if requested else None)
    return allow()


if __name__ == "__main__":
    main()
