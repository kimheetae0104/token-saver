# 다단계 파이프라인 소배치 통위임 차단 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `hooks/ladder_gate.py`(Agent PreToolUse)가 실험10·17에서 실측 손해가 확인된
"다단계 파이프라인을 소배치로 서브에이전트 하나에 통위임"하는 프롬프트 패턴을 정규식
휴리스틱으로 감지해 1회 deny(재시도하면 통과)시키고, `docs/TOKEN-GUIDE.md`에 캐시절감
$/효율점수를 성능검증 공식 지표로 채택한다는 문구를 추가한다.

**Architecture:** 새 파일 없음. 기존 `ladder_gate.py`의 티어-불일치 검사와 동일한 "1회
deny → state 플래그 세팅 → 재시도 시 통과" 패턴을 그대로 재사용해 두 번째 독립 검사로
추가한다. 판단은 `tool_input.prompt` 텍스트에 대한 결정론 정규식 매치뿐(LLM 호출 없음).

**Tech Stack:** Python 3 stdlib만(`re`, `json`, `os`, `tempfile`, `time`) — 기존 파일과 동일,
신규 의존성 없음.

## Global Constraints
- 스펙: `docs/superpowers/specs/2026-08-13-pipeline-batch-guard-design.md` (커밋 `c0ec09a`, 사용자 승인 완료).
- 단계 카테고리 3종, 정규식 그대로: `생성|만들|작성` / `판정|판단|평가|채점|검증` / `측정|계산|집계|비용`. 2개 이상 카테고리 매치 시 "다단계 신호".
- 배치 크기 정규식: `(\d+)\s*(건|개|case|items?)` (대소문자 무시). 못 찾거나 20 미만이면 "소배치 신호"(불명은 위험군 취급).
- 소배치 임계값: `BATCH_SMALL_THRESHOLD = 20` (CLAUDE.md 사다리 규칙 N<20 기준 재사용).
- 새 상태 키: `pipeline_batch_acknowledged`(기존 `ladder_gate` 세션 상태 dict에 추가, 새 상태파일 아님). `--reset`이 `consulted`와 함께 매 턴 false로 리셋.
- 새 이벤트: `event: "pipeline_batch_flagged"`를 기존 `ladder_gate_events/<session_id>.jsonl`에 추가(새 디렉터리 아님, `log_resolution`과 같은 파일에 append).
- 킬스위치/설정 재사용: `TOKEN_SAVER_DISABLE_LADDER_GATE=1`, `config.json`의 `ladder_gate.disabled` — 새 킬스위치 만들지 않음.
- deny 메시지 문구(정확히): `"다단계 파이프라인(생성→판정→측정 등)을 서브에이전트 하나에 통위임하는 패턴으로 보이고 배치가 작아 보입니다(20건 미만 또는 배치 크기 불명) — 실험10·17 실측상 오버헤드가 절감분을 상쇄하거나 역전(최대 3.495배)합니다. 각 단계를 병렬 Agent 여러 콜로 쪼개거나, 배치가 20건 이상이면 그대로 다시 시도하세요(통과합니다)."`
- 커밋 메시지는 한글, `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`로 끝맺음(레포 컨벤션).

---

### Task 1: `ladder_gate.py`에 다단계+소배치 탐지 게이트 추가

**Files:**
- Modify: `hooks/ladder_gate.py` (상수 삽입: 65번 줄 뒤 / 로그 함수 삽입: `log_resolution` 정의 뒤, 186번 줄 부근 / `--reset` 분기 수정: 226번 줄 / 기본 모드 분기 삽입: 253번 줄과 254번 줄 사이)
- Test: `tests/test_ladder_gate.py` (파일 끝, `main()` 정의 앞에 새 테스트 함수들 추가)

**Interfaces:**
- Consumes: 기존 `state_path`, `read_state`, `write_state`, `events_dir`, `allow`, `deny`, `_tier_of` — 시그니처 변경 없음.
- Produces: `_has_pipeline_signal(prompt: str | None) -> bool`, `_has_small_batch_signal(prompt: str | None) -> bool`, `log_pipeline_batch_flagged(session_id: str, stage_signal: bool, batch_signal: bool, acknowledged: bool) -> None`. 이 3개는 이번 태스크에서만 쓰이고 다른 태스크가 의존하지 않음.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ladder_gate.py`의 `def main():` 정의 바로 앞에 아래 테스트 함수들을 추가한다
(기존 `_call`, `_events_path`, `_read_events` 헬퍼를 그대로 재사용 — 새 헬퍼 불필요):

```python
def test_pipeline_signal_with_small_batch_denies_once_then_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "각 항목을 생성하고 판정한 뒤 비용을 측정해서 보고해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is not None
        reason = resp["hookSpecificOutput"]["permissionDecisionReason"]
        assert "다단계 파이프라인" in reason
        assert "3.495배" in reason
        # 재시도(2번째 호출)는 통과 — 강제 변경이 아니라 1회 확인
        resp2 = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp2 is None


def test_pipeline_signal_with_large_batch_allows_immediately():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "30건을 생성하고 판정한 뒤 측정해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is None


def test_single_stage_category_allows():
    """단계어가 1개 카테고리만 매치되면(다단계 아님) 배치 크기와 무관하게 허용."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "이 버그를 판정해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is None


def test_small_explicit_batch_denies():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "15건을 생성하고 판정해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is not None


def test_pipeline_batch_kill_switch_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "생성하고 판정한 뒤 측정해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt},
                     disable=True)
        assert resp is None


def test_pipeline_batch_config_disabled_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_config(data_dir, {"disabled": True})
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        prompt = "생성하고 판정한 뒤 측정해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is None


def test_reset_clears_pipeline_batch_acknowledged():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "생성하고 판정한 뒤 측정해줘"
        _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})  # 최초 deny
        # 다음 턴: --reset이 다시 돌면 acknowledged도 초기화되어야 함
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is not None  # 리셋됐으니 다시 최초 deny


def test_pipeline_batch_flag_logs_event_each_time():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "생성하고 판정한 뒤 측정해줘"
        _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})  # deny
        events = [e for e in _read_events(data_dir, "sess-1")
                  if e["event"] == "pipeline_batch_flagged"]
        assert len(events) == 1, events
        assert events[0]["acknowledged"] is False, events

        _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})  # 재시도, allow
        events2 = [e for e in _read_events(data_dir, "sess-1")
                   if e["event"] == "pipeline_batch_flagged"]
        assert len(events2) == 2, events2
        assert events2[1]["acknowledged"] is True, events2


def test_no_prompt_field_skips_pipeline_batch_check():
    """tool_input에 prompt가 아예 없으면(비정상 배선) 예외 없이 그냥 통과."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={})
        assert resp is None
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python3 tests/test_ladder_gate.py`
Expected: `test_pipeline_signal_with_small_batch_denies_once_then_allows`,
`test_small_explicit_batch_denies`, `test_reset_clears_pipeline_batch_acknowledged`,
`test_pipeline_batch_flag_logs_event_each_time` — 이 4개가 FAIL(아직 아무것도 막지
않으므로 `resp`가 `None`이라 `assert resp is not None`에서 실패). 나머지는 이미 통과할 수
있음(원래도 allow였던 경로) — 그래도 계속 진행.

- [ ] **Step 3: `hooks/ladder_gate.py`에 최소 구현 작성**

`_RESPONSE_FIELD_CANDIDATES = ("tool_output", "tool_response", "output")` 줄(65번 줄) 바로
뒤에 삽입:

```python
# 다단계 파이프라인 소배치 통위임 탐지(실험10·17 실측 반례) — 서로 다른 단계 카테고리
# 2개 이상 + 소배치(20건 미만 또는 불명)면 "서브에이전트 하나에 여러 단계를 한 번에
# 시키는" 패턴으로 본다. docs/superpowers/specs/2026-08-13-pipeline-batch-guard-design.md
_GEN_RE = re.compile(r"(생성|만들|작성)")
_JUDGE_RE = re.compile(r"(판정|판단|평가|채점|검증)")
_MEASURE_RE = re.compile(r"(측정|계산|집계|비용)")
_STAGE_RES = (_GEN_RE, _JUDGE_RE, _MEASURE_RE)
_BATCH_SIZE_RE = re.compile(r"(\d+)\s*(건|개|case|items?)", re.IGNORECASE)
BATCH_SMALL_THRESHOLD = 20


def _has_pipeline_signal(prompt):
    if not isinstance(prompt, str):
        return False
    return sum(1 for r in _STAGE_RES if r.search(prompt)) >= 2


def _has_small_batch_signal(prompt):
    """배치 크기를 못 찾으면 소배치로 간주(실험17 반례를 놓치지 않는 쪽으로 보수적
    기본값 — 브레인스토밍에서 합의)."""
    if not isinstance(prompt, str):
        return True
    m = _BATCH_SIZE_RE.search(prompt)
    if not m:
        return True
    try:
        return int(m.group(1)) < BATCH_SMALL_THRESHOLD
    except ValueError:
        return True
```

`log_resolution` 함수(현재 173-185번 줄) 바로 뒤에 삽입:

```python
def log_pipeline_batch_flagged(session_id, stage_signal, batch_signal, acknowledged):
    try:
        path = os.path.join(events_dir(), f"{session_id}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps({
                "event": "pipeline_batch_flagged",
                "stage_signal": stage_signal,
                "batch_signal": batch_signal,
                "acknowledged": acknowledged,
                "ts": time.time(),
            }) + "\n")
    except Exception:
        pass
```

`--reset` 분기(226번 줄)를 수정:

```python
    if "--reset" in sys.argv:
        write_state(session_id, {"consulted": False, "pipeline_batch_acknowledged": False})
        return allow()
```

기본 모드에서 티어-불일치 deny 블록(253번 줄, `)`로 끝나는 줄) 과 최종
`if recommended: log_resolution(...)` (254번 줄) 사이에 삽입:

```python
    prompt = (payload.get("tool_input") or {}).get("prompt")
    stage_signal = _has_pipeline_signal(prompt)
    batch_signal = _has_small_batch_signal(prompt)
    if stage_signal and batch_signal:
        already_acknowledged = bool(state.get("pipeline_batch_acknowledged"))
        log_pipeline_batch_flagged(session_id, stage_signal, batch_signal, already_acknowledged)
        if not already_acknowledged:
            state["pipeline_batch_acknowledged"] = True
            write_state(session_id, state)
            return deny(
                "다단계 파이프라인(생성→판정→측정 등)을 서브에이전트 하나에 통위임하는 "
                "패턴으로 보이고 배치가 작아 보입니다(20건 미만 또는 배치 크기 불명) — "
                "실험10·17 실측상 오버헤드가 절감분을 상쇄하거나 역전(최대 3.495배)합니다. "
                "각 단계를 병렬 Agent 여러 콜로 쪼개거나, 배치가 20건 이상이면 그대로 "
                "다시 시도하세요(통과합니다)."
            )
```

- [ ] **Step 4: 테스트 재실행해 통과 확인**

Run: `python3 tests/test_ladder_gate.py`
Expected: 전체 PASS(기존 테스트 포함 — 기존 로직 순서·상태 키를 건드리지 않았으므로
회귀 없어야 함). 마지막 줄에 `N/N passed`.

- [ ] **Step 5: 커밋**

```bash
git add hooks/ladder_gate.py tests/test_ladder_gate.py
git commit -m "feat(ladder-gate): 다단계 파이프라인 소배치 통위임 차단 게이트 추가

실험10·17에서 실측된 반례(오버헤드가 절감분을 상쇄·역전, 최대 3.495배)를
정규식 휴리스틱(단계어 2개 이상 카테고리 + 소배치)으로 감지해 1회 deny
후 재시도 시 통과시킨다. 기존 티어-불일치 검사와 동일한 패턴 재사용.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `docs/TOKEN-GUIDE.md`에 성능검증 지표 공식 채택 문구 추가

**Files:**
- Modify: `docs/TOKEN-GUIDE.md` (섹션 5 "측정 방법론" 안, `②실험 층` 블록 뒤·`근거:` 줄 앞)

**Interfaces:**
- Consumes: 없음(문서 전용, 코드 의존성 없음).
- Produces: 없음(후속 태스크 없음 — 이 계획의 마지막 태스크).

- [ ] **Step 1: 문구 삽입**

`docs/TOKEN-GUIDE.md`에서 아래 두 줄(`② 실험 층` 블록의 마지막 항목, "근거: MT-Bench...")
사이에 새 단락을 삽입한다:

```
- 주관 품질 심판: **길이통제 win-rate(AlpacaEval 2.0 LC)** + pairwise + 순서 랜덤화 + swap augmentation +
  자기모델 심판 금지(교차/앙상블) + 인간 100~300건 κ>0.6 보정. (순진한 judge는 긴 답 선호 → 우리 주제 배신)

**공식 채택(2026-08-13)**: "이 세션이 실제로 이득이었는가"의 표준 지표는 `measure.py
--check`/`--statusline`이 내는 **캐시절감 $**와 **효율점수**다(둘 다 라이브 층, 새 로직
아님 — 이미 계산되던 값을 공식 지표로 선언). 구독 주간/5시간 사용량 게이지는 작업량과
효율이 섞인 값이라 이 목적에 쓰지 않는다 — 작업량이 많으면 효율이 좋아도 게이지는 높게
나올 수 있다.

근거: MT-Bench(2306.05685), AlpacaEval-LC(2404.04475), OckBench, Token Complexity(2503.01141).
```

(즉 기존 "근거:" 줄 바로 앞에 "**공식 채택(2026-08-13)**" 단락 한 개만 새로 끼워 넣는다 —
나머지 줄은 원문 그대로.)

- [ ] **Step 2: 커밋**

```bash
git add docs/TOKEN-GUIDE.md
git commit -m "docs(token-guide): 캐시절감\$/효율점수를 성능검증 공식 지표로 채택

구독 주간/5시간 게이지는 작업량과 효율이 섞여 있어 부적합하다는 점을
명시. measure.py 계산 로직 변경 없음, 문서 채택 선언만.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
