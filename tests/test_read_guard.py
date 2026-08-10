"""hooks/read_guard.py 검증 — PreToolUse Read 가드(정확한 범위 재독·대형파일 스코프없는
재독 차단). pytest 없음, stdlib assert + PASS/FAIL 러너(레포 컨벤션).
실행: python3 tests/test_read_guard.py
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
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


def _write_config(data_dir, cfg):
    with open(os.path.join(data_dir, "config.json"), "w") as f:
        json.dump({"read_guard": cfg}, f)


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


def test_blocked_exact_reread_logs_estimated_tokens_saved():
    """차단된 재독의 추정 토큰 수를 세션별 절감 로그에 남긴다 — measure.py 합산 대상."""
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        _call({"file_path": f, "offset": 1, "limit": 5}, session_id="sess-log", data_dir=data_dir)
        _call({"file_path": f, "offset": 1, "limit": 5}, session_id="sess-log", data_dir=data_dir)
        log_path = os.path.join(data_dir, "token_savings", "sess-log.jsonl")
        assert os.path.isfile(log_path), log_path
        with open(log_path) as fh:
            records = [json.loads(line) for line in fh if line.strip()]
        assert len(records) == 1, records
        assert records[0]["source"] == "read_guard_exact"
        assert records[0]["estimated_tokens"] > 0


def test_blocked_large_file_reread_logs_estimated_tokens_saved():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "large.txt", 600)
        _call({"file_path": f, "offset": 0, "limit": 50}, session_id="sess-log2", data_dir=data_dir)
        _call({"file_path": f}, session_id="sess-log2", data_dir=data_dir)  # 스코프 없는 재독
        log_path = os.path.join(data_dir, "token_savings", "sess-log2.jsonl")
        assert os.path.isfile(log_path), log_path
        with open(log_path) as fh:
            records = [json.loads(line) for line in fh if line.strip()]
        assert len(records) == 1, records
        assert records[0]["source"] == "read_guard_large"
        assert records[0]["estimated_tokens"] > 0


def test_blocks_subset_reread_of_earlier_full_read():
    """전체 통독 후 그 안의 일부 범위만 다시 요청 — 파일 안 바뀌었으면 100% 중복이라 차단."""
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        r1 = _call({"file_path": f}, data_dir=data_dir)  # 전체 통독
        assert r1 is None
        r2 = _call({"file_path": f, "offset": 2, "limit": 3}, data_dir=data_dir)  # 그 부분집합
        assert r2 is not None
        reason = r2["hookSpecificOutput"]["permissionDecisionReason"]
        assert r2["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "완전히 포함" in reason


def test_blocks_subset_reread_of_earlier_wider_range():
    """넓은 범위(1~8) 재독 후 그 안의 좁은 부분(2~5) 재요청 — offset/limit이 달라도 부분집합이면 차단."""
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        r1 = _call({"file_path": f, "offset": 1, "limit": 8}, data_dir=data_dir)
        assert r1 is None
        r2 = _call({"file_path": f, "offset": 2, "limit": 4}, data_dir=data_dir)  # 2~5 ⊆ 1~8
        assert r2 is not None
        assert r2["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_allows_overlapping_range_that_extends_beyond():
    """겹치긴 하지만 이전 범위 밖으로 확장되는 요청(새 정보 있음)은 허용."""
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        r1 = _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir)
        assert r1 is None
        r2 = _call({"file_path": f, "offset": 1, "limit": 8}, data_dir=data_dir)  # 1~8 ⊄ 1~5
        assert r2 is None


def test_subset_reread_logs_estimated_tokens_saved():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "small.txt", 10)
        _call({"file_path": f}, session_id="sess-sub", data_dir=data_dir)
        _call({"file_path": f, "offset": 2, "limit": 3}, session_id="sess-sub", data_dir=data_dir)
        log_path = os.path.join(data_dir, "token_savings", "sess-sub.jsonl")
        with open(log_path) as fh:
            records = [json.loads(line) for line in fh if line.strip()]
        assert len(records) == 1, records
        assert records[0]["source"] == "read_guard_subset"
        assert records[0]["estimated_tokens"] > 0


def test_config_disabled_allows_everything():
    """config.json의 read_guard.disabled=true — DIY로 이 hook을 통째로 끌 수 있다."""
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        _write_config(data_dir, {"disabled": True})
        f = _make_file(work, "small.txt", 10)
        _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir)
        r2 = _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir)
        assert r2 is None, "config로 꺼졌으면 정확히 같은 범위 재독도 허용해야 함"


def test_config_custom_large_file_lines_applies():
    """임계값을 낮추면 기본값(500줄)에선 안 걸릴 파일도 재통독 차단 대상이 된다."""
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        _write_config(data_dir, {"large_file_lines": 20})
        f = _make_file(work, "mid.txt", 30)
        r1 = _call({"file_path": f, "offset": 0, "limit": 5}, data_dir=data_dir)
        assert r1 is None
        r2 = _call({"file_path": f}, data_dir=data_dir)
        assert r2 is not None
        assert "20줄" in r2["hookSpecificOutput"]["permissionDecisionReason"]


def test_env_kill_switch_wins_over_config_enabled():
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        _write_config(data_dir, {"disabled": False})
        f = _make_file(work, "small.txt", 10)
        _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir)
        r2 = _call({"file_path": f, "offset": 1, "limit": 5}, data_dir=data_dir, disable=True)
        assert r2 is None


def test_concurrent_identical_reads_deny_all_but_one():
    """실측된 레이스: 같은 세션에서 동일 (file_path, offset, limit) Read 여러 개가 병렬로
    들어오면(CLAUDE.md가 권장하는 패턴 그 자체), 락 없는 read-decide-append는 TOCTOU로
    몇 건이 서로의 기록을 못 보고 같이 통과해버린다(수정 전 실측: 8개 동시 동일요청 중
    5회 시행에서 2회는 ALLOW가 1개가 아니라 2개 샘). 세션 단위 스핀락으로 정확히 1개만
    ALLOW돼야 한다(첫 Read는 정당하게 허용·기록되고 나머지는 방금 기록된 동일 범위 재독으로
    거부)."""
    with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as work:
        f = _make_file(work, "race.txt", 600)
        N = 8
        results = [None] * N

        def call(idx):
            resp = _call({"file_path": f, "offset": 1, "limit": 50}, session_id="sess-race",
                         data_dir=data_dir)
            results[idx] = "DENY" if resp is not None else "ALLOW"

        threads = [threading.Thread(target=call, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count("ALLOW") == 1, results
        assert results.count("DENY") == N - 1, results


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
