"""hooks/read_guard.py 검증 — PreToolUse Read 가드(정확한 범위 재독·대형파일 스코프없는
재독 차단). pytest 없음, stdlib assert + PASS/FAIL 러너(레포 컨벤션).
실행: python3 tests/test_read_guard.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "read_guard.py")


def _call(tool_input, session_id="sess-1", tool_name="Read", data_dir=None, disable=False):
    payload = {"session_id": session_id, "hook_event_name": "PreToolUse",
               "tool_name": tool_name, "tool_input": tool_input}
    env = dict(os.environ)
    if data_dir:
        env["CLAUDE_PLUGIN_DATA"] = data_dir
    if disable:
        env["TOKEN_SAVER_DISABLE_GUARD"] = "1"
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    out = proc.stdout.strip()
    if not out:
        return None  # 허용
    return json.loads(out)


def _make_file(d, name, n_lines):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        for i in range(n_lines):
            f.write(f"line {i}\n")
    return path


def test_allows_first_read():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        resp = _call({"file_path": f}, data_dir=data_dir)
        assert resp is None


def test_blocks_exact_duplicate_same_offset_limit():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        r1 = _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir)
        assert r1 is None
        r2 = _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir)
        assert r2 is not None
        reason = r2["hookSpecificOutput"]["permissionDecisionReason"]
        assert r2["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "이미 이 세션에서 정확히 같은 범위" in reason


def test_allows_same_file_different_range():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        r1 = _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir)
        r2 = _call({"file_path": f, "offset": 6, "limit": 5}, data_dir=data_dir)
        assert r1 is None and r2 is None


def test_allows_reread_after_file_changed():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        r1 = _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir)
        assert r1 is None
        time.sleep(0.05)
        with open(f, "a") as fh:
            fh.write("appended\n")
        r2 = _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir)
        assert r2 is None, "파일이 바뀌었으면 같은 범위 재독도 허용해야 함(품질손상 방지)"


def test_large_file_first_full_read_allowed():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "big.txt", 600)
        resp = _call({"file_path": f}, data_dir=data_dir)
        assert resp is None, "대형 파일이라도 최초 통독은 항상 허용"


def test_large_file_reread_after_partial_blocked():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "big.txt", 600)
        r1 = _call({"file_path": f, "offset": 0, "limit": 50}, data_dir=data_dir)
        assert r1 is None
        r2 = _call({"file_path": f}, data_dir=data_dir)  # 스코프 없는 재독
        assert r2 is not None
        assert r2["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "500줄" in r2["hookSpecificOutput"]["permissionDecisionReason"]


def test_large_file_reread_allowed_after_change():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "big.txt", 600)
        r1 = _call({"file_path": f, "offset": 0, "limit": 50}, data_dir=data_dir)
        assert r1 is None
        time.sleep(0.05)
        with open(f, "a") as fh:
            fh.write("more\n")
        r2 = _call({"file_path": f}, data_dir=data_dir)
        assert r2 is None, "파일이 바뀌었으면 대형 파일 재통독도 허용해야 함"


def test_small_file_full_reread_blocked_by_exact_match_not_size():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)  # 500줄 이하
        r1 = _call({"file_path": f}, data_dir=data_dir)
        assert r1 is None
        r2 = _call({"file_path": f}, data_dir=data_dir)
        assert r2 is not None
        reason = r2["hookSpecificOutput"]["permissionDecisionReason"]
        assert "이미 이 세션에서 정확히 같은 범위" in reason, "소형 파일은 체크1(정확매치) 경로여야 함"
        assert "500줄" not in reason


def test_kill_switch_disables_everything():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        r1 = _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir, disable=True)
        r2 = _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir, disable=True)
        assert r1 is None and r2 is None


def test_missing_session_id_fails_open():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        resp = _call({"file_path": f}, session_id=None, data_dir=data_dir)
        assert resp is None


def test_malformed_stdin_fails_open():
    env = dict(os.environ)
    proc = subprocess.run([sys.executable, HOOK], input="not json{{{", capture_output=True,
                          text=True, env=env, timeout=10)
    assert proc.stdout.strip() == ""
    assert proc.returncode == 0


def test_non_read_tool_is_noop():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call({"command": "ls"}, tool_name="Bash", data_dir=data_dir)
        assert resp is None


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
