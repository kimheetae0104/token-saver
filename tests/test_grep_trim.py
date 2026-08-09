"""hooks/grep_trim.py 검증 — PostToolUse Grep 출력 트리밍(매치 과다 시 상위+하위만 남기고
중간 생략, 전체 건수는 항상 명시). pytest 없음, stdlib assert + PASS/FAIL 러너(레포 컨벤션).
실행: python3 tests/test_grep_trim.py
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "grep_trim.py")


def _call(tool_output, tool_name="Grep", disable=False, field="tool_output",
          session_id="sess-1", data_dir=None):
    """data_dir 미지정 시에도 절대 호스트의 공유 tempdir 폴백을 쓰지 않는다 — grep_trim이
    이제 세션별 절감 로그를 쓰므로(log_savings), 격리 없이 반복 실행하면 실제 개발 머신의
    임시 디렉터리에 테스트 부산물이 무한히 쌓인다. 매 호출 자동으로 일회용 디렉터리 배정."""
    payload = {"session_id": session_id, "hook_event_name": "PostToolUse", "tool_name": tool_name,
               field: tool_output}
    env = dict(os.environ)
    if disable:
        env["TOKEN_SAVER_DISABLE_GREP_TRIM"] = "1"
    with tempfile.TemporaryDirectory() as auto_dir:
        env["CLAUDE_PLUGIN_DATA"] = data_dir or auto_dir
        proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    out = proc.stdout.strip()
    return None if not out else json.loads(out)


def _lines(n, prefix="match"):
    return "\n".join(f"{prefix} {i}" for i in range(n))


def test_small_output_passthrough():
    resp = _call(_lines(20))
    assert resp is None


def test_exactly_at_threshold_not_trimmed():
    resp = _call(_lines(100))  # 임계값(100) 이하는 그대로
    assert resp is None


def test_large_output_trimmed():
    resp = _call(_lines(150))
    assert resp is not None
    trimmed = resp["hookSpecificOutput"]["updatedToolOutput"]
    assert resp["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "match 0" in trimmed  # 앞부분 유지
    assert "match 29" in trimmed  # HEAD=30
    assert "match 149" in trimmed  # 마지막 줄(TAIL=10) 유지
    assert "match 30" not in trimmed  # 중간은 생략
    assert "150" in trimmed  # 전체 건수 명시
    assert "생략" in trimmed


def test_omitted_count_arithmetic():
    resp = _call(_lines(150))
    trimmed = resp["hookSpecificOutput"]["updatedToolOutput"]
    # HEAD 30 + TAIL 10 = 40 유지, 110건 생략
    assert "110" in trimmed


def test_non_grep_tool_is_noop():
    resp = _call(_lines(150), tool_name="Bash")
    assert resp is None


def test_missing_tool_output_fails_open():
    env = dict(os.environ)
    proc = subprocess.run([sys.executable, HOOK],
                          input=json.dumps({"session_id": "s", "tool_name": "Grep"}),
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_malformed_stdin_fails_open():
    proc = subprocess.run([sys.executable, HOOK], input="not json{{{",
                          capture_output=True, text=True, env=dict(os.environ), timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_kill_switch_disables():
    resp = _call(_lines(150), disable=True)
    assert resp is None


def test_non_string_output_fails_open():
    env = dict(os.environ)
    proc = subprocess.run([sys.executable, HOOK],
                          input=json.dumps({"session_id": "s", "tool_name": "Grep", "tool_output": 12345}),
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_trim_logs_estimated_tokens_saved():
    """트림 발생 시 생략된 매치(중간 부분)의 추정 토큰 수를 세션별 절감 로그에 남긴다 —
    measure.py가 이걸 합산해 '절대 토큰 절감'을 statusline에 노출한다."""
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(_lines(150), session_id="sess-trim", data_dir=data_dir)
        assert resp is not None  # 트림 발생 확인(기존 동작 무회귀)
        log_path = os.path.join(data_dir, "token_savings", "sess-trim.jsonl")
        assert os.path.isfile(log_path), log_path
        with open(log_path) as f:
            records = [json.loads(line) for line in f if line.strip()]
        assert len(records) == 1, records
        assert records[0]["source"] == "grep_trim"
        assert records[0]["estimated_tokens"] > 0


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
