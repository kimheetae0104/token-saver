"""hooks/intent_gate.py 검증 — 4슬롯(의도·제약·성공기준·위임경계) 리마인더.
pytest 없음, stdlib assert + PASS/FAIL 러너(레포 컨벤션).
실행: python3 tests/test_intent_gate.py
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "intent_gate.py")


def _call(prompt):
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps({"prompt": prompt}),
                          capture_output=True, text=True, env=dict(os.environ), timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    return proc.stdout.strip()


def test_short_vague_request_flags_intent():
    """실측 근거: 이 세션에서 실제로 되물어야 했던 초단문 요청 2건."""
    out = _call("더 강화시켜")
    assert "의도" in out, out


def test_short_referent_request_flags_intent():
    out = _call("그것도 강화해")
    assert "의도" in out, out


def test_detailed_request_with_all_slots_stays_silent():
    out = _call("measure.py의 check_line 함수만 수정해줘, 기존 포맷 절대 깨지 말고, "
                "테스트 통과하면 완료로 간주")
    assert out == "", out


def test_question_prompt_is_noop():
    out = _call("이 함수는 왜 이렇게 짜여있어?")
    assert out == "", out


def test_broad_request_without_delegation_flags_it():
    out = _call("전체 코드베이스 모든 파일 리팩터해줘 완료기준은 테스트 통과")
    assert "위임경계" in out, out


def test_broad_request_with_delegation_omits_that_flag():
    out = _call("전체 코드베이스 모든 파일을 서브에이전트로 나눠서 리팩터해줘, 테스트 통과가 완료 기준")
    assert "위임경계" not in out, out


def test_long_prompt_stays_silent_regardless():
    long_prompt = "강화해줘 " * 30  # 25단어 초과
    out = _call(long_prompt)
    assert out == "", out


def test_non_action_short_prompt_is_noop():
    out = _call("고마워")
    assert out == "", out


def test_malformed_stdin_fails_open():
    proc = subprocess.run([sys.executable, HOOK], input="not json{{{",
                          capture_output=True, text=True, env=dict(os.environ), timeout=10)
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
