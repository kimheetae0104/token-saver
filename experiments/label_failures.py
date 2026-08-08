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
