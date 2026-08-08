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
