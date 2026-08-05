"""measure.py 순수 함수 리팩터 검증. pytest 없이 stdlib assert만(레포 컨벤션).
실행: python3 tests/test_measure_refactor.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import measure

FIXTURE = """\
{"message": {"role": "user", "content": "hello"}, "timestamp": "2026-08-05T00:00:00Z"}
{"message": {"role": "assistant", "content": [{"type": "text", "text": "hi there"}], "usage": {"input_tokens": 500, "cache_creation_input_tokens": 200, "cache_read_input_tokens": 1000, "output_tokens": 300}, "model": "claude-sonnet-5-20260101"}, "timestamp": "2026-08-05T00:00:01Z"}
{"message": {"role": "user", "content": "thanks"}, "timestamp": "2026-08-05T00:00:02Z"}
{"message": {"role": "assistant", "content": [{"type": "text", "text": "you're welcome"}], "usage": {"input_tokens": 100, "cache_creation_input_tokens": 50, "cache_read_input_tokens": 5000, "output_tokens": 80}, "model": "claude-sonnet-5-20260101"}, "timestamp": "2026-08-05T00:00:03Z"}
"""


def test_transcript_dir_sanitizes_and_defaults():
    # project_dir 명시 -> 비영숫자를 '-'로 치환한 경로
    got = measure.transcript_dir("/Volumes/Extreme SSD/worktree/token-saver")
    assert got == os.path.expanduser(
        "~/.claude/projects/-Volumes-Extreme-SSD-worktree-token-saver")
    # 인자 없으면 기존 TRANSCRIPT_DIR 상수와 완전히 동일(하위호환, 무회귀)
    assert measure.transcript_dir() == measure.TRANSCRIPT_DIR


def test_check_line_exact_output():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fake-session.jsonl")
        with open(path, "w") as f:
            f.write(FIXTURE)
        line = measure.check_line(path)
        assert line == "⟢ 턴2 · 7,230tok · hit 96% · $0.0068 · 효율74", line


def test_check_line_missing_file_returns_empty():
    assert measure.check_line("/no/such/file.jsonl") == ""
    assert measure.check_line(None) == ""


def test_autopsy_text_has_header():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fake-session.jsonl")
        with open(path, "w") as f:
            f.write(FIXTURE)
        text = measure.autopsy_text(path)
        assert text.startswith("\n== 낭비 부검 ==")
        assert os.path.basename(path) in text


def test_capture_failures_text_no_subagents_is_empty():
    # 서브에이전트 디렉터리가 없으면 candidates=[] -> "" (조용히, 파일 I/O 없음)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fake-session.jsonl")
        with open(path, "w") as f:
            f.write(FIXTURE)
        assert measure.capture_failures_text(path) == ""


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
