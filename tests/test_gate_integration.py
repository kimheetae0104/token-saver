"""hooks/intent_gate.py + hooks/prompt_gate.py 통합 검증 — 두 훅이 세션 상태파일을 통해
턴을 넘나들며 협력하는 지점만 다룬다(단일 훅 단위 테스트는 각 test_*.py에 있음).
pytest 없음, stdlib assert + PASS/FAIL 러너(레포 컨벤션). 실행: python3 tests/test_gate_integration.py
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTENT_GATE = os.path.join(REPO, "hooks", "intent_gate.py")
PROMPT_GATE = os.path.join(REPO, "hooks", "prompt_gate.py")


def _submit_prompt(prompt, session_id, data_dir):
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_DATA"] = data_dir
    subprocess.run([sys.executable, INTENT_GATE],
                    input=json.dumps({"prompt": prompt, "session_id": session_id}),
                    capture_output=True, text=True, env=env, timeout=10)


def _tool_call(session_id, data_dir):
    payload = {"session_id": session_id, "hook_event_name": "PreToolUse",
               "tool_name": "Bash", "tool_input": {}}
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_DATA"] = data_dir
    proc = subprocess.run([sys.executable, PROMPT_GATE], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    out = proc.stdout.strip()
    return "DENY" if out else "ALLOW"


def test_new_ambiguous_turn_trips_again_after_prior_turn_tripped():
    """레이스 픽스(O_CREAT|O_EXCL 클레임 파일)의 부작용 가드: 이전 턴이 트립하며 남긴
    클레임 파일을 intent_gate.py가 다음 턴 상태 갱신 시 지우지 않으면, 다음 턴이 새로
    모호해도 클레임 파일이 이미 있어서 조용히 통과해버린다(트립 게이트가 세션당 평생
    1회로 고장남 — 의도는 턴마다 1회)."""
    with tempfile.TemporaryDirectory() as data_dir:
        # 턴 1: 모호한 요청 -> 첫 도구 호출 deny, 재시도는 allow
        _submit_prompt("더 강화시켜", "sess-1", data_dir)
        assert _tool_call("sess-1", data_dir) == "DENY"
        assert _tool_call("sess-1", data_dir) == "ALLOW"

        # 턴 2: 같은 세션에서 다시 모호한 요청 -> 새로 트립해야 한다
        _submit_prompt("그것도 강화해", "sess-1", data_dir)
        assert _tool_call("sess-1", data_dir) == "DENY"
        assert _tool_call("sess-1", data_dir) == "ALLOW"


def test_clear_turn_after_flagged_turn_does_not_trip():
    """턴 1이 모호해서 flagged=True로 트립됐어도, 턴 2가 4슬롯을 다 채운 명확한 요청이면
    상태가 flagged=False로 덮어써져 도구 호출이 막히면 안 된다(과거 턴 상태가 새지 않음
    — test_intent_gate.py의 state 단위 검증을 훅 두 개를 다 거치는 실제 흐름으로 재확인)."""
    with tempfile.TemporaryDirectory() as data_dir:
        _submit_prompt("더 강화시켜", "sess-1", data_dir)
        assert _tool_call("sess-1", data_dir) == "DENY"

        _submit_prompt(
            "measure.py의 check_line 함수만 수정해줘, 기존 포맷 절대 깨지 말고, "
            "테스트 통과하면 완료로 간주", "sess-1", data_dir)
        assert _tool_call("sess-1", data_dir) == "ALLOW"


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
