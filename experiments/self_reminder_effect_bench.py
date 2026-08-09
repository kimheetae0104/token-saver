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
