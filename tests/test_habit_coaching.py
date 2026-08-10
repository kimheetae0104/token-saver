"""hooks/habit_coaching.py 검증 — UserPromptSubmit 채팅 습관 코칭(연결어 과다·회고+재확인
결합·방향전환·긴 배경설명·짧은 재확인·명령 앞 긴 사유, 6개 패턴 중 첫 매치만 1줄 출력).
이 repo의 다른 5개 훅과 달리 킬스위치/config.json 오버라이드가 없다 — 순수 advisory,
전용 테스트가 지금까지 없었던 유일한 훅(2026-08-10 라운드3에서 발견해 추가).
pytest 없음, stdlib assert + PASS/FAIL 러너(레포 컨벤션). 실행: python3 tests/test_habit_coaching.py
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "habit_coaching.py")


def _call(prompt):
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": prompt}),
                          capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    return proc.stdout.strip()


def test_clean_specific_request_stays_silent():
    out = _call("이 함수 리팩터해줘, 테스트 통과가 완료 기준")
    assert out == "", out


def test_empty_prompt_is_noop():
    out = _call("")
    assert out == "", out


def test_pattern1_excess_connectors_flagged():
    out = _call("이거 하고 그리고 저거 하고 또한 이것도 하고 그런데 잠깐 근데 이건 왜 그래서 다시")
    assert "연결어" in out, out


def test_pattern1_three_connectors_stays_silent():
    """임계값은 '4개 초과'(> 3) — 정확히 3개는 안 걸려야 한다."""
    out = _call("이거 하고 그리고 저거 하고 또한 이것도 하고 그런데 확인해줘")
    assert out == "", out


def test_pattern2_retro_plus_recheck_combo_flagged():
    out = _call("어제 그거 확인해줘 맞나요")
    assert "회고" in out, out


def test_pattern2_retro_alone_without_recheck_stays_silent():
    out = _call("어제 작업한 내용 이어서 해줘")
    assert out == "", out


def test_pattern3_pivot_flagged():
    out = _call("대신에 다른 방식으로 해줘")
    assert "방향전환" in out, out


def test_pattern4_long_background_flagged():
    out = _call("x" * 301)
    assert "배경 설명 과다" in out, out


def test_pattern4_just_under_threshold_stays_silent():
    out = _call("x" * 300)
    assert out == "", out


def test_pattern5_short_recheck_flagged():
    out = _call("이거 맞나요")
    assert "재확인" in out, out


def test_pattern5_long_recheck_stays_silent():
    """재확인 신호가 있어도 15단어↑면 이미 맥락이 충분하다고 보고 침묵."""
    out = _call("맞나요 " + "설명 " * 20)
    assert out == "", out


def test_pattern6_long_reason_before_command_flagged():
    out = _call("왜냐하면 " + "배경설명 " * 30 + "만들어줘")
    assert "요청 전 배경" in out, out


def test_pattern6_short_reason_before_command_stays_silent():
    out = _call("왜냐하면 급해서 만들어줘")
    assert out == "", out


def test_only_first_matching_pattern_reported():
    """여러 패턴이 동시에 걸려도 한 줄만 출력(패턴1이 먼저 체크되므로 우선)."""
    out = _call(
        "어제 그리고 또한 그런데 근데 그래서 확인해줘 맞나요"  # 연결어 4개↑ AND 회고+재확인 둘 다 해당
    )
    assert out.count("\n") == 0
    assert "연결어" in out, out


def test_malformed_stdin_fails_open():
    proc = subprocess.run([sys.executable, HOOK], input="not json{{{",
                          capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_missing_prompt_key_fails_open():
    proc = subprocess.run([sys.executable, HOOK], input="{}",
                          capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_non_string_prompt_fails_open():
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": 5}),
                          capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
