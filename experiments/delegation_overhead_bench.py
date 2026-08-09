"""experiments/delegation_overhead_bench.py — 실험10(N=1)을 N≥3로 재실행하기 위한 지표
계산 로직. 실제 위임 실행(Agent 도구로 오케스트레이터 서브에이전트 N=3회 디스패치)은 이
세션에서 직접 수행하고, 각 라운드의 (orchestrator_cost, content_cost, baseline_cost)를
여기 넣어 집계한다 — 라이브 API 호출은 코드로 감싸지 않는다(레포 컨벤션: 위임은 Agent 도구,
비용 계산은 measure.py).
"""
import statistics


def overhead_ratio(orchestrator_cost, content_cost, baseline_cost):
    """orchestrator_cost: 오케스트레이터 자신의 턴 비용(자식 서브에이전트 비용은 제외한
    exclusive 값). content_cost: 자식 서브에이전트 비용 합계. 둘은 서로 배타적이라
    total_cost = orchestrator_cost + content_cost로 합산해야 실제 총비용이 나온다
    (실험17에서 확인된 실제 호출 관례 — 실험10 헤드라인 "11.5% 절감/0.885배"와 실험17
    표의 "총비용/baseline 배율"도 전부 이 total_cost 기준이다). multiplier_vs_baseline이
    그 정의를 따르는 주 지표이고, orchestrator_only_multiplier_vs_baseline은 오케스트레이터
    자체 비용만 baseline과 견주고 싶을 때 참고용으로 남긴다(총비용 아님에 주의).
    """
    if orchestrator_cost < 0 or content_cost < 0 or baseline_cost < 0:
        raise ValueError("비용은 음수일 수 없다")
    total_cost = orchestrator_cost + content_cost
    overhead_pct = (orchestrator_cost / content_cost * 100) if content_cost else float("inf")
    multiplier = total_cost / baseline_cost if baseline_cost else float("inf")
    orchestrator_only_multiplier = (
        orchestrator_cost / baseline_cost if baseline_cost else float("inf")
    )
    return {
        "total_cost": total_cost,
        "overhead": orchestrator_cost,
        "overhead_pct_of_content": overhead_pct,
        "multiplier_vs_baseline": multiplier,
        "savings_pct_vs_baseline": (1 - multiplier) * 100,
        "orchestrator_only_multiplier_vs_baseline": orchestrator_only_multiplier,
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
    # 헤드라인(총비용 기준) = "11.5% 절감/0.885배" — PROTOCOL.md 실험10·실험17에 명시된 값.
    r = overhead_ratio(1.6208, 0.6685, 2.586)
    check("matches_exp10_overhead_pct", abs(r["overhead_pct_of_content"] - 242.5) < 1.0)
    check("matches_exp10_multiplier", abs(r["multiplier_vs_baseline"] - 0.885) < 0.01)
    check("matches_exp10_savings", abs(r["savings_pct_vs_baseline"] - 11.5) < 1.0)

    # 실험17 round1 실측값 회귀 확인: orchestrator=1.4268, content=0.4998, baseline=0.4131
    # (10건 라운드 baseline ×10). 총비용/baseline = 4.664배(PROTOCOL.md 표에 명시).
    r17 = overhead_ratio(1.4268, 0.4998, 0.4131)
    check("matches_exp17_round1_multiplier", abs(r17["multiplier_vs_baseline"] - 4.664) < 0.01)

    try:
        overhead_ratio(-1, 0.6685, 2.586)
        check("rejects_negative_cost", False)
    except ValueError:
        check("rejects_negative_cost", True)

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
