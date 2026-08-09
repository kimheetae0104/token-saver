#!/usr/bin/env python3
"""hooks/prompt_gate.py 검증 — PreToolUse 1회성 트립 게이트. pytest 없음, stdlib assert +
PASS/FAIL 러너(레포 컨벤션). 실행: python3 tests/test_prompt_gate.py
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "prompt_gate.py")


def _call(session_id="sess-1", tool_name="Bash", data_dir=None, disable=False):
    payload = {"session_id": session_id, "hook_event_name": "PreToolUse",
               "tool_name": tool_name, "tool_input": {}}
    env = dict(os.environ)
    if data_dir:
        env["CLAUDE_PLUGIN_DATA"] = data_dir
    if disable:
        env["TOKEN_SAVER_DISABLE_PROMPT_GATE"] = "1"
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    out = proc.stdout.strip()
    if not out:
        return None  # 허용
    return json.loads(out)


def _write_state(data_dir, session_id, state):
    d = os.path.join(data_dir, "prompt_gate")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{session_id}.json"), "w") as f:
        json.dump(state, f)


def _write_config(data_dir, cfg):
    with open(os.path.join(data_dir, "config.json"), "w") as f:
        json.dump({"prompt_gate": cfg}, f)


def test_no_state_file_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(data_dir=data_dir)
        assert resp is None


def test_not_flagged_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": False, "tripped": False})
        resp = _call(data_dir=data_dir)
        assert resp is None


def test_flagged_untripped_denies_and_trips():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is not None
        assert resp["hookSpecificOutput"]["permissionDecision"] == "deny"
        with open(os.path.join(data_dir, "prompt_gate", "sess-1.json")) as f:
            state = json.load(f)
        assert state["tripped"] is True, state


def test_flagged_and_tripped_allows_retry():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": True})
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is None


def test_corrupt_state_file_fails_open():
    with tempfile.TemporaryDirectory() as data_dir:
        d = os.path.join(data_dir, "prompt_gate")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sess-1.json"), "w") as f:
            f.write("not json{{{")
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is None


def test_missing_session_id_allows():
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {}}
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=dict(os.environ), timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_malformed_stdin_fails_open():
    proc = subprocess.run([sys.executable, HOOK], input="not json{{{",
                          capture_output=True, text=True, env=dict(os.environ), timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_kill_switch_disables():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        resp = _call(session_id="sess-1", data_dir=data_dir, disable=True)
        assert resp is None


def test_config_disabled_skips_gate():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        _write_config(data_dir, {"disabled": True})
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is None


def test_env_kill_switch_wins_over_config_enabled():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        _write_config(data_dir, {"disabled": False})
        resp = _call(session_id="sess-1", data_dir=data_dir, disable=True)
        assert resp is None


def test_applies_regardless_of_tool_name():
    """matcher 없이 전체 도구에 적용되는 설계 확인 — Bash 아닌 다른 도구명으로도 차단."""
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        resp = _call(session_id="sess-1", tool_name="Write", data_dir=data_dir)
        assert resp is not None


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
