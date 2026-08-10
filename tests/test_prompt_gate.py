#!/usr/bin/env python3
"""hooks/prompt_gate.py 검증 — PreToolUse 1회성 트립 게이트. pytest 없음, stdlib assert +
PASS/FAIL 러너(레포 컨벤션). 실행: python3 tests/test_prompt_gate.py
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

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


def test_trip_logs_gate_event_for_measure_py():
    """시너지: measure.py의 gate_trips_for_session()이 읽는 gate_events/ 로그를 트립마다
    남긴다 — read_guard/grep_trim/bash_trim의 절감 로그와 같은 관측 파이프라인에 4슬롯
    게이트 개입 횟수도 잡히게 한 것(measure.py 쪽 검증은 test_measure_refactor.py 참고)."""
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        _call(session_id="sess-1", data_dir=data_dir)
        events_path = os.path.join(data_dir, "gate_events", "sess-1.jsonl")
        assert os.path.isfile(events_path), "gate_events 로그가 안 남았다"
        with open(events_path) as f:
            lines = [ln for ln in f if ln.strip()]
        assert len(lines) == 1
        assert json.loads(lines[0])["event"] == "prompt_gate_trip"


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


def test_cleanup_removes_old_state_files():
    with tempfile.TemporaryDirectory() as data_dir:
        d = os.path.join(data_dir, "prompt_gate")
        os.makedirs(d, exist_ok=True)
        stale_path = os.path.join(d, "stale-session.json")
        with open(stale_path, "w") as f:
            json.dump({"flagged": False, "tripped": False}, f)
        old_time = time.time() - 25 * 60 * 60  # 25시간 전(24시간 임계값 초과)
        os.utime(stale_path, (old_time, old_time))
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        _call(session_id="sess-1", data_dir=data_dir)  # deny 트리거 -> cleanup 실행
        assert not os.path.exists(stale_path)


def test_non_dict_config_value_fails_open():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        with open(os.path.join(data_dir, "config.json"), "w") as f:
            json.dump({"prompt_gate": "oops"}, f)
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is None


def test_concurrent_flagged_calls_deny_exactly_once():
    """CLAUDE.md가 권장하는 '독립적 도구 호출은 한 메시지에 병렬로' 패턴에서, 같은 턴에
    도구 호출 N개가 동시에 이 훅에 도달할 수 있다. read-check-write가 원자적이지 않으면
    다수가 동시에 tripped=false를 읽고 전부 통과해버리는 레이스가 생긴다(수정 전 실측:
    8개 동시 호출 중 1개만 deny). O_CREAT|O_EXCL 클레임으로 정확히 1개만 deny돼야 한다."""
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-race", {"flagged": True, "tripped": False})
        N = 8
        results = [None] * N

        def call(idx):
            resp = _call(session_id="sess-race", data_dir=data_dir)
            results[idx] = "DENY" if resp is not None else "ALLOW"

        threads = [threading.Thread(target=call, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count("DENY") == 1, results
        assert results.count("ALLOW") == N - 1, results


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
