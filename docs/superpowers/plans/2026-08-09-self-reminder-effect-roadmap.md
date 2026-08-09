# 자기상기(hook 코칭) 행동효과 실측 로드맵

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HANDOFF.md 10차 항목2("어시스턴트 자신이 매 턴 상태를 상기하는 것만으로 실제 행동이
달라지는가")를 근거 없는 가정에서 실측된 사실로 바꾼다 — hook이 주입하는 `⟢` 효율 줄·경고를
프롬프트에 넣은 경우와 안 넣은 경우, 동일 과제에서 어시스턴트 응답이 실제로 달라지는지 결정론적
지표로 비교한다.

**Architecture:** 고정된 벤치마크 프롬프트 N쌍을 골라, 각각 (a) hook 출력을 흉내낸 코칭 텍스트를
프롬프트 앞에 주입한 버전 / (b) 주입 없는 원본 버전으로 Agent 서브에이전트 디스패치. 두 조건의
transcript를 `measure.py`로 파싱해 결정론적 지표(출력 토큰수=장황도, `/compact`·`/clear` 자발적
언급 여부, 응답 문장 수)를 비교. LLM judge 없음 — 전부 정규식/토큰카운트 기반.

**Tech Stack:** Python stdlib만(레포 컨벤션), `measure.py`의 기존 파서 재사용, 실행은 Agent 도구
(Workflow 아님 — 페어 수가 적고 순차 판단이 필요해 컨트롤러가 직접 디스패치).

## Global Constraints

- stdlib만 사용, 외부 의존성 추가 금지(레포 전체 컨벤션).
- 테스트는 pytest 없이 `assert` 기반 자체 러너(기존 `tests/test_*.py` 패턴 그대로).
- LLM 호출로 판정하지 않는다 — 전부 결정론적 텍스트/토큰 지표(AI-YAGNI, CLAUDE.md 도구·스킬 위생).
- 실측값만 기록, 지어낸 수치 금지(레포 전체 컨벤션, PROTOCOL.md 헤더 참고).
- 커밋 메시지는 한국어, 끝에 `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- 표본수 정당화는 기존 `experiments/ladder_real/calibrate_threshold.py`의
  `exact_binomial_upper_bound`/`min_n_for_risk`를 재사용(새로 만들지 않는다).

---

### Task 1: 효과 측정 하네스 — `experiments/self_reminder_effect_bench.py`

**Files:**
- Create: `experiments/self_reminder_effect_bench.py`
- Test: 같은 파일 하단 `_run_tests()` + `if __name__ == "__main__": ... --test` (레포 컨벤션,
  `experiments/delegation_overhead_bench.py`·`experiments/scoped_backtest.py`와 동일 패턴)

**Interfaces:**
- Consumes: 없음(신규 모듈). 참고용으로 `measure.py`의 `parse_session`/`aggregate` 시그니처를
  차용하되 import는 하지 않는다(이 모듈은 실제 세션 JSONL이 아니라 컨트롤러가 만든 응답 텍스트를
  직접 분석하므로 독립적).
- Produces:
  - `build_reminder_prefix(check_line_text: str) -> str` — hook이 실제로 주입하는 형식
    (`⟢ 턴{n} · {tok}tok · hit {pct}% · {cost} · 효율{score} ⚠️ ...`)을 그대로 프롬프트 앞에 붙일
    수 있는 블록으로 감싼다. 시스템 리마인더 자체를 흉내내되, 진짜 시스템 리마인더 태그(`<system-reminder>`)와
    구분되도록 `<simulated-reminder>...</simulated-reminder>`로 감싼다(진짜처럼 위장하지 않는다 —
    이 실험이 측정하려는 게 "리마인더가 있으면 행동이 달라지는가"이지 "속일 수 있는가"가 아님).
  - `score_response(text: str) -> dict` — 응답 텍스트 하나를 받아 결정론적 지표를 반환:
    `{"output_chars": int, "mentions_compact": bool, "mentions_clear": bool, "sentence_count": int}`.
    `mentions_compact`/`mentions_clear`는 `/compact`·`/clear` 리터럴 문자열 포함 여부(정규식 아님,
    단순 `in` 체크 — AI-YAGNI).
  - `compare_pair(with_reminder_text: str, without_reminder_text: str) -> dict` — 두 응답에
    `score_response()`를 적용해 `{"with": {...}, "without": {...}, "output_chars_delta": int,
    "compact_mentioned_only_with": bool}`를 반환.

> **실행 완료 (2026-08-09)**: Task 1·2 전부 실행·커밋됨 — `cc0e3be`(하네스, 실측 7/7 통과,
> 테스트 케이스가 계획의 9개보다 적은 건 중복 없이 구현), `7f0a9a6`(파일럿 N=5 + PROTOCOL.md
> 실험19 + HANDOFF.md 10차 항목2 완료 처리). 결론: 응답 길이 방향 불일치(2/5 짧아짐·3/5
> 길어짐), `/compact`·`/clear` 자발적 언급 5쌍 전부 0건 — "효과 있다"는 가정 뒷받침 안 됨,
> 단 N=5·hoeffding 상한 1.0(포화)이라 "효과 없다"로 확정할 표본력도 아님. 상세: PROTOCOL.md
> 실험19. 이 플랜 파일은 실행 당시 커밋되지 않고 워킹트리에 남아 있던 것을 사후 정리한다.

- [x] **Step 1: 실패하는 테스트부터 작성**

```python
# experiments/self_reminder_effect_bench.py 하단 _run_tests() 안에 추가할 케이스들

def _run_tests():
    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"PASS {name}")
        else:
            failed += 1
            print(f"FAIL {name}")

    prefix = build_reminder_prefix("⟢ 턴5 · 45,000tok · hit 92% · $0.12 · 효율58")
    check("prefix_wraps_in_simulated_tag", prefix.startswith("<simulated-reminder>")
          and prefix.rstrip().endswith("</simulated-reminder>"))
    check("prefix_contains_check_line", "⟢ 턴5" in prefix)

    s = score_response("네 알겠습니다. 지금 컨텍스트가 크니 /compact 하는 게 좋겠습니다.")
    check("detects_compact_mention", s["mentions_compact"] is True)
    check("no_false_clear_mention", s["mentions_clear"] is False)
    check("sentence_count_counts_periods", s["sentence_count"] == 2)

    cmp_result = compare_pair(
        "짧게 답할게요. /compact 권장.",
        "여기 아주 길게 설명하겠습니다 " * 20 + "끝.",
    )
    check("output_chars_delta_negative_when_with_is_shorter",
          cmp_result["output_chars_delta"] < 0)
    check("flags_compact_only_in_with_condition",
          cmp_result["compact_mentioned_only_with"] is True)

    print(f"\n{passed}/{passed + failed} passed")
    return failed == 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        sys.exit(0 if _run_tests() else 1)
    print(__doc__)
```

- [x] **Step 2: 테스트 실행해 실패 확인**

Run: `python3 experiments/self_reminder_effect_bench.py --test`
Expected: `NameError` 또는 `ImportError` — 함수 미정의로 즉시 실패.

- [x] **Step 3: 최소 구현 작성**

```python
"""experiments/self_reminder_effect_bench.py — HANDOFF.md 10차 항목2: hook이 주입하는
⟢ 효율 줄·경고("자기상기")가 실제로 어시스턴트 응답을 바꾸는지, 결정론적 지표로 비교한다.
LLM judge 없음 — 전부 문자열/토큰 카운트 기반. 실행 자체(Agent 페어 디스패치)는 이 모듈이
아니라 컨트롤러가 Task 2에서 수행하고, 여기는 순수 채점 함수만 담는다(라이브 API 호출은
코드로 감싸지 않는다는 레포 컨벤션, delegation_overhead_bench.py와 동일).
"""


def build_reminder_prefix(check_line_text):
    return f"<simulated-reminder>\n{check_line_text}\n</simulated-reminder>\n\n"


def score_response(text):
    return {
        "output_chars": len(text),
        "mentions_compact": "/compact" in text,
        "mentions_clear": "/clear" in text,
        "sentence_count": text.count(".") + text.count("다.") - text.count("다."),
    }
```

(위 `sentence_count`는 임시 placeholder가 아니라 다음 스텝에서 바로 교정한다 — 마침표 카운트가
실제로 필요한 지표라 이 단계에서 한글 종결어미까지 정확히 세도록 고친다.)

- [x] **Step 4: 마침표 기반으로 정확히 교정 + compare_pair 추가**

```python
def score_response(text):
    return {
        "output_chars": len(text),
        "mentions_compact": "/compact" in text,
        "mentions_clear": "/clear" in text,
        "sentence_count": text.count("."),
    }


def compare_pair(with_reminder_text, without_reminder_text):
    with_s = score_response(with_reminder_text)
    without_s = score_response(without_reminder_text)
    return {
        "with": with_s,
        "without": without_s,
        "output_chars_delta": with_s["output_chars"] - without_s["output_chars"],
        "compact_mentioned_only_with": (
            with_s["mentions_compact"] and not without_s["mentions_compact"]
        ),
    }
```

- [x] **Step 5: 테스트 재실행해 통과 확인**

Run: `python3 experiments/self_reminder_effect_bench.py --test`
Expected: `9/9 passed` (또는 그 이상 — Step1의 케이스 수만큼)

- [x] **Step 6: 커밋**

```bash
git add experiments/self_reminder_effect_bench.py
git commit -m "feat(experiments): 자기상기 행동효과 측정 하네스 추가 (HANDOFF 10차 항목2 Task1)

build_reminder_prefix()/score_response()/compare_pair() — hook이 주입하는
⟢ 효율 줄·경고를 흉내낸 프리픽스 유무에 따라 응답이 실제로 달라지는지 비교할
결정론적 채점 함수. LLM judge 없음, 전부 문자열/토큰 카운트 기반.

테스트 9/9 통과.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: 파일럿 실행(N=5쌍) + PROTOCOL.md 실험19 기록

**Files:**
- Modify: `experiments/PROTOCOL.md` (실험19 섹션 추가, 실험18 다음)
- Modify: `HANDOFF.md` (10차 항목2를 완료 처리 — Task 1 완료 후에도 이 Task까지 끝나야 실측이
  완성되므로, 항목2 취소선은 Task 2 완료 시에만 긋는다)

**Interfaces:**
- Consumes: Task 1의 `build_reminder_prefix`/`compare_pair`(정확히 이 두 함수 이름과 시그니처).
- Produces: PROTOCOL.md에 실험19 결과 표(5쌍의 `output_chars_delta`·`compact_mentioned_only_with`),
  다음 세션이 참고할 결론 문장.

**실행 방법(컨트롤러가 직접 수행 — 서브에이전트에 통위임하지 않는다, CLAUDE.md "다단계
파이프라인 통위임 금지" 규칙 그대로 적용):**

- [x] **Step 1: 벤치마크 프롬프트 5개 고정**

`experiments/ladder_real/`의 기존 오라클-없는 과제(G1~G5, `task_g_oracle_less.py`)를 그대로
재사용한다 — 새 프롬프트를 지어내지 않는다(레포 컨벤션: 기존 벤치마크 재사용 우선). 컨텍스트가
큰 시나리오를 흉내내기 위해 `check_line` 텍스트는 실제 관측값 중 경고가 뜬 사례를 하나 골라
고정한다(예: 이번 세션의 `⟢ 턴136 · 12,907,803tok · hit 98% · $4.21 · 효율61 ⚠️ 컨텍스트
133,467 토큰 — 작업 경계면 /compact, 무관 작업이면 /clear 권장`).

- [x] **Step 2: 5쌍(10회) Agent 디스패치를 한 메시지에 병렬로**

각 G1~G5 프롬프트마다 두 개의 Agent 호출을 만든다 — 하나는 `build_reminder_prefix(고정_check_line)
+ 원본_프롬프트`, 하나는 원본_프롬프트 그대로. **총 10개 Agent 호출을 한 메시지 안에서 병렬로**
보낸다(CLAUDE.md "왕복 최소화" 규칙). 각 응답의 최종 텍스트를 그대로 수집한다(subagent가 알아서
정리하지 않게, "요약하지 말고 실제로 작성한 응답 텍스트를 그대로 반환하라"고 프롬프트에 명시).

- [x] **Step 3: `compare_pair()`로 5쌍 채점**

```python
import sys
sys.path.insert(0, "experiments")
from self_reminder_effect_bench import compare_pair

results = [compare_pair(with_text, without_text) for with_text, without_text in pairs]
n_shorter_with = sum(1 for r in results if r["output_chars_delta"] < 0)
n_compact_only_with = sum(1 for r in results if r["compact_mentioned_only_with"])
```

- [x] **Step 4: `calibrate_threshold.py`로 표본수 해석 붙이기**

N=5는 판단하기엔 작은 표본이다 — `exact_binomial_upper_bound`/`min_n_for_risk`를 그대로 불러와
"5/5 전부 짧아졌다면 실패율(=효과 없음) 상한이 얼마인가"를 계산해 PROTOCOL.md에 같이 적는다
(레포 컨벤션: 소표본 결론에는 항상 신뢰구간을 붙인다, 실험15 패턴 그대로).

- [x] **Step 5: PROTOCOL.md에 실험19 기록**

실험18 섹션 바로 다음에 `### 실험 19 — 자기상기(hook 코칭)의 실제 행동효과 실측 (날짜)` 추가.
표(프롬프트별 with/without `output_chars`·`compact_mentioned_only_with`) + Step4의 신뢰구간 +
결론(효과가 있다/없다/불확실 중 실측이 가리키는 쪽을 그대로 기록 — 미리 정하지 않는다).

- [x] **Step 6: HANDOFF.md 10차 항목2 완료 처리 + 커밋**

```bash
git add experiments/PROTOCOL.md HANDOFF.md
git commit -m "docs(experiments): 자기상기 행동효과 파일럿 실측 — 실험19 (HANDOFF 10차 항목2 완료)

G1~G5 5쌍(N=10 디스패치)으로 hook 코칭 프리픽스 유무에 따른 응답 차이를
compare_pair()로 채점. 결과·신뢰구간은 PROTOCOL.md 실험19 참고. HANDOFF.md
10차 항목2를 근거 없는 가정에서 실측 완료로 갱신.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review 체크리스트 (계획 작성자 자체 점검, 완료됨)

1. **스펙 커버리지**: HANDOFF.md 10차 항목2("실제 행동이 달라지는지 실측 필요")는 Task1(측정
   도구)+Task2(파일럿 실행+기록)로 전부 커버. verify_fails.py 실전 위음성 재현(실험14)은 "사례가
   다시 나오면" 조건부 대기 상태라 이 로드맵에 넣지 않음 — 능동적으로 만들 수 있는 작업이 아님.
2. **Placeholder 스캔**: Step3의 임시 `sentence_count` 버그는 의도적 TDD 중간단계(레포 관례상
   허용되는 "먼저 틀리게, 다음 스텝에서 고친다" 패턴)이지 방치되는 placeholder가 아님 — Step4에서
   바로 교정.
3. **타입/시그니처 일관성**: `build_reminder_prefix`·`score_response`·`compare_pair` 이름과
   반환 dict 키가 Task1 정의와 Task2 사용처(Step3의 import)에서 동일함 확인 완료.
