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


def exact_binomial_upper_bound(n_pass, n_total, delta=0.05):
    """전부 통과(0 fail)를 관측했을 때의 정확(Clopper-Pearson) 실패율 상한, 신뢰 1-delta.
    공식: 1 - delta**(1/n_total). 분포무가정인 Hoeffding bound보다 이 0-failure Bernoulli
    케이스에서는 훨씬 타이트하다(최종 브랜치 리뷰 Important-1: n=45에서 Hoeffding 0.1824 vs
    exact 0.0644 — Hoeffding은 "더 엄밀한 개선"이 아니라 이 케이스에서는 5배 느슨한 하한).
    n_total=0이면 상한 없음(1.0). 이 공식은 n_pass == n_total(전부 통과)일 때만 유효 —
    실패가 섞인 일반 케이스는 beta 분포 분위수가 필요해 범위 밖(현재 미지원)."""
    if n_total == 0:
        return 1.0
    if n_pass != n_total:
        raise ValueError(
            "exact_binomial_upper_bound는 전부 통과(0 fail, n_pass == n_total) 케이스만 지원한다")
    return 1 - delta ** (1 / n_total)


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

    # 이 프로젝트 실측값(실험8: 45/45 통과) — Hoeffding은 rule-of-three(3/n) 근사보다
    # 유의미하게 느슨한 하한이다(최종 브랜치 리뷰 Important-1: 이름이 "근사와 대략 일치"였던
    # 게 오해를 줌 — 실제로는 일치가 아니라 훨씬 더 보수적).
    real_bound = hoeffding_upper_bound(45, 45, delta=0.05)
    rule_of_three_approx = 3 / 45
    check("hoeffding_bound_is_looser_than_rule_of_three",
          real_bound > 2 * rule_of_three_approx)

    check("exact_binomial_bound_is_1_when_no_data", exact_binomial_upper_bound(0, 0) == 1.0)
    exact_n30 = exact_binomial_upper_bound(30, 30, delta=0.05)
    check("exact_binomial_n30_near_rule_of_three_ballpark", 0.08 < exact_n30 < 0.11)
    check("exact_binomial_tighter_than_hoeffding_at_n45",
          exact_binomial_upper_bound(45, 45, delta=0.05) < hoeffding_upper_bound(45, 45, delta=0.05))
    try:
        exact_binomial_upper_bound(44, 45, delta=0.05)
        check("exact_binomial_rejects_partial_pass", False)
    except ValueError:
        check("exact_binomial_rejects_partial_pass", True)

    print(f"\n{passed}/{passed + failed} passed")
    return failed == 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        sys.exit(0 if _run_tests() else 1)

    print("실험8 실측(A~F, 45/45 통과)의 Hoeffding 실패율 상한(95% 신뢰):",
          f"{hoeffding_upper_bound(45, 45, 0.05):.4f}",
          f"(exact binomial: {exact_binomial_upper_bound(45, 45, 0.05):.4f} — 이쪽이 표준)")
    for alpha in (0.05, 0.1, 0.2):
        print(f"  목표 실패율상한 α={alpha} 달성 최소 N (95% 신뢰, 전부통과 가정, Hoeffding):",
              min_n_for_risk(alpha, 0.05))
