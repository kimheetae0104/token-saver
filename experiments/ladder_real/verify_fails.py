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
