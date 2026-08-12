#!/usr/bin/env python3
"""measure.py — Claude Code 토큰 세이버 측정 엔진.

세션 transcript(JSONL)의 usage를 파싱해 토큰·비용·캐시 적중률·행위자별 분해와
라이브 효율 프록시·낭비 부검(waste autopsy)을 산출한다. stdlib만 사용.

핵심 사실(리서치 확정):
- 비용 5분면: input×b + cache_write(5m×1.25 | 1h×2) + cache_read×0.1 + output×(5×b).
  모든 모델에서 배수 일정 → 모델별 base input 단가 하나만 알면 됨.
- 총 입력 = input_tokens + cache_creation_input_tokens + cache_read_input_tokens.
- 구독 계정이면 $는 실제 청구가 아니라 "동등 API 비용"(참고치).

CLI:
  measure.py [session.jsonl]     세션 리포트(기본: 최신 세션)
  measure.py --autopsy [s.jsonl] 낭비 부검(원인 귀속 + tip)
  measure.py --diff A B          두 세션 비교
  measure.py --all               세션 간 추세
  measure.py --statusline        stdin JSON(transcript_path) → 한 줄
  measure.py --score --quality Q --tokens N   OckScore/quality-per-1k
  measure.py --suggest-tier [--oracle] [--batch-size N] [--semantic-risk] [--high-stakes]
                                  서브에이전트 위임 시 모델 티어 추천(라우팅 사다리, 조언용)
"""
import json
import sys
import os
import glob
import math
import argparse
import re
import tempfile
import datetime

# ── config (단가는 2026-08 공식 pricing 기준; 런타임 재확인 권장) ──
# Claude Code는 프로젝트 경로의 비영숫자 문자를 '-'로 치환해 세션 디렉터리명을 만든다
# (예: /Volumes/Extreme SSD/worktree/token-saver → -Volumes-Extreme-SSD-worktree-token-saver).
# 하드코딩하면 프로젝트 폴더 이동 시 조용히 옛 경로를 가리키게 되므로(2026-08-04 실제로 발생:
# token-test → worktree/token-saver 이동 후 미수정 상태로 남아있었음) 스크립트 위치 기준으로 계산한다.
def transcript_dir(project_dir=None):
    """Claude Code 세션 저장 규칙: ~/.claude/projects/<프로젝트 경로의 비영숫자를 '-'로 치환>/.
    project_dir 기본값은 이 스크립트 파일의 디렉터리 — 레포 자체를 CLI로 실행할 때 프로젝트
    폴더가 이동해도 안 깨지는 기존 설계를 그대로 보존한다(2026-08-04 실제로 겪은 문제, 위 주석
    참고). MCP 서버처럼 *다른* 프로젝트를 대신 찾아야 하는 호출부는 반드시 project_dir을 명시로
    넘길 것 — 안 그러면 이 스크립트가 설치된 플러그인 디렉터리를 프로젝트로 착각한다."""
    project_dir = project_dir or os.path.dirname(os.path.abspath(__file__))
    return os.path.expanduser(
        "~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", project_dir))


TRANSCRIPT_DIR = transcript_dir()  # 하위호환 상수 — print_all() 등 기존 참조부 그대로 동작
BASE_IN = {           # $/MTok, base input. 파생: out=5x, w5m=1.25x, w1h=2x, read=0.1x
    "opus": 5.0,
    "sonnet": 2.0,    # Sonnet 5 도입가; 2026-09-01부터 3.0
    "haiku": 1.0,
    "fable": 10.0,
}
DEFAULT_BASE = 5.0
ACCOUNT = "subscription"   # "subscription" → $는 "동등 API 비용" 참고치
# 2026-08-04 2차 재보정. N=6(세션 5개 유지+1개 추가, turns 84~231). 근거:
# read_thrash(0/0/0.11/0.33/0.50/0.67)·correction(전부 ~0)·verbosity(809~2743)·
# cache_hit(0.94~0.98)·sunk_input(전부 120k 초과, 세션 종료 시점 특성상 정상)는
# 기존값이 여전히 잘 분리해 유지. ctx_growth·many_agents는 재조정:
#  - ctx_growth(1.48~2.67, 중앙값 2.15): 기존 2.00은 애초에 중앙값(2.17) *아래*였던
#    설계 오류 — 임계값이 중앙값보다 낮으면 정의상 세션 과반이 상시발화한다. 3.00으로 상향.
#  - many_agents(0/6/8/8/10/30): 30은 신규 세션(d3b71176, 실험8 표본확대 — PROTOCOL.md에
#    "배치 위임 금지 원칙 예외"로 명시된 의도적 벤치마크, 정상 위임 분포를 대표하지 않음).
#    이를 제외한 "건강한" 상한은 10 — 기존 7은 이미 8/8/10에 상시발화(재조정 전에도
#    미해결이었음, 이번에 처음 확인). 30은 여전히 잡아야 하므로 건강 상한 바로 위인 12로.
# N=6 여전히 작음 — 향후 세션 누적되면 재검토, 특히 many_agents는 outlier 1건에 의존.
# 2026-08-04 3차 재검토(many_agents만): N=6→7(세션 1개 추가, n_agents=0). 분포
# 0/0/6/8/8/10/30 — 새 세션은 0이라 건강 상한(10)·outlier(30) 둘 다 그대로. 발화 1/7(outlier만),
# 변경 없음. 8~10과 12 사이 경계를 실제로 테스트하는 값이 아직 한 건도 없어 결론 유보 — 다음에도
# 근처 값(11~15)이 나와야 판단 가능. many_agents=12 유지.
THRESH = {
    "read_thrash": 0.20,      # 중복 Read 비율 경보 — 실측 분리 양호(0/0/0.11 vs 0.33/0.50/0.67), 유지
    "ctx_growth": 3.00,       # 후반/전반 입력 비율 경보 — 2.00은 중앙값 아래라 상시발화, 관측 최대(2.67) 위로 상향
    "correction": 0.15,       # 교정 메시지 비율 경보 — 실측 전부 0에 가까워 판단 근거 없음, 유지
    "verbosity": 3000,        # 턴당 평균 output 토큰 경보 — 관측 최대(2743) 그대로 유효, 유지
    "cache_hit_low": 0.85,    # 캐시 적중률 하한 — 실측 0.94~0.98이 정상 구간, 유지
    "sunk_input": 120_000,    # 마지막 턴 total_input 이상이면 새 세션 권장 — 실측과 정성판단 일치, 유지
    "many_agents": 12,        # 서브에이전트 다수 — 건강 상한(10, outlier 30 제외) 바로 위로 상향
    "delegation_bash": 3,     # 서브에이전트 1건 내부 Bash 호출 수 — 실험10 패턴(생성→판정→비용측정
                              # 등 다단계를 서브에이전트 1개에 통위임, 오버헤드가 74.1%→11.5% 절감으로
                              # 갉아먹음) 재현 감지용. 아직 미보정(N=1, 실험10 단일 사례) — 향후 실사용
                              # 세션 누적되면 재검토.
}
CORRECTION_MARKERS = [
    "아니 ", "아니,", "그게 아니", "그거 아니", "틀렸", "틀린", "되돌", "취소",
    "undo", "revert", "not that", "actually no", "that's wrong", "no wait",
]
PIVOT_MARKERS = [
    "대신", "차라리", "방향을 바꿔", "방향 전환", "처음부터 다시",
    "다른 방식으로", "다른 방향으로", "그거 말고", "그건 됐고", "말고 다른",
]
PRODUCTION_LOG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "experiments", "production_failures.jsonl")
_DESC_STOPWORDS = {
    "haiku", "sonnet", "opus", "fable", "task", "the", "a", "an", "and", "for", "to", "of", "in",
    "re", "review", "fix", "round", "wave", "final",
}

LAMBDA_OCK = 10.0    # OckScore 로그 페널티 계수
T0_OCK = 10_000      # OckScore 기준 토큰


# ── 단가 ──
def tier_of(model):
    m = (model or "").lower()
    for k in BASE_IN:
        if k in m:
            return k
    return None


def base_price(model):
    return BASE_IN.get(tier_of(model), DEFAULT_BASE)


def record_cost(u, model):
    """5분면 비용($). u = message.usage dict."""
    b = base_price(model) / 1e6
    cc = u.get("cache_creation") or {}
    w5 = cc.get("ephemeral_5m_input_tokens", 0)
    w1 = cc.get("ephemeral_1h_input_tokens", 0)
    if not (w5 or w1):   # 분할 없으면 전체를 5m으로 보수적 처리
        w5 = u.get("cache_creation_input_tokens", 0)
    return (u.get("input_tokens", 0) * b
            + w5 * b * 1.25
            + w1 * b * 2.0
            + u.get("cache_read_input_tokens", 0) * b * 0.1
            + u.get("output_tokens", 0) * b * 5)


def total_input(u):
    return (u.get("input_tokens", 0)
            + u.get("cache_creation_input_tokens", 0)
            + u.get("cache_read_input_tokens", 0))


# ── 라우팅 사다리 추천 ──
AVAILABLE_TIERS = tuple(BASE_IN)  # ("opus", "sonnet", "haiku", "fable") — BASE_IN에 이미 있는 것만


def suggest_tier(has_oracle=False, batch_size=1, semantic_risk=False, high_stakes=False):
    """CLAUDE.md 라우팅 사다리 규칙(15행)을 결정론적으로 적용해 서브에이전트(Agent 도구) 위임
    시 모델 티어를 추천한다. Agent 호출을 가로채거나 모델을 자동으로 바꾸지 않는다 — Claude
    Code에는 그런 개입 지점이 없다(메인 응답이든 서브에이전트 스폰이든, 실행 전에 하네스가
    끼어들어 모델을 재선택해주는 훅이 없음). 위임 여부·모델을 결정하는 건 언제나 호출부
    (어시스턴트)이고, 이 함수는 그 판단에 참고할 근거를 CLAUDE.md/experiments/PROTOCOL.md에
    이미 문서화된 실측 수치 그대로 돌려주는 조언 도구다 — 새로 지어낸 임계값 없음.

    분류축은 자유 텍스트 설명이 아니라 구조화된 플래그다: 실험9에서 프로즈 채점(키워드
    루브릭)이 위양성·위음성을 실측으로 냈으므로, "복잡한지" 판단 자체는 여기서 자동화하지
    않고 호출부가 이미 내린 판단(오라클 유무·배치 크기·의미론적 위험·고위험 여부)을 그대로
    받아 사다리 규칙만 결정론적으로 적용한다.

    인자:
      has_oracle: compile/test/lint/schema 등 값싼 검증 수단이 있는지.
      batch_size: 유사한 반복 작업 건수(오라클 없을 때만 갈림).
      semantic_risk: 튜플 언패킹 LHS 순서 등 실험7이 찾은 Haiku 실패 경계에 해당하는
        미묘한 의미론적 판단이 필요한지.
      high_stakes: 실패 시 되돌리기 어렵거나 비용이 큰지.

    반환: {"tier", "effort", "reason", "escalation"(다음 단계 리스트 또는 None), "note"(부가정보 또는 None)}
    """
    if has_oracle:
        return {
            "tier": "haiku", "effort": "low",
            "reason": ("오라클(compile/test/lint/schema)로 저비용 검증 가능 — 실험8: "
                       "오라클 있는 과제에서 Sonnet 직행 대비 3.09배 저렴, N=30 벤치마크 "
                       "실패율 상한 95% CI ~10%"),
            "escalation": ["haiku(프롬프트 강화 재시도)", "sonnet"],
            "note": None,
        }
    if semantic_risk and high_stakes:
        return {
            "tier": "opus", "effort": "high",
            "reason": ("의미론적 판단(실험7: 튜플 언패킹 LHS 순서 등 Haiku 실패 경계) + "
                       "고위험 + 오라클 없음 — CLAUDE.md '오라클 없고 고위험이면 Sonnet "
                       "이상부터'를 가장 보수적으로 적용"),
            "escalation": None,
            "note": ("Sonnet/Opus의 정확한 경계는 실측 미문서화 — 두 조건이 겹칠 때만 "
                     "보수적으로 Opus, 하나만 해당하면 Sonnet 권장"),
        }
    if semantic_risk or high_stakes:
        return {
            "tier": "sonnet", "effort": "high" if semantic_risk else "default",
            "reason": ("오라클 없음 + (의미론적 판단 또는 고위험) — 실험7이 확인한 Haiku "
                       "실패 경계에 걸릴 수 있어 Sonnet 직행"),
            "escalation": None,
            "note": None,
        }
    if batch_size >= 20:
        return {
            "tier": "haiku", "effort": "low",
            "reason": ("오라클 없어도 대규모 반복(N≥20)+배치판정이면 사다리가 유리 — "
                       "실험9 후속2·6: 0.35~0.44배, 에스컬레이션률 2.86%(Wilson 95% CI "
                       "0.8~9.8%)"),
            "escalation": ["sonnet(배치판정)"],
            "note": "배치 판정 입력은 반드시 원문 그대로 — 요약하면 판정이 오염됨(실험9 후속3 교훈)",
        }
    if batch_size < 10:
        return {
            "tier": "sonnet", "effort": "default",
            "reason": ("오라클 없음 + 소표본(N<10) — 에스컬레이션 1건만 나와도 사다리가 "
                       "베이스라인보다 비싸짐(실험9), Sonnet 직행이 안전"),
            "escalation": None,
            "note": None,
        }
    return {
        "tier": "sonnet", "effort": "default",
        "reason": "오라클 없음 + N 10~19 — 사다리 유·불리 실측 공백 구간, 안전하게 Sonnet 직행",
        "escalation": None,
        "note": "N≥20으로 늘어나면 배치판정 사다리가 유리해질 수 있음(N≥20 조건 참고)",
    }


# ── 파싱 ──
def _text_len(content):
    n = 0
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") in ("text", "thinking"):
                n += len(b.get("text") or b.get("thinking") or "")
    return n


def parse_session(path):
    """JSONL 한 파일 → 구조화 dict."""
    assistants = []   # {usage, model, effort, tools:[names], reads:[paths], out_text, ts}
    users = []        # {text}
    n_agent_spawns = 0
    for line in _read_lines(path):
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get("message")
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role == "assistant":
            u = m.get("usage") or {}
            tools, reads = [], []
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        name = b.get("name")
                        tools.append(name)
                        inp = b.get("input") or {}
                        if name == "Read" and inp.get("file_path"):
                            reads.append(inp["file_path"])
            n_agent_spawns += tools.count("Agent")
            assistants.append({
                "usage": u,
                "model": m.get("model"),
                "effort": d.get("effort"),
                "tools": tools,
                "reads": reads,
                "out_text": _text_len(content),
                "ts": d.get("timestamp"),
            })
        elif role == "user":
            users.append({"text": _flatten_user_text(content), "ts": d.get("timestamp")})
    return {
        "path": path,
        "assistants": assistants,
        "users": users,
        "n_agent_spawns": n_agent_spawns,
    }


def _flatten_user_text(content):
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
    return " ".join(parts)


def _read_lines(path):
    with open(path, "r", errors="replace") as f:
        return f.readlines()


# ── 절대 토큰 절감(hooks/read_guard.py·hooks/grep_trim.py 로그 합산) ──
def token_savings_log_dir():
    """hooks/read_guard.py·hooks/grep_trim.py의 savings_log_dir()와 정확히 같은 경로 규약
    (CLAUDE_PLUGIN_DATA 있으면 그 밑 token_savings/, 없으면 tempdir 공용 폴백) — 어긋나면
    hook이 쓴 로그를 여기서 못 찾는다."""
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    return os.path.join(data_dir, "token_savings") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-token-savings")


def token_savings_for_session(session_id):
    """세션별 절대 토큰 절감(추정) 합계 — 캐시 절감($, cache_savings)과는 다른 지표: 이건
    캐시 적중 여부와 무관하게 애초에 컨텍스트에 안 들어간 토큰(차단된 재독·트림된 grep
    매치)이다. 로그 없으면 0(정상 — 두 hook 다 발화 안 한 세션)."""
    path = os.path.join(token_savings_log_dir(), f"{session_id or ''}.jsonl")
    total = 0
    if session_id and os.path.isfile(path):
        with open(path, "r", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    total += json.loads(line).get("estimated_tokens", 0)
                except Exception:
                    continue
    return total


# ── 4슬롯 게이트 개입 횟수(hooks/prompt_gate.py 로그) ──
def gate_trips_log_dir():
    """hooks/prompt_gate.py의 gate_events_dir()와 정확히 같은 경로 규약."""
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    return os.path.join(data_dir, "gate_events") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-gate-events")


def gate_trips_for_session(session_id):
    """세션별 4슬롯 게이트 개입(트립) 횟수 — 모호한 요청의 첫 도구 호출을 막아 Claude가
    먼저 설명하게 유도한 횟수. token_savings와 별개 지표(토큰 절감이 아니라 개입 횟수)라
    합산하지 않고 독립적으로 리포트한다. 로그 없으면 0(정상 — 게이트가 한 번도 안 걸린 세션)."""
    path = os.path.join(gate_trips_log_dir(), f"{session_id or ''}.jsonl")
    if not session_id or not os.path.isfile(path):
        return 0
    n = 0
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


# ── 라우팅 사다리 실사용 로그(hooks/ladder_gate.py) ──
def ladder_gate_log_dir():
    """hooks/ladder_gate.py의 events_dir()와 정확히 같은 경로 규약. gate_events(prompt_gate
    전용)와는 별도 디렉터리 — 섞으면 gate_trips_for_session()의 카운트가 오염된다."""
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    return os.path.join(data_dir, "ladder_gate_events") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-ladder-gate-events")


def _read_ladder_gate_events(session_id):
    """ladder_gate.py가 기록한 events jsonl을 원본 그대로 파싱(순서는 파일에 쓰인 그대로 —
    정렬은 호출부 책임). 로그 없으면 빈 리스트(정상)."""
    path = os.path.join(ladder_gate_log_dir(), f"{session_id or ''}.jsonl")
    events = []
    if not session_id or not os.path.isfile(path):
        return events
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    return events


def ladder_gate_summary_for_session(session_id):
    """세션별 사다리 실제 적용 요약 — 전부 실제로 일어난 사실만 집계한다(추천 티어·실제
    model·일치 여부). $환산은 여기서 하지 않는다: '다른 티어로 돌렸으면 얼마였을까'는
    실제로 일어나지 않은 대안의 비용을 추정하는 것이라 RTK류 허수 counterfactual 함정과
    같다(README '시장 비교' 참고) — 실 $ 비교는 ladder_gate_cost_comparison() 참고
    (actor_breakdown() 소스의 실측 토큰과 대조, 추정 없음). 로그 없으면 전부 0(정상).

    주의(코드리뷰로 발견, 2026-08-11): `mismatched`는 "추천과 다른 티어로 위임"의 총합일
    뿐, 원인은 못 가른다 — CLAUDE.md 사다리 정책 자체가 "Haiku 실패시 Sonnet으로 상향"을
    명시하므로, 같은 턴에서 추천(haiku)대로 시도했다가 검증 실패로 정당하게 Sonnet으로
    올린 경우도 여기 잡힌다(recommended_tier가 턴 단위로 고정이라 재호출을 구분 못 함).
    "무모한 이탈 건수"로 해석하면 과잉해석 — 그냥 "추천과 실제가 갈린 총 횟수"로 읽을 것."""
    resolutions = matched = mismatched = 0
    tiers = {}
    for rec in _read_ladder_gate_events(session_id):
        resolutions += 1
        tier = rec.get("recommended_tier")
        if tier:
            tiers[tier] = tiers.get(tier, 0) + 1
        m = rec.get("matched")
        if m is True:
            matched += 1
        elif m is False:
            mismatched += 1
    return {"resolutions": resolutions, "matched": matched, "mismatched": mismatched,
            "tiers": tiers}


def _iso_to_epoch(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def ladder_gate_cost_comparison(main_path):
    """ladder_gate 이벤트를 서브에이전트 실측 비용(actor_breakdown 소스인
    _subagent_records())과 타임스탬프로 대조해, 이번 세션에서 '추천대로 위임했을 때'와
    '추천과 다르게 위임했을 때' 각각 실제로 얼마를 썼는지 합산한다. '다른 티어였으면
    얼마였을까'는 절대 추정하지 않는다 — 그건 실제로 일어나지 않은 대안 비용 추정이라
    RTK류 허수 counterfactual 함정(README '시장 비교' 참고)과 같다. 여기 나오는 숫자는
    전부 실제로 청구된(구독이면 동등 API 환산) 실측치뿐이다.

    매칭 방법(근사치 — 로그에 tool_use_id가 없어 정확한 1:1 연결은 불가): ladder_gate.py는
    PreToolUse(Agent) 게이트를 막 통과시킨 직후 이벤트를 기록하므로, 이벤트 ts 이후 가장
    먼저 시작한(아직 안 쓰인) 서브에이전트를 그 이벤트가 만든 위임으로 본다. 이벤트·
    서브에이전트 모두 시간순으로 정렬한 뒤 투 포인터로 순서대로 소비 — matched=None(요청
    모델 미지정, 부모 상속) 이벤트는 레코드를 소비하되 어느 쪽에도 집계하지 않는다(포인터
    정렬을 유지하기 위함). 대응하는 서브에이전트를 못 찾은 이벤트는 unmatched_events로만
    세고 비용 합산에서 제외한다 — 없는 값을 0으로 지어내지 않는다. 로그나 서브에이전트가
    없으면 전부 0(정상)."""
    session_id = session_id_from_path(main_path)
    events = sorted(_read_ladder_gate_events(session_id), key=lambda e: e.get("ts") or 0)
    records = []
    for r in _subagent_records(main_path):
        epoch = _iso_to_epoch(r["start_ts"]) if r.get("start_ts") else None
        if epoch is not None:
            records.append((epoch, r))
    records.sort(key=lambda pair: pair[0])

    matched_n = mismatched_n = unmatched_events = 0
    matched_cost = mismatched_cost = 0.0
    i = 0
    for e in events:
        ts = e.get("ts") or 0
        while i < len(records) and records[i][0] < ts:
            i += 1
        if i >= len(records):
            unmatched_events += 1
            continue
        _, rec = records[i]
        i += 1
        if e.get("matched") is True:
            matched_n += 1
            matched_cost += rec["cost"]
        elif e.get("matched") is False:
            mismatched_n += 1
            mismatched_cost += rec["cost"]
    return {"matched_n": matched_n, "matched_cost": matched_cost,
            "mismatched_n": mismatched_n, "mismatched_cost": mismatched_cost,
            "unmatched_events": unmatched_events}


def session_id_from_path(path):
    return os.path.splitext(os.path.basename(path))[0] if path else None


# ── 집계 ──
def aggregate(sess):
    A = sess["assistants"]
    tot = {"input": 0, "cache_create": 0, "cache_read": 0, "output": 0, "cost": 0.0,
           "cache_savings": 0.0}
    per_turn = []
    for a in A:
        u = a["usage"]
        tot["input"] += u.get("input_tokens", 0)
        tot["cache_create"] += u.get("cache_creation_input_tokens", 0)
        tot["cache_read"] += u.get("cache_read_input_tokens", 0)
        tot["output"] += u.get("output_tokens", 0)
        c = record_cost(u, a["model"])
        tot["cost"] += c
        # 캐시 절감액: cache_read 토큰이 캐시 미스였다면(=fresh input 단가) 들었을 비용 대비
        # 실제로 낸 비용(0.1x)의 차액 = read_tokens × b × (1 - 0.1). 실측 usage 그대로 재계산한
        # 값이라 지어낸 수치 아님(CLAUDE.md 북극성).
        b = base_price(a["model"]) / 1e6
        tot["cache_savings"] += u.get("cache_read_input_tokens", 0) * b * 0.9
        per_turn.append({"total_input": total_input(u),
                         "output": u.get("output_tokens", 0), "cost": c,
                         "ts": a.get("ts")})
    tot["turns"] = len(A)
    tot["total_tokens"] = tot["input"] + tot["cache_create"] + tot["cache_read"] + tot["output"]
    denom = tot["cache_read"] + tot["cache_create"]
    tot["cache_hit"] = (tot["cache_read"] / denom) if denom else 0.0
    return tot, per_turn


def proxies(sess, per_turn):
    A = sess["assistants"]
    U = sess["users"]
    # cache thrash: model/effort 전환 수
    thrash = 0
    for i in range(1, len(A)):
        if A[i]["model"] != A[i - 1]["model"] or A[i]["effort"] != A[i - 1]["effort"]:
            thrash += 1
    # read thrash
    all_reads = [p for a in A for p in a["reads"]]
    dup_reads = len(all_reads) - len(set(all_reads))
    read_thrash = (dup_reads / len(all_reads)) if all_reads else 0.0
    # parallelism
    tool_turns = [a for a in A if a["tools"]]
    multi = [a for a in tool_turns if len(a["tools"]) >= 2]
    parallelism = (len(multi) / len(tool_turns)) if tool_turns else 0.0
    # ctx growth: 후반 1/3 / 전반 1/3
    ti = [t["total_input"] for t in per_turn]
    ctx_growth = _third_ratio(ti)
    # correction ratio
    corr = sum(1 for u in U if _has_marker(u["text"])) if U else 0
    correction = (corr / len(U)) if U else 0.0
    # clarify round-trips: AskUserQuestion 호출 수
    clarify = sum(a["tools"].count("AskUserQuestion") for a in A)
    # verbosity
    outs = [t["output"] for t in per_turn if t["output"]]
    verbosity = (sum(outs) / len(outs)) if outs else 0.0
    # delegation overhead: 서브에이전트 통위임 재발 감지(실험10)
    delegation_hits, delegation_ratio = _delegation_overhead(sess["path"])
    return {
        "cache_thrash": thrash,
        "read_thrash": read_thrash,
        "dup_reads": dup_reads,
        "parallelism": parallelism,
        "ctx_growth": ctx_growth,
        "correction": correction,
        "clarify": clarify,
        "verbosity": verbosity,
        "n_agent_spawns": sess["n_agent_spawns"],
        "delegation_hits": delegation_hits,
        "delegation_ratio": delegation_ratio,
    }


def _third_ratio(xs):
    if len(xs) < 6:
        return 1.0
    k = len(xs) // 3
    first = sum(xs[:k]) / k
    last = sum(xs[-k:]) / k
    return (last / first) if first else 1.0


def _has_marker(text):
    t = (text or "").lower()
    return any(mk in t for mk in CORRECTION_MARKERS)


# ── 효율 점수 & 부검 ──
def efficiency_score(tot, px):
    """0–100. 캐시적중·병렬·낮은 backtracking(=read_thrash)·낮은 correction."""
    parts = [
        tot["cache_hit"],
        px["parallelism"],
        1.0 - min(px["read_thrash"], 1.0),
        1.0 - min(px["correction"], 1.0),
    ]
    return round(100 * sum(parts) / len(parts), 1)


def autopsy(tot, px, per_turn):
    findings = []

    def add(name, sev, detail, tip):
        findings.append({"name": name, "sev": sev, "detail": detail, "tip": tip})

    if px["ctx_growth"] > THRESH["ctx_growth"]:
        add("컨텍스트 비대", "high",
            f"후반 입력이 전반의 {px['ctx_growth']:.1f}배",
            "작업 경계에서 /compact, 대량 탐색은 서브에이전트 위임")
    if px["cache_thrash"] >= 1:
        add("캐시 스래싱", "high",
            f"model/effort 전환 {px['cache_thrash']}회(전환마다 캐시 무효화)",
            "세션 시작 시 모델·effort 고정 후 유지")
    if px["read_thrash"] > THRESH["read_thrash"]:
        add("Read 스래싱", "med",
            f"중복 Read {px['dup_reads']}건({px['read_thrash']*100:.0f}%)",
            "grep으로 위치 먼저, Read는 offset/limit로 필요한 줄만")
    if px["correction"] > THRESH["correction"]:
        add("Rework 캐스케이드", "high",
            f"교정성 메시지 비율 {px['correction']*100:.0f}%",
            "계획-후-실행 + 완료 전 값싼 검증 게이트")
    if tot["cache_hit"] < THRESH["cache_hit_low"] and tot["turns"] > 4:
        add("낮은 캐시 적중", "med",
            f"캐시 적중률 {tot['cache_hit']*100:.0f}%",
            "안정적 컨텍스트를 앞에 고정, 잦은 /clear·전환 자제")
    if px["verbosity"] > THRESH["verbosity"]:
        add("장황 스파이럴", "med",
            f"턴당 평균 output {px['verbosity']:.0f} 토큰",
            "간결 강제·정지 조건(다음단계·한일요약 금지), 필요 추론은 확보")
    if px["n_agent_spawns"] >= THRESH["many_agents"]:
        add("과분해 가능", "low",
            f"서브에이전트 {px['n_agent_spawns']}회 spawn(각 cold-start)",
            "trivial 작업은 하나로 배치 위임(item당 1개 금지)")
    if px["delegation_hits"]:
        n = len(px["delegation_hits"])
        max_bash = max(h["bash_calls"] for h in px["delegation_hits"])
        sev = "high" if px["delegation_ratio"] > 0.30 else "med"
        add("위임 오버헤드 의심", sev,
            f"서브에이전트 {n}건이 내부 Bash {max_bash}회+/중첩 Agent로 자체 오케스트레이션"
            f"(비용비중 {px['delegation_ratio']*100:.0f}%)",
            "다단계 파이프라인 통위임 금지 — 메인이 각 단계를 병렬 직접호출(Agent 여러 콜)로 쪼개고 결과만 회수(실험10)")
    if per_turn and per_turn[-1]["total_input"] > THRESH["sunk_input"]:
        add("Sunk-cost 세션", "med",
            f"마지막 턴 입력 {per_turn[-1]['total_input']:,} 토큰",
            "남은 작업이 작으면 /clear 후 새 세션이 저렴")
    return findings


# ── OckScore ──
def ockscore(quality, tokens):
    return quality - LAMBDA_OCK * math.log(tokens / T0_OCK + 1)


# ── 포맷 ──
def fmt(n):
    return f"{n:,}"


def money(x):
    return f"${x:,.4f}" if x < 1 else f"${x:,.2f}"


def cost_label():
    """구독 계정이면 실제 청구가 아니라는 걸 매 출력에서 명시(리포트에만 붙어있으면
    --diff/--all만 보는 사용자가 실청구액으로 착각할 수 있어 공용 함수로 통일)."""
    return "동등 API 비용(구독=참고치)" if ACCOUNT == "subscription" else "비용"


def latest_session(project_dir=None):
    files = sorted(glob.glob(os.path.join(transcript_dir(project_dir), "*.jsonl")),
                   key=os.path.getmtime)
    return files[-1] if files else None


def discover_task_files(main_path):
    """메인 세션 jsonl 경로 → 서브에이전트 task 트랜스크립트 자동 discovery.
    Claude Code는 <uuid>.jsonl 옆에 <uuid>/subagents/**/agent-*.jsonl(중첩 workflows
    포함)로 저장한다 — 경로 수동 지정 없이 이 구조를 재귀 탐색."""
    base = os.path.splitext(main_path)[0]  # .../<uuid>
    subagents_dir = os.path.join(base, "subagents")
    if not os.path.isdir(subagents_dir):
        return []
    return sorted(glob.glob(os.path.join(subagents_dir, "**", "agent-*.jsonl"), recursive=True))


def _agent_meta(task_path):
    meta_path = task_path[: -len(".jsonl")] + ".meta.json"
    try:
        with open(meta_path, "r", errors="replace") as f:
            return json.load(f)
    except Exception:
        return {}


def actor_breakdown(main_path):
    """메인 + 자동 discover된 서브에이전트 task 파일을 행위자(agentType)별로 집계."""
    main_tot, _ = aggregate(parse_session(main_path))
    rows = [{"label": "메인 세션", "turns": main_tot["turns"],
              "tokens": main_tot["total_tokens"], "cost": main_tot["cost"]}]
    by_type = {}
    for tp in discover_task_files(main_path):
        meta = _agent_meta(tp)
        tot, _ = aggregate(parse_session(tp))
        key = meta.get("agentType") or "unknown"
        agg = by_type.setdefault(key, {"n": 0, "turns": 0, "tokens": 0, "cost": 0.0})
        agg["n"] += 1
        agg["turns"] += tot["turns"]
        agg["tokens"] += tot["total_tokens"]
        agg["cost"] += tot["cost"]
    for key, agg in sorted(by_type.items(), key=lambda kv: -kv[1]["cost"]):
        rows.append({"label": f"서브에이전트({key}) x{agg['n']}", "turns": agg["turns"],
                      "tokens": agg["tokens"], "cost": agg["cost"]})
    grand_tokens = sum(r["tokens"] for r in rows)
    grand_cost = sum(r["cost"] for r in rows)
    return rows, grand_tokens, grand_cost


def _delegation_overhead(main_path):
    """실험10 패턴 감지: 서브에이전트 1건이 내부에서 Bash를 여러 번 호출하거나
    중첩 Agent를 스폰해 스스로 다단계 파이프라인(생성→판정→비용측정 등)을
    수행 중인 경우. 이런 '통위임'은 컨텐츠만 봤을 때의 절감률을 오버헤드가
    크게 갉아먹는 게 실측됨(74.1%→11.5%, 실험10) — 사후 감지용, 판정 아님."""
    hits = []
    total_cost = 0.0
    overhead_cost = 0.0
    for tp in discover_task_files(main_path):
        sess = parse_session(tp)
        if not sess["assistants"]:
            continue
        tot, _ = aggregate(sess)
        total_cost += tot["cost"]
        bash_calls = sum(a["tools"].count("Bash") for a in sess["assistants"])
        nested_agents = sum(a["tools"].count("Agent") for a in sess["assistants"])
        if bash_calls >= THRESH["delegation_bash"] or nested_agents >= 1:
            overhead_cost += tot["cost"]
            meta = _agent_meta(tp)
            hits.append({"agent_type": meta.get("agentType") or "unknown",
                         "bash_calls": bash_calls, "nested_agents": nested_agents,
                         "cost": tot["cost"]})
    ratio = (overhead_cost / total_cost) if total_cost else 0.0
    return hits, ratio


def _desc_tokens(desc):
    """단어 토큰화 + stopword 제거. 숫자 토큰(1자리 포함)은 stopword·길이 필터를 건너뛰고
    항상 보존한다 — 안 그러면 "Task 2"/"Task 3"처럼 정형 문구에서 유일하게 다른 부분이
    한 자리 숫자뿐인 서로 다른 태스크가 boilerplate만 남아 자카드 1.0으로 오탐된다(실측,
    2026-08-12 — 실험13이 남긴 잔여 오탐, production_failures.jsonl 실사용 확인)."""
    words = re.findall(r"[a-z0-9가-힣]+", (desc or "").lower())
    return {w for w in words if w.isdigit() or (w not in _DESC_STOPWORDS and len(w) > 1)}


def _similar_desc(a, b):
    ta, tb = _desc_tokens(a), _desc_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.7


def _subagent_records(main_path):
    """서브에이전트 task 파일 → 실패 후보 스캔용 레코드(모델·설명·타임스탬프·비용)."""
    out = []
    for tp in discover_task_files(main_path):
        meta = _agent_meta(tp)
        sess = parse_session(tp)
        A = sess["assistants"]
        if not A:
            continue
        tot, _ = aggregate(sess)
        out.append({
            "tool_use_id": meta.get("toolUseId") or tp,
            "agent_type": meta.get("agentType"),
            "description": meta.get("description") or "",
            "model": meta.get("model") or A[0]["model"],
            "tier": tier_of(meta.get("model") or A[0]["model"]),
            "tokens": tot["total_tokens"],
            "cost": tot["cost"],
            "start_ts": A[0]["ts"],
            "end_ts": A[-1]["ts"],
        })
    out.sort(key=lambda r: r["end_ts"] or "")
    return out


def _load_dedup_keys(log_path):
    keys = set()
    if os.path.exists(log_path):
        for line in _read_lines(log_path):
            try:
                keys.add(json.loads(line).get("dedup_key"))
            except Exception:
                continue
    return keys


def capture_failures(main_path, log_path=None):
    """실사용 중 Haiku 1차 시도 실패 후보(에스컬레이션·사용자 교정)를 감지해 로그에 누적.
    신호 1: Haiku 서브에이전트 뒤에 설명이 유사한 상위 모델 서브에이전트가 뒤따름(재위임).
    신호 2: Haiku 서브에이전트 직후 사용자 메시지에 교정/방향전환 마커.
    확정 판정이 아니라 사후 수동 검토용 후보 수집이다(합성 벤치마크 대신 실사용 사례 축적)."""
    log_path = log_path or PRODUCTION_LOG
    records = _subagent_records(main_path)
    if not records:
        return []
    existing = _load_dedup_keys(log_path)
    session_label = os.path.basename(main_path)
    candidates = []

    for i, ri in enumerate(records):
        if ri["tier"] != "haiku":
            continue
        if "baseline" in ri["description"].lower():
            continue
        for rj in records[i + 1:]:
            if "baseline" in rj["description"].lower():
                continue  # 의도적 A/B 비교(실험) — 실패로 인한 재위임이 아님
            if rj["tier"] == "haiku":
                break  # 진짜 haiku가 먼저 오면 그 이후 에스컬레이션은 그 haiku 소관 —
                       # 무관한 더 이전 haiku(ri)까지 같은 에스컬레이션에 중복 매칭 방지
                       # (user_correction_follow와 같은 클래스 버그, 2026-08-11 발견·수정)
            if rj["tier"] in ("sonnet", "opus", "fable") and _similar_desc(ri["description"], rj["description"]):
                key = f"esc:{ri['tool_use_id']}:{rj['tool_use_id']}"
                if key not in existing:
                    candidates.append({
                        "dedup_key": key, "type": "escalation_pair", "session": session_label,
                        "haiku_task": {k: ri[k] for k in ("description", "tokens", "cost", "end_ts")},
                        "escalated_task": {"model": rj["model"], "description": rj["description"],
                                            "tokens": rj["tokens"], "cost": rj["cost"]},
                    })
                    existing.add(key)
                break

    main_sess = parse_session(main_path)
    user_msgs = sorted(
        (u for u in main_sess["users"] if u.get("ts")), key=lambda u: u["ts"])
    user_msgs = [u for u in user_msgs if not u["text"].lstrip().startswith("<task-notification>")]
    haiku_starts = sorted(
        r["start_ts"] for r in records if r["tier"] == "haiku" and r.get("start_ts"))
    for ri in records:
        if ri["tier"] != "haiku" or not ri["end_ts"]:
            continue
        # 매칭 폭을 "다음 haiku 위임이 시작되기 전까지"로 좁힌다(HANDOFF.md 11차 처방#2,
        # 2026-08-11 구현) — 그냥 "그 뒤 첫 사용자 메시지"만 보면, haiku 여러 건이 순차
        # 실행되고 그 뒤에 진짜 교정 메시지가 하나만 왔을 때 그 메시지가 모든 haiku
        # 레코드에 중복 매칭된다(실측 137/137은 task-notification 필터로 이미 걸렀지만,
        # 진짜 사용자 발화가 여러 haiku에 중복 매칭되는 잔여 리스크는 남아 있었음).
        upper_bound = next((s for s in haiku_starts if s > ri["end_ts"]), None)
        nxt = next((u for u in user_msgs
                    if u["ts"] > ri["end_ts"] and (upper_bound is None or u["ts"] < upper_bound)),
                   None)
        if not nxt:
            continue
        text = nxt["text"]
        matched = _has_marker(text) or any(pm in text for pm in PIVOT_MARKERS)
        if matched:
            key = f"corr:{ri['tool_use_id']}"
            if key not in existing:
                candidates.append({
                    "dedup_key": key, "type": "user_correction_follow", "session": session_label,
                    "haiku_task": {k: ri[k] for k in ("description", "tokens", "cost", "end_ts")},
                    "user_text_snippet": text[:120],
                })
                existing.add(key)

    if candidates:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            for c in candidates:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return candidates


def print_report(path):
    sess = parse_session(path)
    tot, per_turn = aggregate(sess)
    px = proxies(sess, per_turn)
    score = efficiency_score(tot, px)
    print(f"\n== 세션 리포트 ==  {os.path.basename(path)}")
    print(f"  턴(assistant): {tot['turns']}   효율 점수: {score}/100")
    print(f"  토큰  input={fmt(tot['input'])}  cache_create={fmt(tot['cache_create'])}"
          f"  cache_read={fmt(tot['cache_read'])}  output={fmt(tot['output'])}")
    print(f"  총 토큰: {fmt(tot['total_tokens'])}   캐시 적중률: {tot['cache_hit']*100:.0f}%")
    print(f"  {cost_label()}: {money(tot['cost'])}   캐시 절감: {money(tot['cache_savings'])}")
    blocked = token_savings_for_session(session_id_from_path(path))
    print(f"  차단·트림으로 애초에 컨텍스트에 안 들어간 토큰(추정): ~{fmt(blocked)}tok"
          f"  [read_guard 재독 차단 + grep_trim 트림 합산]")
    trips = gate_trips_for_session(session_id_from_path(path))
    print(f"  4슬롯 게이트 개입: {trips}회  [prompt_gate가 모호한 요청의 첫 도구 호출을 막은 횟수]")
    ladder = ladder_gate_summary_for_session(session_id_from_path(path))
    if ladder["resolutions"]:
        tiers_str = ", ".join(f"{k}×{v}" for k, v in sorted(ladder["tiers"].items()))
        print(f"  사다리 실적용: {ladder['resolutions']}회(추천대로 {ladder['matched']}·"
              f"추천과 다름 {ladder['mismatched']}·모름 "
              f"{ladder['resolutions']-ladder['matched']-ladder['mismatched']})  "
              f"추천분포: {tiers_str}  [ladder_gate 실측, $환산 안 함 — '다름'엔 정당한 "
              f"검증실패 후 상향도 포함, 무모한 이탈로 오독 금지]")
        cmp = ladder_gate_cost_comparison(path)
        if cmp["matched_n"] or cmp["mismatched_n"]:
            unmatched_note = f" · 대응 못한 이벤트 {cmp['unmatched_events']}건" if cmp["unmatched_events"] else ""
            print(f"    실측 $ 대조: 추천대로 위임 {cmp['matched_n']}건 {money(cmp['matched_cost'])}"
                  f" · 추천과 다르게 위임 {cmp['mismatched_n']}건 {money(cmp['mismatched_cost'])}"
                  f"{unmatched_note}  [타임스탬프 근사 매칭, '다른 티어였으면' 추정 아님]")
    print(f"  프록시  병렬={px['parallelism']*100:.0f}%  read_thrash={px['read_thrash']*100:.0f}%"
          f"  correction={px['correction']*100:.0f}%  clarify={px['clarify']}"
          f"  verbosity={px['verbosity']:.0f}/턴  agents={px['n_agent_spawns']}")
    rows, grand_tokens, grand_cost = actor_breakdown(path)
    print(f"  행위자별 분해 (task 파일 자동 discover, 서브에이전트 그룹 {len(rows) - 1}개):")
    for r in rows:
        print(f"    {r['label']:<26} 턴={r['turns']:<4} 토큰={fmt(r['tokens']):>12}  {money(r['cost'])}")
    if len(rows) > 1:
        print(f"    합계(메인+서브)              토큰={fmt(grand_tokens):>12}  {money(grand_cost)}")


def autopsy_text(path):
    """세션 낭비 부검 리포트 문자열. print_autopsy()·MCP 서버 공용."""
    if not path or not os.path.isfile(path):
        return ""
    sess = parse_session(path)
    tot, per_turn = aggregate(sess)
    px = proxies(sess, per_turn)
    finds = autopsy(tot, px, per_turn)
    lines = [f"\n== 낭비 부검 ==  {os.path.basename(path)}"]
    if not finds:
        lines.append("  이상 신호 없음. 효율 양호.")
    else:
        for f in finds:
            lines.append(f"  [{f['sev'].upper():4}] {f['name']}: {f['detail']}")
            lines.append(f"         → {f['tip']}")
    return "\n".join(lines)


def print_autopsy(path):
    text = autopsy_text(path)
    if text:
        print(text)


def print_diff(a, b):
    ta, _ = aggregate(parse_session(a))
    tb, _ = aggregate(parse_session(b))
    print(f"\n== 세션 비교 ==")
    print(f"  {'지표':18} {'A':>14} {'B':>14}")
    for key, label in [("turns", "턴"), ("total_tokens", "총 토큰"),
                       ("output", "output"), ("cache_read", "cache_read")]:
        print(f"  {label:18} {fmt(ta[key]):>14} {fmt(tb[key]):>14}")
    print(f"  {'캐시 적중률':16} {ta['cache_hit']*100:>13.0f}% {tb['cache_hit']*100:>13.0f}%")
    print(f"  {cost_label():18} {money(ta['cost']):>14} {money(tb['cost']):>14}")
    if ta["total_tokens"]:
        save = (1 - tb["total_tokens"] / ta["total_tokens"]) * 100
        print(f"  → B는 A 대비 총 토큰 {save:+.0f}%")


def print_all():
    files = sorted(glob.glob(os.path.join(TRANSCRIPT_DIR, "*.jsonl")),
                   key=os.path.getmtime)
    if not files:
        print("세션 없음.")
        return
    print(f"\n== 세션 간 추세 ==  ({len(files)} 세션, {cost_label()})")
    print(f"  {'세션':22} {'턴':>5} {'총토큰':>12} {'적중%':>6} {'효율':>5} {'비용':>10}")
    tot_tokens = tot_cost = tot_cache_savings = tot_blocked = tot_trips = 0
    tot_ladder_resolutions = tot_ladder_matched = 0
    hits = []
    for p in files:
        sess = parse_session(p)
        tot, per_turn = aggregate(sess)
        px = proxies(sess, per_turn)
        sc = efficiency_score(tot, px)
        tot_tokens += tot["total_tokens"]
        tot_cost += tot["cost"]
        tot_cache_savings += tot["cache_savings"]
        tot_blocked += token_savings_for_session(session_id_from_path(p))
        tot_trips += gate_trips_for_session(session_id_from_path(p))
        ladder = ladder_gate_summary_for_session(session_id_from_path(p))
        tot_ladder_resolutions += ladder["resolutions"]
        tot_ladder_matched += ladder["matched"]
        hits.append(tot["cache_hit"])
        print(f"  {os.path.basename(p)[:22]:22} {tot['turns']:>5} "
              f"{fmt(tot['total_tokens']):>12} {tot['cache_hit']*100:>5.0f}% "
              f"{sc:>5} {money(tot['cost']):>10}")
    avg_hit = sum(hits) / len(hits) if hits else 0
    print(f"  {'—합계/평균':22} {'':>5} {fmt(tot_tokens):>12} "
          f"{avg_hit*100:>5.0f}% {'':>5} {money(tot_cost):>10}")
    print(f"  누적 캐시 절감: {money(tot_cache_savings)}   "
          f"누적 차단·트림 절감(추정): ~{fmt(tot_blocked)}tok   "
          f"누적 게이트 개입: {tot_trips}회")
    if tot_ladder_resolutions:
        print(f"  누적 사다리 실적용: {tot_ladder_resolutions}회(추천대로 {tot_ladder_matched}) "
              f"[ladder_gate 실측, $환산 안 함]")


def _pace_line(per_turn):
    """실측 시간당 소비 속도 — 계정의 실제 5시간/주간 한도는 서버 쪽 상태라 로컬에서 절대 알
    수 없다(HANDOFF.md 12차 후속: policy-limits.json엔 quota 없음, CLI에도 usage 조회 커맨드
    없음 확인됨). 하지만 "이 세션이 지금까지 실제로 얼마나 빨리 토큰을 쓰고 있는지"는 transcript
    타임스탬프로 정확히 계산 가능한 실측값이다. 잔여 한도%처럼 지어낸 수치를 보여주는 대신,
    관측된 페이스를 그대로 보여줘서 사용자가 스스로 조절하게 하는 것이 목적 — THRESH처럼 발화
    임계값을 보정한 게 아니라 항상 뜨는 정보성 라인(경고 아님)."""
    stamped = [t for t in per_turn if t.get("ts")]
    if len(stamped) < 2:
        return None
    try:
        t0 = datetime.datetime.fromisoformat(stamped[0]["ts"].replace("Z", "+00:00"))
        t1 = datetime.datetime.fromisoformat(stamped[-1]["ts"].replace("Z", "+00:00"))
    except Exception:
        return None
    elapsed_h = (t1 - t0).total_seconds() / 3600
    if elapsed_h < 0.05:  # 3분 미만은 속도 추정이 노이즈에 지배됨 — 표시 안 함
        return None
    total = sum(t["total_input"] + t["output"] for t in stamped)
    rate = int(total / elapsed_h)
    if elapsed_h >= 5:
        return f"⏱️ 세션 경과 {elapsed_h:.1f}시간(5시간 초과) · 페이스 {fmt(rate)}tok/h"
    return f"⏱️ 페이스 {fmt(rate)}tok/h(이 속도로 5시간 채우면 ~{fmt(rate * 5)}tok, 실측 기반 추정)"


def _coaching_warnings(tot, per_turn):
    """컨텍스트 비대·캐시 적중 저하 경고 목록 + 페이스 정보 라인. check_line()·do_statusline()
    공용 — statusLine이 hook보다 사용자에게 실제로 보이는 유일한 경로이므로(HANDOFF.md 10차
    근본 설계 오류 참고), 같은 내용을 두 채널 모두에 실어야 사용자가 실제로 볼 수 있다."""
    warnings = []
    last = per_turn[-1]["total_input"]
    if last > THRESH["sunk_input"]:
        warnings.append(f"⚠️ 컨텍스트 {last:,} 토큰 — 작업 경계면 /compact, 무관 작업이면 /clear 권장")
    if tot["cache_hit"] < THRESH["cache_hit_low"] and tot["turns"] > 6:
        warnings.append(f"⚠️ 캐시 적중률 {tot['cache_hit']*100:.0f}% — 모델·effort 전환 자제")
    pace = _pace_line(per_turn)
    if pace:
        warnings.append(pace)
    return warnings


def statusline_text(path):
    """do_statusline()·MCP token_saver_check 공용 — 캐시절감·차단절감까지 포함한 완전한 한 줄.
    check_line()(hook 전용, 어시스턴트 컨텍스트에만 들어가는 비가시 채널이라 절감 세그먼트
    없이 간결하게 유지)과는 별개 포맷 — 이쪽은 실제 사람 눈에 보이는 두 경로(statusLine,
    Desktop MCP) 전용이라 '체감'에 필요한 정보를 전부 싣는다."""
    if not path or not os.path.isfile(path):
        return "token: n/a"
    tot, per_turn = aggregate(parse_session(path))
    line = (f"⟢ {fmt(tot['total_tokens'])} tok · hit {tot['cache_hit']*100:.0f}% "
            f"· {money(tot['cost'])} · 캐시절감 {money(tot['cache_savings'])} · {tot['turns']}턴")
    blocked = token_savings_for_session(session_id_from_path(path))
    if blocked:
        line += f" · 차단절감 ~{fmt(blocked)}tok(추정)"
    trips = gate_trips_for_session(session_id_from_path(path))
    if trips:
        line += f" · 게이트개입 {trips}회"
    ladder = ladder_gate_summary_for_session(session_id_from_path(path))
    if ladder["resolutions"]:
        line += f" · 사다리 {ladder['resolutions']}회(추천대로 {ladder['matched']})"
    if per_turn:
        line = " ".join([line] + _coaching_warnings(tot, per_turn))
    return line


def do_statusline():
    """stdin JSON(transcript_path 포함) → 한 줄. UserPromptSubmit hook과 달리 statusLine은
    설치 즉시 사용자 화면에 실제로 뜨는 유일한 경로라, 경고도 여기 실어야 사용자가 본다."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    path = payload.get("transcript_path") or latest_session()
    print(statusline_text(path))


def _session_totals(path):
    """parse_session + aggregate 공용 헬퍼 — check_line()과 do_check()가 같은 파일을 각자
    두 번 파싱하지 않도록 분리(2026-08-10, do_check()의 systemMessage 노출 추가하며 리팩터).
    파일 없음/빈 세션이면 None."""
    if not path or not os.path.isfile(path):
        return None
    sess = parse_session(path)
    tot, per_turn = aggregate(sess)
    if not per_turn:
        return None
    return sess, tot, per_turn


def check_line(path):
    """세션 효율 한 줄(+조건부 경고) 문자열. 없으면 "". do_check()·MCP 서버 공용.
    이 문자열 자체는 (do_check()가 hookSpecificOutput.additionalContext로 감싸 어시스턴트
    컨텍스트에 주입하므로) 사용자 화면에는 뜨지 않는다 — 사용자에게 보이는 경고는
    do_statusline()의 _coaching_warnings() 또는 do_check()의 systemMessage 몫."""
    data = _session_totals(path)
    if not data:
        return ""
    sess, tot, per_turn = data
    px = proxies(sess, per_turn)
    score = efficiency_score(tot, px)
    msgs = [f"⟢ 턴{tot['turns']} · {fmt(tot['total_tokens'])}tok · "
            f"hit {tot['cache_hit']*100:.0f}% · {money(tot['cost'])} · 효율{score:.0f}"]
    msgs.extend(_coaching_warnings(tot, per_turn))
    return " ".join(msgs)


def do_check():
    """UserPromptSubmit hook용: stdin JSON -> Claude 컨텍스트 주입(hookSpecificOutput.
    additionalContext, 기존 plain-stdout과 동일 효과) + 경고가 있으면 top-level
    systemMessage로 사용자 화면에도 직접 노출(2026-08-10 추가).

    공식 hooks 스키마(code.claude.com/docs/en/hooks)에 systemMessage는 전체 이벤트 공통
    필드로 명시돼 있고, Claude 컨텍스트가 아니라 사용자 화면에 직접 렌더링된다 — "설치만으로는
    statusLine 없이 아무것도 안 보인다"였던 기존 제한사항을 경고에 한해 해소할 수 있는 경로.
    '⟢' 요약 라인 전체를 매 턴 그대로 노출하면 statusLine 대체품처럼 스팸이 되므로,
    _coaching_warnings()가 실제로 뭔가 있을 때만 systemMessage를 싣는다. 실사용 세션에서
    실제 렌더링 여부는 아직 미검증(신규) — 확인되면 README "알려진 제한사항" 갱신."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    path = payload.get("transcript_path") or latest_session()
    data = _session_totals(path)
    if not data:
        return
    sess, tot, per_turn = data
    px = proxies(sess, per_turn)
    score = efficiency_score(tot, px)
    warnings = _coaching_warnings(tot, per_turn)
    line = " ".join([f"⟢ 턴{tot['turns']} · {fmt(tot['total_tokens'])}tok · "
                      f"hit {tot['cache_hit']*100:.0f}% · {money(tot['cost'])} · 효율{score:.0f}"]
                     + warnings)
    out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": line}}
    if warnings:
        out["systemMessage"] = " ".join(warnings)
    print(json.dumps(out))


def capture_failures_text(path, data_dir=None):
    """실패 후보 포착 요약 문자열. 없으면 "". do_capture_failures()·MCP 서버 공용.
    data_dir이 주어지면(플러그인 설치 시 ${CLAUDE_PLUGIN_DATA}) 그 경로에 쓴다 —
    ${CLAUDE_PLUGIN_ROOT}는 플러그인 업데이트마다 바뀌는 임시 경로라 로그 유실 위험이 있어서다."""
    path = path or latest_session()
    if not path or not os.path.isfile(path):
        return ""
    log_path = os.path.join(data_dir, "production_failures.jsonl") if data_dir else None
    candidates = capture_failures(path, log_path=log_path)
    if not candidates:
        return ""
    kinds = {}
    for c in candidates:
        kinds[c["type"]] = kinds.get(c["type"], 0) + 1
    detail = ", ".join(f"{k}×{v}" for k, v in kinds.items())
    return f"📋 실패 후보 {len(candidates)}건 포착({detail}) → {log_path or PRODUCTION_LOG}"


def do_capture_failures(path, data_dir=None):
    text = capture_failures_text(path, data_dir=data_dir)
    if text:
        print(text)


def suggest_tier_text(has_oracle=False, batch_size=1, semantic_risk=False, high_stakes=False):
    """suggest_tier()의 사람이 읽는 한 줄 요약. do_suggest_tier()·MCP 서버 공용."""
    rec = suggest_tier(has_oracle=has_oracle, batch_size=batch_size,
                        semantic_risk=semantic_risk, high_stakes=high_stakes)
    line = f"추천: {rec['tier']}(effort={rec['effort']}) — {rec['reason']}"
    if rec["escalation"]:
        line += f" · 실패 시: {' → '.join(rec['escalation'])}"
    if rec["note"]:
        line += f" · 참고: {rec['note']}"
    return line


def do_suggest_tier(has_oracle, batch_size, semantic_risk, high_stakes):
    print(suggest_tier_text(has_oracle=has_oracle, batch_size=batch_size,
                             semantic_risk=semantic_risk, high_stakes=high_stakes))


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("session", nargs="?", help="세션 JSONL 경로(기본: 최신)")
    ap.add_argument("--autopsy", action="store_true")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--statusline", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--capture-failures", action="store_true")
    ap.add_argument("--data-dir", help="production_failures.jsonl을 쓸 영속 디렉터리(플러그인 설치 시 ${CLAUDE_PLUGIN_DATA})")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--quality", type=float)
    ap.add_argument("--tokens", type=int)
    ap.add_argument("--suggest-tier", action="store_true", help="서브에이전트 위임 시 모델 티어 추천(라우팅 사다리)")
    ap.add_argument("--oracle", action="store_true", help="compile/test/lint/schema 등 값싼 검증 수단 있음")
    ap.add_argument("--batch-size", type=int, default=1, help="유사 반복 작업 건수(기본 1)")
    ap.add_argument("--semantic-risk", action="store_true", help="튜플 언패킹 등 미묘한 의미론적 판단 필요(실험7)")
    ap.add_argument("--high-stakes", action="store_true", help="실패 시 되돌리기 어렵거나 비용 큼")
    args = ap.parse_args()

    if args.suggest_tier:
        return do_suggest_tier(args.oracle, args.batch_size, args.semantic_risk, args.high_stakes)
    if args.statusline:
        return do_statusline()
    if args.check:
        return do_check()
    if args.capture_failures:
        return do_capture_failures(args.session or latest_session(), data_dir=args.data_dir)
    if args.all:
        return print_all()
    if args.diff:
        return print_diff(args.diff[0], args.diff[1])
    if args.score:
        if args.quality is None or args.tokens is None:
            print("--score 는 --quality Q --tokens N 필요")
            return
        print(f"OckScore = {ockscore(args.quality, args.tokens):.2f}   "
              f"quality/1k = {args.quality/(args.tokens/1000):.4f}")
        return

    path = args.session or latest_session()
    if not path:
        print(f"세션 JSONL 없음: {TRANSCRIPT_DIR}")
        return
    if args.autopsy:
        print_autopsy(path)
    else:
        print_report(path)
        print_autopsy(path)


if __name__ == "__main__":
    main()
