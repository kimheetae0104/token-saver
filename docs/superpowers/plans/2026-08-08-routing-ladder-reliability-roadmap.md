# 라우팅 사다리 신뢰도·성능 개선 로드맵

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 라우팅 사다리(Haiku→오라클 검증→실패시 상향)의 신뢰도·성능 평가 리포트(2026-08-08)에서 나온
6개 개선안을 실행 가능한 태스크로 분해하고 순서대로 반영한다.

**Architecture:** 순수 stdlib 결정론 도구(측정·판정·캘리브레이션)를 `experiments/`에 추가하고,
`CLAUDE.md`·`experiments/PROTOCOL.md`에 결과를 기록한다. 신규 LLM 호출(이질적 judge, 오케스트레이션
재실행)은 코드가 아니라 **실행 시점에 Agent 도구로 직접 호출** — 하드코딩된 API 호출 클라이언트는
만들지 않는다(레포에 이미 그런 클라이언트가 없고, Claude Code 환경 자체가 호출 수단이기 때문).

**Tech Stack:** Python 3 stdlib만(레포 컨벤션, AI-YAGNI). pytest 없음 — `python3 tests/test_x.py` 직접
실행 + PASS/FAIL 카운터 러너 패턴을 그대로 따른다.

## Global Constraints

- 결정론으로 되는 것에 LLM 쓰지 않는다(AI-YAGNI, CLAUDE.md 도구·스킬 위생 섹션).
- 신규 실험 섹션은 `experiments/PROTOCOL.md`의 "실험 템플릿"(파일 끝) 형식을 따르고 실측 아닌 값은
  "(실측 아님)"으로 명시한다.
- 이 레포는 공개 저장소 — 백테스트·라벨링 과정에서 다른 프로젝트의 세션 데이터가 섞이지 않도록
  경로를 `~/.claude/projects/-Volumes-Extreme-SSD-worktree-token-saver/`로 하드 스코프한다(실험12
  재발 방지, 최우선 제약).
- 기존 테스트(`tests/test_*.py`, 31/31 통과 상태)를 절대 깨지 않는다 — 각 태스크 마지막에 전체
  재실행해 확인.

**실행 순서는 보고서의 우선순위가 아니라 "저비용→고비용" 순으로 재배열했다** — CLAUDE.md 검증 원칙
("가장 값싼 오라클 먼저")을 로드맵 자체에도 적용. Task 5·6은 실제 LLM 호출 비용이 들어간다.

---

### Task 1: CLAUDE.md 라우팅 규칙에 실험9후속6 반영

**Files:**
- Modify: `CLAUDE.md:15`

**Interfaces:** 없음(문서 전용, 코드 의존 없음).

- [ ] **Step 1: 현재 줄 확인**

```bash
grep -n "라우팅=사다리" CLAUDE.md
```
Expected: `15:- 라우팅=사다리: Haiku→오라클 검증→실패시 **프롬프트 강화 먼저**→재실패시 Sonnet(의미론 경계)→Opus. 오라클 없고 고위험이면 Sonnet 이상부터.`

- [ ] **Step 2: 조건부 예외 추가**

`CLAUDE.md:15`를 다음으로 교체:

```markdown
- 라우팅=사다리: Haiku→오라클 검증→실패시 **프롬프트 강화 먼저**→재실패시 Sonnet(의미론 경계)→Opus. 오라클 없고 고위험이면 Sonnet 이상부터 — 단, **오라클 없어도 대규모 반복(N≥50 수준)이고 배치판정을 쓸 수 있으면 사다리가 여전히 유리**(실험9후속2·6, 배치판정 0.35~0.44배, 에스컬레이션률 2.86% [Wilson 95% CI 0.8~9.8%]). 소표본(N<10)에서는 에스컬레이션 1건만 나와도 역전되니 소표본 오라클-없음 과제는 Sonnet 직행.
```

- [ ] **Step 3: 검증**

```bash
grep -n "실험9후속" CLAUDE.md
```
Expected: 방금 추가한 줄이 매치.

- [ ] **Step 4: 기존 테스트 무영향 확인**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver" && for f in tests/test_*.py; do python3 "$f" | tail -1; done
```
Expected: 4개 파일 모두 `N/N passed`.

- [ ] **Step 5: 커밋**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md 라우팅 규칙에 실험9후속6(배치판정 대규모 예외) 반영"
```

---

### Task 2: production_failures.jsonl 141건 라벨링 — 위양성률 산출

**Files:**
- Create: `experiments/label_failures.py`
- Test: `experiments/label_failures.py` 자체(직접 실행 시 PASS/FAIL 러너 포함, 레포 컨벤션)
- Modify: `experiments/PROTOCOL.md` (실험 13 섹션 추가, 파일 끝 실험 템플릿 앞에 삽입)

**Interfaces:**
- Produces: `stratified_sample(records, k, seed) -> list[dict]` — `type`별 층화 고정시드 샘플링.
- Produces: `type_breakdown(path) -> dict[str, int]` — 기존에 확인한 `{'escalation_pair': 3, 'user_correction_follow': 138}` 재현.

- [ ] **Step 1: 스크립트 작성**

```python
"""experiments/label_failures.py — production_failures.jsonl(141건, 2026-08-08 기준) 후보를
층화 고정시드 샘플링해 수동 라벨링 대상 목록을 뽑는다. capture_failures()는 "재검토 후보"만
수집하지 확정 판정이 아니므로(measure.py:capture_failures docstring), 위양성률은 여기서
사람이 세션 원문을 대조해 직접 매긴다 — 이 파일은 판정 로직이 아니라 표본추출 로직만 담는다.
"""
import json
import os
import random

LOG_PATH = os.path.join(os.path.dirname(__file__), "production_failures.jsonl")


def load_records(path=LOG_PATH):
    records = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def type_breakdown(records):
    out = {}
    for r in records:
        out[r["type"]] = out.get(r["type"], 0) + 1
    return out


def stratified_sample(records, k_per_type, seed=13):
    """type별로 최대 k_per_type개씩 고정시드로 뽑는다. 재현 가능해야 라벨링 세션이 끊겨도
    같은 표본으로 이어갈 수 있다."""
    by_type = {}
    for r in records:
        by_type.setdefault(r["type"], []).append(r)
    out = []
    for t, items in sorted(by_type.items()):
        rng = random.Random(f"{seed}:{t}")
        picked = items[:] if len(items) <= k_per_type else rng.sample(items, k_per_type)
        out.extend(picked)
    return out


def _run_tests():
    fake = (
        [{"type": "a", "dedup_key": f"a{i}"} for i in range(5)]
        + [{"type": "b", "dedup_key": f"b{i}"} for i in range(50)]
    )
    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"PASS {name}")
        else:
            failed += 1
            print(f"FAIL {name}")

    bd = type_breakdown(fake)
    check("type_breakdown_counts", bd == {"a": 5, "b": 50})

    s1 = stratified_sample(fake, k_per_type=10, seed=1)
    check("sample_caps_at_k_per_type", len(s1) == 15)  # a는 5개뿐이라 5+10

    s2 = stratified_sample(fake, k_per_type=10, seed=1)
    check("sample_is_deterministic", [r["dedup_key"] for r in s1] == [r["dedup_key"] for r in s2])

    s3 = stratified_sample(fake, k_per_type=10, seed=2)
    check("different_seed_differs", [r["dedup_key"] for r in s1] != [r["dedup_key"] for r in s3])

    print(f"\n{passed}/{passed + failed} passed")
    return failed == 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        sys.exit(0 if _run_tests() else 1)

    records = load_records()
    print("breakdown:", type_breakdown(records))
    sample = stratified_sample(records, k_per_type=15, seed=13)
    print(f"\n표본 {len(sample)}건 (escalation_pair 최대15 + user_correction_follow 최대15):\n")
    for r in sample:
        print(json.dumps(r, ensure_ascii=False)[:200])
```

- [ ] **Step 2: 단위 테스트 실행**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver" && python3 experiments/label_failures.py --test
```
Expected: `4/4 passed`

- [ ] **Step 3: 실제 표본 추출**

```bash
python3 experiments/label_failures.py
```
Expected: `breakdown: {'escalation_pair': 3, 'user_correction_follow': 138}` 출력 + 최대 3+15=18건 표본.

- [ ] **Step 4: 수동 라벨링 (실행 시점 작업 — 코드 아님)**

표본의 각 `session` 필드로 `~/.claude/projects/-Volumes-Extreme-SSD-worktree-token-saver/<session>`을
Read해 `haiku_task`/`escalated_task` 또는 `user_text_snippet` 전후 맥락을 대조, 다음 3가지로 분류:
- **real_escalation**: Haiku가 실제로 실패해서 상위 모델로 넘어간 경우
- **false_positive**: 의도적 A/B 비교, 무관한 후속 대화, PIVOT_MARKERS 오검출
- **ambiguous**: 판단 불가

`user_correction_follow` 138건 중 표본 15건의 위양성률을 `experiments/PROTOCOL.md`에 실험 13으로 기록.

- [ ] **Step 5: PROTOCOL.md에 실험 13 섹션 추가**

파일 끝 "실험 템플릿" 앞에 삽입 (형식은 기존 실험 9 섹션과 동일하게 동기/설정/결과/해석/처방 구조):

```markdown
### 실험 13 — production_failures.jsonl 141건 표본 라벨링 (2026-08-08)
동기: 로드맵 태스크4 — capture_failures()가 실사용 중 축적한 141건(escalation_pair 3,
user_correction_follow 138)이 "재검토 후보"일 뿐 확정 판정이 아니므로, 실제 위양성률을
사람이 직접 대조해야 이 파이프라인의 신뢰도를 알 수 있다.

**설정**: `label_failures.py`로 type별 층화 고정시드(seed=13) 표본 18건(escalation_pair 3
전수 + user_correction_follow 15) 추출, 각 세션 원문 대조.

**결과**: [라벨링 완료 후 표로 채움 — real_escalation N / false_positive N / ambiguous N,
위양성률 %]

**해석**: [PIVOT_MARKERS 기반 감지가 실사용에서 과민한지, escalation_pair 감지(설명
유사도 기반)가 A/B 비교와 실제 실패를 잘 구분하는지]

**처방**: [위양성률이 높으면 measure.py의 PIVOT_MARKERS·_similar_desc 임계값 조정 필요 —
후속 태스크로 분리]
```

- [ ] **Step 6: 커밋**

```bash
git add experiments/label_failures.py experiments/PROTOCOL.md
git commit -m "feat(experiments): production_failures.jsonl 층화표본 도구 + 실험13 라벨링 착수"
```

---

### Task 3: 오라클 없는 과제(G1~G5) — 이질적 judge + polling 검증기

**Files:**
- Create: `experiments/ladder_real/verify_fails.py`
- Modify: `experiments/PROTOCOL.md` (실험 14 섹션)

**Interfaces:**
- Consumes: `task_g_oracle_less.grade(task_key, candidate_text) -> (bool, str)` (기존, `experiments/ladder_real/task_g_oracle_less.py:75`)
- Produces: `poll_vote(votes: list[bool]) -> bool` — 과반 다수결.
- Produces: `needs_judge(task_key, candidate_text) -> bool` — 정규식 오라클이 FAIL일 때만 True(비용 절감, PASS는 judge 호출 안 함).

- [ ] **Step 1: 스크립트 작성**

```python
"""experiments/ladder_real/verify_fails.py — 실험9 정규식 오라클(task_g_oracle_less.py)이
FAIL 판정한 후보만 이질적 judge로 재검증. 정규식 오라클의 알려진 위음성(동의어 미포함,
docstring 참고)을 걸러내는 2차 필터.

이질적(heterogeneous) 원칙: 후보를 생성한 모델과 같은 계열/유사 모델을 judge로 쓰지 않는다
(egocentric bias 회피, LLM-as-judge 문헌 공통 권고). 이 파일은 judge 호출 자체를 하지
않는다 — judge_fn을 주입받는 순수 로직만 담고, 실제 호출은 실행 시점에 Agent 도구로 한다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import task_g_oracle_less as oracle


def needs_judge(task_key, candidate_text):
    """정규식 오라클이 FAIL이어야만 judge 호출 대상(비용 절감 — PASS는 그대로 신뢰)."""
    ok, _ = oracle.grade(task_key, candidate_text)
    return not ok


def poll_vote(votes):
    """과반 다수결. 짝수 동률이면 보수적으로 False(=진짜 실패로 취급, 에스컬레이션 쪽으로
    치우침 — 판정 비용보다 오상향 비용이 싸다는 사다리 설계 원칙과 일치)."""
    if not votes:
        raise ValueError("votes is empty")
    true_count = sum(1 for v in votes if v)
    return true_count > len(votes) / 2


def verify(task_key, candidate_text, judge_fn, n_polls=3):
    """judge_fn(task_key, candidate_text) -> bool 을 n_polls회 호출해 다수결.
    judge_fn은 실행 시점에 이질적 모델을 호출하는 콜백(예: Agent 도구 래퍼)을 주입."""
    if not needs_judge(task_key, candidate_text):
        return True, ["regex_oracle_pass"]
    votes = [judge_fn(task_key, candidate_text) for _ in range(n_polls)]
    return poll_vote(votes), votes


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

    check("poll_vote_majority_true", poll_vote([True, True, False]) is True)
    check("poll_vote_majority_false", poll_vote([True, False, False]) is False)
    check("poll_vote_tie_conservative_false", poll_vote([True, False]) is False)
    try:
        poll_vote([])
        check("poll_vote_empty_raises", False)
    except ValueError:
        check("poll_vote_empty_raises", True)

    good_g1 = "PUT은 리소스 전체를 덮어써서 멱등적이고, PATCH는 일부 필드만 부분수정한다."
    bad_g1 = "둘 다 리소스를 수정하는 HTTP 메서드다."
    check("needs_judge_false_when_regex_passes", needs_judge("G1", good_g1) is False)
    check("needs_judge_true_when_regex_fails", needs_judge("G1", bad_g1) is True)

    verdict, votes = verify("G1", good_g1, judge_fn=lambda k, t: False, n_polls=3)
    check("verify_skips_judge_on_regex_pass", verdict is True and votes == ["regex_oracle_pass"])

    calls = []

    def fake_judge_majority_pass(k, t):
        calls.append(1)
        return len(calls) != 2  # 1,3번째 True, 2번째만 False → 다수결 True

    verdict2, votes2 = verify("G1", bad_g1, judge_fn=fake_judge_majority_pass, n_polls=3)
    check("verify_calls_judge_on_regex_fail", len(calls) == 3)
    check("verify_majority_overturns_regex_fail", verdict2 is True)

    print(f"\n{passed}/{passed + failed} passed")
    return failed == 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(0 if _run_tests() else 1)
    print(__doc__)
```

- [ ] **Step 2: 테스트 실행**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver" && python3 experiments/ladder_real/verify_fails.py --test
```
Expected: `9/9 passed`

- [ ] **Step 3: 실사용 판정 (실행 시점 작업 — 코드 아님)**

round2(N=20)에서 위음성으로 확인됐던 7건(PROTOCOL.md 실험9후속2 참고)의 후보 텍스트를
`attempts_g_round2/`에서 찾아 `verify()`에 넣되, `judge_fn`은 이 세션에서 **Agent 도구로
후보 생성 모델과 다른 계열의 모델을 호출**해 채점하도록 즉석 구현(코드로 미리 안 만듦 —
judge_fn 인터페이스만 맞으면 됨). n_polls=3.

- [ ] **Step 4: 실험 14 섹션 기록**

```markdown
### 실험 14 — 오라클 없는 과제 이질적 judge + polling 검증 (2026-08-08)
동기: 실험9 정규식 오라클의 35% 위음성 문제를 egocentric bias 없는 이질적 judge + 다수결
polling으로 줄일 수 있는지 확인.

**설정**: round2 위음성 확정 7건을 `verify_fails.py`(n_polls=3, 이질적 judge)로 재판정.

**결과**: [7건 중 몇 건이 이질적 judge 다수결로 정정됐는지]

**해석/처방**: [정규식 오라클 단독 대비 위음성률 개선폭, judge 호출 비용 대비 이득]
```

- [ ] **Step 5: 커밋**

```bash
git add experiments/ladder_real/verify_fails.py experiments/PROTOCOL.md
git commit -m "feat(experiments): 오라클없는 과제 이질적 judge+polling 검증기, 실험14 기록"
```

---

### Task 4: 오라클 있는 과제(A~F) — LTT/CTD 스타일 캘리브레이션 임계값

**Files:**
- Create: `experiments/ladder_real/calibrate_threshold.py`
- Modify: `experiments/PROTOCOL.md` (실험 15 섹션)

**Interfaces:**
- Produces: `hoeffding_upper_bound(n_pass, n_total, delta) -> float` — 유한샘플 실패율 상한(1-delta 신뢰).
- Produces: `min_n_for_risk(alpha, delta) -> int` — 목표 실패율 상한 α, 신뢰 1-δ를 만족하는 데 필요한
  최소 전부-통과 시행 수(Hoeffding bound 역산).

- [ ] **Step 1: 스크립트 작성**

```python
"""experiments/ladder_real/calibrate_threshold.py — Learn-Then-Test/Calibrate-Then-Delegate
스타일: "N번 다 통과하면 실패율이 α를 넘지 않는다"를 유한샘플로 보장하는 최소 N을 계산한다.
분포 가정 없는 Hoeffding bound 사용(모델·과제 종류 무관 — LTT 논문의 핵심 이점).
"""
import math


def hoeffding_upper_bound(n_pass, n_total, delta=0.05):
    """관측 실패율(1 - n_pass/n_total)에 Hoeffding 여유값을 더한, 신뢰 1-delta의 실패율 상한.
    n_total=0이면 상한 없음(1.0)."""
    if n_total == 0:
        return 1.0
    observed_fail_rate = 1 - n_pass / n_total
    margin = math.sqrt(math.log(1 / delta) / (2 * n_total))
    return min(1.0, observed_fail_rate + margin)


def min_n_for_risk(alpha, delta=0.05):
    """전부 통과(0 fail)를 관측했다고 가정할 때, 실패율 상한이 alpha 이하가 되는 최소 n.
    margin(n) <= alpha 를 n에 대해 풀면 n >= log(1/delta) / (2*alpha^2)."""
    if not (0 < alpha < 1) or not (0 < delta < 1):
        raise ValueError("alpha, delta must be in (0, 1)")
    return math.ceil(math.log(1 / delta) / (2 * alpha ** 2))


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

    check("bound_is_1_when_no_data", hoeffding_upper_bound(0, 0) == 1.0)
    check("bound_decreases_with_more_passes",
          hoeffding_upper_bound(45, 45, 0.05) < hoeffding_upper_bound(3, 3, 0.05))
    check("bound_never_exceeds_1", hoeffding_upper_bound(0, 5, 0.05) <= 1.0)

    n = min_n_for_risk(alpha=0.1, delta=0.05)
    achieved = hoeffding_upper_bound(n, n, 0.05)
    check("min_n_achieves_target_risk", achieved <= 0.1)
    check("min_n_minus_one_fails_target",
          hoeffding_upper_bound(n - 1, n - 1, 0.05) > 0.1 or n == 1)

    try:
        min_n_for_risk(alpha=1.5)
        check("min_n_rejects_invalid_alpha", False)
    except ValueError:
        check("min_n_rejects_invalid_alpha", True)

    # 이 프로젝트 실측값(실험8: 45/45 통과) 회귀 확인
    real_bound = hoeffding_upper_bound(45, 45, delta=0.05)
    check("real_n45_bound_matches_rule_of_three_ballpark", 0.05 < real_bound < 0.15)

    print(f"\n{passed}/{passed + failed} passed")
    return failed == 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        sys.exit(0 if _run_tests() else 1)

    print("실험8 실측(A~F, 45/45 통과)의 Hoeffding 실패율 상한(95% 신뢰):",
          f"{hoeffding_upper_bound(45, 45, 0.05):.4f}")
    for alpha in (0.05, 0.1, 0.2):
        print(f"  목표 실패율상한 α={alpha} 달성 최소 N (95% 신뢰, 전부통과 가정):",
              min_n_for_risk(alpha, 0.05))
```

- [ ] **Step 2: 테스트 실행**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver" && python3 experiments/ladder_real/calibrate_threshold.py --test
```
Expected: `7/7 passed`

- [ ] **Step 3: 실측값 적용**

```bash
python3 experiments/ladder_real/calibrate_threshold.py
```
출력값을 기록.

- [ ] **Step 4: 실험 15 섹션 추가 (PROTOCOL.md)**

```markdown
### 실험 15 — A~F 과제 Hoeffding 캘리브레이션 (2026-08-08)
동기: "N=30~50에서 0/N 실패"라는 rule-of-three 눈대중 대신, 분포무가정 유한샘플 상한을
공식화(LTT/CTD 방법론).

**결과**: 45/45 통과 기준 95% 신뢰 실패율 상한 [calibrate_threshold.py 실측값]. 목표
실패율 10% 이하를 95% 신뢰로 보장하려면 최소 N=[min_n_for_risk(0.1, 0.05) 값] 필요 —
현재 45회는 [충분/부족].

**처방**: 이후 A~F류 신규 과제 추가 시 이 최소 N을 사다리 검증 표준으로 사용.
```

- [ ] **Step 5: 커밋**

```bash
git add experiments/ladder_real/calibrate_threshold.py experiments/PROTOCOL.md
git commit -m "feat(experiments): Hoeffding 캘리브레이션 도구로 A~F 실패율 상한 공식화"
```

---

### Task 5: 실험12 백테스트 재실행 — 이 프로젝트 세션으로 스코프 한정

**Files:**
- Create: `experiments/scoped_backtest.py`
- Modify: `experiments/PROTOCOL.md` (실험 16 섹션)

**Interfaces:**
- Produces: `list_own_sessions(base_dir=None) -> list[str]` — 이 프로젝트 세션 디렉터리 안의 `.jsonl`만.
- Produces: `scan_line_range_overlaps(session_paths) -> dict` — `line_range_overlap_detection` 후보
  빈도(실험12에서 제일 유망하다고 판단된 방향, PROTOCOL.md:637-640) 실측.

- [ ] **Step 1: 스크립트 작성**

```python
"""experiments/scoped_backtest.py — 실험12 후속 과제: 이 프로젝트 자신의 세션 디렉터리로만
한정한 백테스트. 실험12가 다른 프로젝트 세션까지 스캔해 결과를 전량 폐기한 재발을 막기 위해,
경로 검증을 하드코딩(다른 base_dir를 넘겨도 이 레포 경로가 아니면 예외).
"""
import glob
import json
import os

OWN_SESSION_DIR = os.path.expanduser(
    "~/.claude/projects/-Volumes-Extreme-SSD-worktree-token-saver/")


def list_own_sessions(base_dir=None):
    base_dir = base_dir or OWN_SESSION_DIR
    if "-Volumes-Extreme-SSD-worktree-token-saver" not in base_dir:
        raise ValueError(
            f"scope violation: {base_dir} is not this project's session dir — "
            "실험12 재발 방지, 다른 프로젝트 세션 스캔 금지")
    if not os.path.isdir(base_dir):
        return []
    return sorted(glob.glob(os.path.join(base_dir, "*.jsonl")))


def scan_line_range_overlaps(session_paths):
    """read_guard가 이미 잡는 '정확 범위 재중복' 대신, 겹치는(overlap) 범위의 재독 빈도를 센다.
    Read 툴 호출의 file_path+offset+limit를 파싱해 같은 파일 내 구간이 겹치는 연속 호출 수를 카운트.
    """
    total_reads = 0
    overlap_events = 0
    for path in session_paths:
        reads_by_file = {}
        for line in open(path, encoding="utf-8", errors="ignore"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            for block in _tool_use_blocks(rec):
                if block.get("name") != "Read":
                    continue
                inp = block.get("input", {})
                fp = inp.get("file_path")
                if not fp:
                    continue
                offset = inp.get("offset", 0) or 0
                limit = inp.get("limit")
                end = offset + limit if limit else float("inf")
                total_reads += 1
                prev = reads_by_file.get(fp)
                if prev is not None:
                    p_off, p_end = prev
                    if offset < p_end and end > p_off and (offset, end) != (p_off, p_end):
                        overlap_events += 1
                reads_by_file[fp] = (offset, end)
    return {"total_reads": total_reads, "overlap_events": overlap_events,
            "sessions_scanned": len(session_paths)}


def _tool_use_blocks(rec):
    msg = rec.get("message", {})
    content = msg.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block


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

    try:
        list_own_sessions(base_dir="/tmp/some-other-project/")
        check("rejects_out_of_scope_dir", False)
    except ValueError:
        check("rejects_out_of_scope_dir", True)

    check("empty_dir_returns_empty_list", list_own_sessions(base_dir="/tmp/definitely-nonexistent-dir-xyz") == [])

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s1.jsonl")
        with open(p, "w") as f:
            f.write(json.dumps({"message": {"content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": "/a.py", "offset": 0, "limit": 50}}]}}) + "\n")
            f.write(json.dumps({"message": {"content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": "/a.py", "offset": 30, "limit": 50}}]}}) + "\n")
        result = scan_line_range_overlaps([p])
        check("detects_overlap", result["overlap_events"] == 1)
        check("counts_total_reads", result["total_reads"] == 2)

    print(f"\n{passed}/{passed + failed} passed")
    return failed == 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        sys.exit(0 if _run_tests() else 1)

    sessions = list_own_sessions()
    print(f"세션 {len(sessions)}개 발견 (스코프: {OWN_SESSION_DIR})")
    print(scan_line_range_overlaps(sessions))
```

- [ ] **Step 2: 테스트 실행**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver" && python3 experiments/scoped_backtest.py --test
```
Expected: `5/5 passed`

- [ ] **Step 3: 실측 백테스트 실행 (이 프로젝트 세션만)**

```bash
python3 experiments/scoped_backtest.py
```
출력된 `overlap_events` / `total_reads` 비율 기록.

- [ ] **Step 4: 실험 16 섹션 추가 (PROTOCOL.md)**

```markdown
### 실험 16 — 실험12 백테스트 재실행, 스코프 한정 (2026-08-08)
동기: 실험12의 백테스트가 무관 프로젝트 세션을 스캔해 전량 폐기됐던 것을, 이 프로젝트
자신의 세션 디렉터리로만 한정해 안전하게 재실행.

**설정**: `scoped_backtest.py` — `list_own_sessions()`가 경로 접두사 검증으로 스코프
이탈 시 예외를 던지도록 하드코딩, `line_range_overlap_detection` 후보의 실제 발생빈도 실측.

**결과**: 세션 [N]개, 총 Read [N]건 중 겹침 재독 [N]건([비율]%).

**처방**: 비율이 유의미하면(예: >5%) read_guard에 겹침 구간 감지 확장을 다음 로드맵 항목으로
승격. 미미하면 실험12의 "유망 후보" 판단 기각.
```

- [ ] **Step 5: 커밋**

```bash
git add experiments/scoped_backtest.py experiments/PROTOCOL.md
git commit -m "feat(experiments): 실험12 백테스트 스코프 한정 재실행, 실험16 기록"
```

---

### Task 6: 실험10 위임 오버헤드 N≥5 재실행 + 직접오케스트레이션 대비 $당 비교

**Files:**
- Create: `experiments/delegation_overhead_bench.py`
- Modify: `experiments/PROTOCOL.md` (실험 17 섹션)

**Interfaces:**
- Consumes: `measure.py`의 세션/서브에이전트 비용 파싱 함수(기존, 직접 import하지 않고 CLI로 호출 —
  `measure.py`가 모듈로 안전하게 import 가능한지 별도 확인 없이 기존 관례대로 subprocess 호출 유지).
- Produces: `overhead_ratio(orchestrator_cost, content_cost, baseline_cost) -> dict` — 실험10과 동일한
  지표(오버헤드/컨텐츠 비율, 배율)를 순수 함수로 분리해 N회 반복에 재사용.

- [ ] **Step 1: 스크립트 작성 (지표 계산 로직만 — 실행은 별도)**

```python
"""experiments/delegation_overhead_bench.py — 실험10(N=1)을 N≥5로 재실행하기 위한 지표
계산 로직. 실제 위임 실행(Agent 도구로 오케스트레이터 서브에이전트 N=5회 디스패치)은 이
세션에서 직접 수행하고, 각 라운드의 (orchestrator_cost, content_cost, baseline_cost)를
여기 넣어 집계한다 — 라이브 API 호출은 코드로 감싸지 않는다(레포 컨벤션: 위임은 Agent 도구,
비용 계산은 measure.py).
"""
import statistics


def overhead_ratio(orchestrator_cost, content_cost, baseline_cost):
    if orchestrator_cost < content_cost:
        raise ValueError("orchestrator_cost는 content_cost를 포함해야 하므로 그보다 작을 수 없다")
    overhead = orchestrator_cost - content_cost
    overhead_pct = (overhead / content_cost * 100) if content_cost else float("inf")
    multiplier = orchestrator_cost / baseline_cost if baseline_cost else float("inf")
    return {
        "overhead": overhead,
        "overhead_pct_of_content": overhead_pct,
        "multiplier_vs_baseline": multiplier,
        "savings_pct_vs_baseline": (1 - multiplier) * 100,
    }


def aggregate_rounds(rounds):
    """rounds: list of overhead_ratio() 결과 dict. N개 라운드의 평균/표준편차 반환."""
    if not rounds:
        raise ValueError("no rounds")
    out = {}
    for key in rounds[0]:
        vals = [r[key] for r in rounds]
        out[key] = {
            "mean": statistics.mean(vals),
            "stdev": statistics.stdev(vals) if len(vals) > 1 else 0.0,
            "n": len(vals),
        }
    return out


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

    # 실험10 실측값 회귀 확인: orchestrator=1.6208, content=0.6685, baseline=2.586
    r = overhead_ratio(1.6208, 0.6685, 2.586)
    check("matches_exp10_overhead_pct", abs(r["overhead_pct_of_content"] - 242.5) < 1.0)
    check("matches_exp10_multiplier", abs(r["multiplier_vs_baseline"] - 0.6268) < 0.01)
    check("matches_exp10_savings", abs(r["savings_pct_vs_baseline"] - 37.3) < 1.0)

    try:
        overhead_ratio(0.5, 0.6685, 2.586)
        check("rejects_orchestrator_less_than_content", False)
    except ValueError:
        check("rejects_orchestrator_less_than_content", True)

    rounds = [overhead_ratio(1.6, 0.67, 2.586), overhead_ratio(1.5, 0.65, 2.586),
              overhead_ratio(1.7, 0.70, 2.586)]
    agg = aggregate_rounds(rounds)
    check("aggregate_has_n_3", agg["multiplier_vs_baseline"]["n"] == 3)
    check("aggregate_mean_is_sane",
          min(r["multiplier_vs_baseline"] for r in rounds)
          <= agg["multiplier_vs_baseline"]["mean"]
          <= max(r["multiplier_vs_baseline"] for r in rounds))

    print(f"\n{passed}/{passed + failed} passed")
    return failed == 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        sys.exit(0 if _run_tests() else 1)
    print(__doc__)
```

- [ ] **Step 2: 테스트 실행**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver" && python3 experiments/delegation_overhead_bench.py --test
```
Expected: `6/6 passed`

- [ ] **Step 3: 실측 라운드 실행 (실행 시점 작업, 비용 발생 — 진행 전 사용자 승인 재확인)**

실험10과 동일 설정(오케스트레이터=sonnet, Agent 도구로 Haiku 30회 배치생성+Sonnet 배치판정
위임)을 N=5회 반복. 매 라운드 오케스트레이터 자신의 agentId로 transcript 대조해
`(orchestrator_cost, content_cost, baseline_cost)` 3개 값을 얻고 `overhead_ratio()`에 입력,
5개 결과를 `aggregate_rounds()`로 집계. **직접 오케스트레이션(위임 없이 메인 세션에서 동일
작업) 1회를 추가로 돌려 $당 비교** — 실험10이 "미착수"로 남겼던 부분.

- [ ] **Step 4: 실험 17 섹션 추가 (PROTOCOL.md)**

```markdown
### 실험 17 — 위임 오버헤드 N=5 재실행 + 직접오케스트레이션 $당 비교 (2026-08-08)
동기: 실험10이 N=1이라 11.5%라는 절감률의 신뢰구간이 없었고, "직접 오케스트레이션과의
$대$ 비교"도 미착수 상태였다.

**설정**: `delegation_overhead_bench.py`로 실험10과 동일 파이프라인 N=5 라운드 집계 +
동일 작업 직접 오케스트레이션 1회 추가.

**결과**: [aggregate_rounds() 출력 — multiplier_vs_baseline의 mean/stdev, 직접
오케스트레이션 대비 $ 비교]

**해석/처방**: [N=1 단일값(0.885배) 대비 N=5 평균이 안정적인지, 직접 오케스트레이션이
더 싼지 — CLAUDE.md 통위임 금지 규칙의 실측 근거 보강 또는 수정]
```

- [ ] **Step 5: 커밋**

```bash
git add experiments/delegation_overhead_bench.py experiments/PROTOCOL.md
git commit -m "feat(experiments): 위임 오버헤드 N=5 재실행 지표도구 + 실험17 기록"
```

---

## Self-Review 체크리스트 (계획 작성자 자체 점검, 완료됨)

- **보고서 6개 항목 커버리지**: 이질적judge(T3)·calibration(T4)·CLAUDE.md반영(T1)·실사용사례(T2)·
  실험12재실행(T5)·실험10재실행(T6) — 전부 태스크로 매핑됨.
- **플레이스홀더 스캔**: 각 태스크의 "Step 3/4" 라이브 실행분은 코드가 아니라 실제 API 비용이
  드는 실행 지시라 의도적으로 결과값을 비워둠(`[실측값]` 표기) — TDD 코드 스텝 자체는 전부
  실행 가능한 완성 코드.
- **타입/시그니처 일관성**: `overhead_ratio`·`aggregate_rounds`·`hoeffding_upper_bound`·
  `min_n_for_risk`·`poll_vote`·`verify`·`needs_judge`·`stratified_sample`·`type_breakdown`·
  `list_own_sessions`·`scan_line_range_overlaps` — 태스크 내에서 정의·사용 일치 확인.
