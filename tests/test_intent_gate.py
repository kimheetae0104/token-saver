"""hooks/intent_gate.py 검증 — 4슬롯(의도·제약·성공기준·위임경계) 리마인더.
pytest 없음, stdlib assert + PASS/FAIL 러너(레포 컨벤션).
실행: python3 tests/test_intent_gate.py
"""
import json
import os
import subprocess
import sys
import tempfile

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


def test_referent_only_short_request_flags_intent():
    """'이것도 해줘'는 ACTION_WORDS 화이트리스트에 없는 범용 동사("해줘")만 쓰지만,
    '그것도 강화해'(위 test_short_referent_request_flags_intent)와 동일하게 대상이
    생략된 초단문 지시다. 실측된 사각지대: 수정 전엔 has_action=False로 통째로
    스킵되어 침묵했다."""
    out = _call("이것도 해줘")
    assert "의도" in out, out


def test_repeat_request_flags_intent():
    """'다시 해줘'도 대상이 이전 대화에 암묵적으로 의존하는 같은 부류."""
    out = _call("다시 해줘")
    assert "의도" in out, out


def test_malformed_stdin_fails_open():
    proc = subprocess.run([sys.executable, HOOK], input="not json{{{",
                          capture_output=True, text=True, env=dict(os.environ), timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def _call_with_session(prompt, session_id="sess-1", data_dir=None):
    payload = {"prompt": prompt, "session_id": session_id}
    env = dict(os.environ)
    if data_dir:
        env["CLAUDE_PLUGIN_DATA"] = data_dir
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    return proc.stdout.strip()


def _read_state(data_dir, session_id):
    path = os.path.join(data_dir, "prompt_gate", f"{session_id}.json")
    with open(path) as f:
        return json.load(f)


def test_vague_prompt_writes_flagged_state():
    with tempfile.TemporaryDirectory() as data_dir:
        _call_with_session("더 강화시켜", data_dir=data_dir)
        state = _read_state(data_dir, "sess-1")
        assert state == {"flagged": True, "tripped": False}, state


def test_clear_prompt_writes_unflagged_state():
    with tempfile.TemporaryDirectory() as data_dir:
        _call_with_session(
            "measure.py의 check_line 함수만 수정해줘, 기존 포맷 절대 깨지 말고, "
            "테스트 통과하면 완료로 간주", data_dir=data_dir)
        state = _read_state(data_dir, "sess-1")
        assert state == {"flagged": False, "tripped": False}, state


def test_state_overwritten_each_turn():
    """이전 턴이 flagged=True였어도, 다음 턴이 명확하면 flagged=False로 덮어써야
    한다(과거 턴 상태가 새 턴에 새면 안 됨)."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call_with_session("더 강화시켜", data_dir=data_dir)
        assert _read_state(data_dir, "sess-1")["flagged"] is True
        _call_with_session(
            "measure.py의 check_line 함수만 수정해줘, 기존 포맷 절대 깨지 말고, "
            "테스트 통과하면 완료로 간주", data_dir=data_dir)
        assert _read_state(data_dir, "sess-1")["flagged"] is False


def test_specific_long_request_does_not_trip_hard_gate_despite_missing_slots():
    """실측된 오탐: '41번째 줄'·'600으로'처럼 구체적인데 SUCCESS_WORDS/CONSTRAINT_WORDS
    정규식과 우연히 안 겹치는 요청 — 넛지는 몰라도 하드게이트까지 트립하면 안 됨."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call_with_session(
            "hooks/read_guard.py의 41번째 줄 상수를 600으로 바꿔줘", data_dir=data_dir)
        state = _read_state(data_dir, "sess-1")
        assert state["flagged"] is False, state


def test_no_session_id_does_not_crash():
    out = _call("더 강화시켜")  # 기존 _call(), session_id 없음
    assert "의도" in out, out  # stdout 동작은 그대로 — 상태 쓰기만 스킵(fail-open)


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
