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
"""
import json
import sys
import os
import glob
import math
import argparse
import re

# ── config (단가는 2026-08 공식 pricing 기준; 런타임 재확인 권장) ──
TRANSCRIPT_DIR = os.path.expanduser(
    "~/.claude/projects/-Volumes-Extreme-SSD-token-test")
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
THRESH = {
    "read_thrash": 0.20,      # 중복 Read 비율 경보 — 실측 분리 양호(0/0/0.11 vs 0.33/0.50/0.67), 유지
    "ctx_growth": 3.00,       # 후반/전반 입력 비율 경보 — 2.00은 중앙값 아래라 상시발화, 관측 최대(2.67) 위로 상향
    "correction": 0.15,       # 교정 메시지 비율 경보 — 실측 전부 0에 가까워 판단 근거 없음, 유지
    "verbosity": 3000,        # 턴당 평균 output 토큰 경보 — 관측 최대(2743) 그대로 유효, 유지
    "cache_hit_low": 0.85,    # 캐시 적중률 하한 — 실측 0.94~0.98이 정상 구간, 유지
    "sunk_input": 120_000,    # 마지막 턴 total_input 이상이면 새 세션 권장 — 실측과 정성판단 일치, 유지
    "many_agents": 12,        # 서브에이전트 다수 — 건강 상한(10, outlier 30 제외) 바로 위로 상향
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


# ── 집계 ──
def aggregate(sess):
    A = sess["assistants"]
    tot = {"input": 0, "cache_create": 0, "cache_read": 0, "output": 0, "cost": 0.0}
    per_turn = []
    for a in A:
        u = a["usage"]
        tot["input"] += u.get("input_tokens", 0)
        tot["cache_create"] += u.get("cache_creation_input_tokens", 0)
        tot["cache_read"] += u.get("cache_read_input_tokens", 0)
        tot["output"] += u.get("output_tokens", 0)
        c = record_cost(u, a["model"])
        tot["cost"] += c
        per_turn.append({"total_input": total_input(u),
                         "output": u.get("output_tokens", 0), "cost": c})
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


def latest_session():
    files = sorted(glob.glob(os.path.join(TRANSCRIPT_DIR, "*.jsonl")),
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


def _desc_tokens(desc):
    words = re.findall(r"[a-z0-9가-힣]+", (desc or "").lower())
    return {w for w in words if w not in _DESC_STOPWORDS and len(w) > 1}


def _similar_desc(a, b):
    ta, tb = _desc_tokens(a), _desc_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.5


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
    for ri in records:
        if ri["tier"] != "haiku" or not ri["end_ts"]:
            continue
        nxt = next((u for u in user_msgs if u["ts"] > ri["end_ts"]), None)
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
    note = "동등 API 비용(구독=참고치)" if ACCOUNT == "subscription" else "비용"
    print(f"\n== 세션 리포트 ==  {os.path.basename(path)}")
    print(f"  턴(assistant): {tot['turns']}   효율 점수: {score}/100")
    print(f"  토큰  input={fmt(tot['input'])}  cache_create={fmt(tot['cache_create'])}"
          f"  cache_read={fmt(tot['cache_read'])}  output={fmt(tot['output'])}")
    print(f"  총 토큰: {fmt(tot['total_tokens'])}   캐시 적중률: {tot['cache_hit']*100:.0f}%")
    print(f"  {note}: {money(tot['cost'])}")
    print(f"  프록시  병렬={px['parallelism']*100:.0f}%  read_thrash={px['read_thrash']*100:.0f}%"
          f"  correction={px['correction']*100:.0f}%  clarify={px['clarify']}"
          f"  verbosity={px['verbosity']:.0f}/턴  agents={px['n_agent_spawns']}")
    rows, grand_tokens, grand_cost = actor_breakdown(path)
    print(f"  행위자별 분해 (task 파일 자동 discover, 서브에이전트 그룹 {len(rows) - 1}개):")
    for r in rows:
        print(f"    {r['label']:<26} 턴={r['turns']:<4} 토큰={fmt(r['tokens']):>12}  {money(r['cost'])}")
    if len(rows) > 1:
        print(f"    합계(메인+서브)              토큰={fmt(grand_tokens):>12}  {money(grand_cost)}")


def print_autopsy(path):
    sess = parse_session(path)
    tot, per_turn = aggregate(sess)
    px = proxies(sess, per_turn)
    finds = autopsy(tot, px, per_turn)
    print(f"\n== 낭비 부검 ==  {os.path.basename(path)}")
    if not finds:
        print("  이상 신호 없음. 효율 양호.")
        return
    for f in finds:
        print(f"  [{f['sev'].upper():4}] {f['name']}: {f['detail']}")
        print(f"         → {f['tip']}")


def print_diff(a, b):
    ta, _ = aggregate(parse_session(a))
    tb, _ = aggregate(parse_session(b))
    print(f"\n== 세션 비교 ==")
    print(f"  {'지표':18} {'A':>14} {'B':>14}")
    for key, label in [("turns", "턴"), ("total_tokens", "총 토큰"),
                       ("output", "output"), ("cache_read", "cache_read")]:
        print(f"  {label:18} {fmt(ta[key]):>14} {fmt(tb[key]):>14}")
    print(f"  {'캐시 적중률':16} {ta['cache_hit']*100:>13.0f}% {tb['cache_hit']*100:>13.0f}%")
    print(f"  {'비용':18} {money(ta['cost']):>14} {money(tb['cost']):>14}")
    if ta["total_tokens"]:
        save = (1 - tb["total_tokens"] / ta["total_tokens"]) * 100
        print(f"  → B는 A 대비 총 토큰 {save:+.0f}%")


def print_all():
    files = sorted(glob.glob(os.path.join(TRANSCRIPT_DIR, "*.jsonl")),
                   key=os.path.getmtime)
    if not files:
        print("세션 없음.")
        return
    print(f"\n== 세션 간 추세 ==  ({len(files)} 세션)")
    print(f"  {'세션':22} {'턴':>5} {'총토큰':>12} {'적중%':>6} {'효율':>5} {'비용':>10}")
    tot_tokens = tot_cost = 0
    hits = []
    for p in files:
        sess = parse_session(p)
        tot, per_turn = aggregate(sess)
        px = proxies(sess, per_turn)
        sc = efficiency_score(tot, px)
        tot_tokens += tot["total_tokens"]
        tot_cost += tot["cost"]
        hits.append(tot["cache_hit"])
        print(f"  {os.path.basename(p)[:22]:22} {tot['turns']:>5} "
              f"{fmt(tot['total_tokens']):>12} {tot['cache_hit']*100:>5.0f}% "
              f"{sc:>5} {money(tot['cost']):>10}")
    avg_hit = sum(hits) / len(hits) if hits else 0
    print(f"  {'—합계/평균':22} {'':>5} {fmt(tot_tokens):>12} "
          f"{avg_hit*100:>5.0f}% {'':>5} {money(tot_cost):>10}")


def do_statusline():
    """stdin JSON(transcript_path 포함) → 한 줄."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    path = payload.get("transcript_path") or latest_session()
    if not path or not os.path.exists(path):
        print("token: n/a")
        return
    tot, per_turn = aggregate(parse_session(path))
    print(f"⟢ {fmt(tot['total_tokens'])} tok · hit {tot['cache_hit']*100:.0f}% "
          f"· {money(tot['cost'])} · {tot['turns']}턴")


def do_check():
    """UserPromptSubmit hook용: stdin JSON → 컨텍스트/캐시 경고 한 줄(넘을 때만)."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    path = payload.get("transcript_path") or latest_session()
    if not path or not os.path.exists(path):
        return
    tot, per_turn = aggregate(parse_session(path))
    if not per_turn:
        return
    last = per_turn[-1]["total_input"]
    msgs = []
    if last > THRESH["sunk_input"]:
        msgs.append(f"⚠️ 컨텍스트 {last:,} 토큰 — 작업 경계면 /compact, 무관 작업이면 /clear 권장")
    if tot["cache_hit"] < THRESH["cache_hit_low"] and tot["turns"] > 6:
        msgs.append(f"⚠️ 캐시 적중률 {tot['cache_hit']*100:.0f}% — 모델·effort 전환 자제")
    if msgs:
        print(" ".join(msgs))


def do_capture_failures(path, data_dir=None):
    """Stop hook용: Haiku 1차 실패 후보(에스컬레이션·사용자 교정)를 감지해 로그에 누적.
    새 후보가 있을 때만 한 줄 출력(없으면 침묵).
    data_dir이 주어지면(플러그인 설치 시 ${CLAUDE_PLUGIN_DATA}) 그 경로에 쓴다 —
    ${CLAUDE_PLUGIN_ROOT}는 플러그인 업데이트마다 바뀌는 임시 경로라 로그 유실 위험이 있어서다."""
    path = path or latest_session()
    if not path or not os.path.exists(path):
        return
    log_path = os.path.join(data_dir, "production_failures.jsonl") if data_dir else None
    candidates = capture_failures(path, log_path=log_path)
    if candidates:
        kinds = {}
        for c in candidates:
            kinds[c["type"]] = kinds.get(c["type"], 0) + 1
        detail = ", ".join(f"{k}×{v}" for k, v in kinds.items())
        print(f"📋 실패 후보 {len(candidates)}건 포착({detail}) → {log_path or PRODUCTION_LOG}")


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
    args = ap.parse_args()

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
