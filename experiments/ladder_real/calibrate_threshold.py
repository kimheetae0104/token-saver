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
    check("real_n45_bound_matches_rule_of_three_ballpark", 0.05 < real_bound < 0.20)

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
