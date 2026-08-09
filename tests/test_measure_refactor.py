"""measure.py 순수 함수 리팩터 검증. pytest 없이 stdlib assert만(레포 컨벤션).
실행: python3 tests/test_measure_refactor.py"""
import os
import sys
import tempfile
import json

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


LARGE_INPUT_FIXTURE = """\
{"message": {"role": "user", "content": "hello"}, "timestamp": "2026-08-05T00:00:00Z"}
{"message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}], "usage": {"input_tokens": 150000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 300}, "model": "claude-sonnet-5-20260101"}, "timestamp": "2026-08-05T00:00:01Z"}
"""


def test_check_line_includes_context_warning():
    """HANDOFF.md 10차: hook stdout(check_line)은 사용자 화면에 안 뜨지만, 그래도 어시스턴트
    컨텍스트에는 경고가 실려야 한다 — sunk_input 임계값(120,000) 초과 시 ⚠️ 문구 포함 확인."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fake-session.jsonl")
        with open(path, "w") as f:
            f.write(LARGE_INPUT_FIXTURE)
        line = measure.check_line(path)
        assert "⚠️ 컨텍스트" in line, line


def test_do_statusline_includes_same_warning():
    """statusLine은 hook과 달리 사용자 화면에 실제로 뜨는 유일한 경로(HANDOFF.md 10차) —
    check_line()과 동일한 경고가 do_statusline() 출력에도 실려야 사용자가 실제로 볼 수 있다."""
    import io
    import contextlib

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fake-session.jsonl")
        with open(path, "w") as f:
            f.write(LARGE_INPUT_FIXTURE)
        stdin_payload = json.dumps({"transcript_path": path})
        buf = io.StringIO()
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(stdin_payload)
            with contextlib.redirect_stdout(buf):
                measure.do_statusline()
        finally:
            sys.stdin = old_stdin
        out = buf.getvalue()
        assert "⚠️ 컨텍스트" in out, out


def test_do_statusline_no_warning_stays_clean():
    """정상 범위 세션은 statusLine에 경고 없이 기존 포맷 그대로 — 회귀 방지."""
    import io
    import contextlib

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fake-session.jsonl")
        with open(path, "w") as f:
            f.write(FIXTURE)
        stdin_payload = json.dumps({"transcript_path": path})
        buf = io.StringIO()
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(stdin_payload)
            with contextlib.redirect_stdout(buf):
                measure.do_statusline()
        finally:
            sys.stdin = old_stdin
        out = buf.getvalue().strip()
        assert out == "⟢ 7,230 tok · hit 96% · $0.0068 · 2턴", out


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


def test_capture_failures_filters_task_notification_messages():
    """버그 검증: <task-notification>으로 시작하는 시스템 메시지는 user_correction_follow 후보에서 제외됨.
    (수정 전엔 task-notification 텍스트 안의 PIVOT_MARKERS가 우연히 매치되어 오탐을 만들었음)"""
    with tempfile.TemporaryDirectory() as d:
        # 메인 세션 JSONL 생성: haiku 서브에이전트 end_ts(00:00:10Z) 직후
        # <task-notification>으로 시작하는 user 메시지(PIVOT_MARKERS 포함)
        main_path = os.path.join(d, "main-session.jsonl")
        main_lines = [
            json.dumps({"message": {"role": "user", "content": "작업 시작"}, "timestamp": "2026-08-05T00:00:00Z"}),
            json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": "준비됨"}],
                       "usage": {"input_tokens": 100, "output_tokens": 50}, "model": "claude-opus-5-20260101"},
                       "timestamp": "2026-08-05T00:00:01Z"}),
            # 서브에이전트 위임
            json.dumps({"message": {"role": "assistant", "content": [{"type": "tool_use",
                       "name": "Agent", "id": "haiku-task-1"}], "usage": {"input_tokens": 50, "output_tokens": 10},
                       "model": "claude-opus-5-20260101"}, "timestamp": "2026-08-05T00:00:02Z"}),
            # 시스템이 자동 주입한 task-notification (task-notification 뒤에 PIVOT_MARKERS 단어 "대신" 포함)
            json.dumps({"message": {"role": "user", "content": "<task-notification>Agent haiku-task-1 completed. 대신 다른 접근</task-notification>"},
                       "timestamp": "2026-08-05T00:00:11Z"}),
        ]
        with open(main_path, "w") as f:
            f.write("\n".join(main_lines) + "\n")

        # 서브에이전트 task 생성 (haiku 모델, end_ts = 00:00:10Z)
        base = os.path.splitext(main_path)[0]
        subagents_dir = os.path.join(base, "subagents", "task-0")
        os.makedirs(subagents_dir, exist_ok=True)

        task_path = os.path.join(subagents_dir, "agent-haiku-task-1.jsonl")
        haiku_task_lines = [
            json.dumps({"message": {"role": "user", "content": "haiku 작업"}, "timestamp": "2026-08-05T00:00:03Z"}),
            json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": "완료"}],
                       "usage": {"input_tokens": 50, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 30},
                       "model": "claude-haiku-4-5-20251001"}, "timestamp": "2026-08-05T00:00:10Z"}),
        ]
        with open(task_path, "w") as f:
            f.write("\n".join(haiku_task_lines) + "\n")

        # meta.json 생성
        meta_path = task_path[:-len(".jsonl")] + ".meta.json"
        meta = {"toolUseId": "haiku-task-1", "model": "claude-haiku-4-5-20251001", "agentType": "general-purpose",
                "description": "테스트 haiku 작업"}
        with open(meta_path, "w") as f:
            json.dump(meta, f)

        # capture_failures 호출
        log_path = os.path.join(d, "test-failures.jsonl")
        candidates = measure.capture_failures(main_path, log_path=log_path)

        # 기대: user_correction_follow 후보가 생성되지 않음 (task-notification 필터링됨)
        assert len(candidates) == 0, f"expected 0 candidates, got {len(candidates)}: {candidates}"


def test_capture_failures_still_detects_real_user_corrections():
    """정탐: 진짜 사용자가 입력한 PIVOT_MARKERS 메시지는 여전히 user_correction_follow 후보로 탐지됨."""
    with tempfile.TemporaryDirectory() as d:
        # 메인 세션: haiku end_ts(00:00:10Z) 직후 진짜 사용자 메시지(PIVOT_MARKERS 포함, task-notification 없음)
        main_path = os.path.join(d, "main-session.jsonl")
        main_lines = [
            json.dumps({"message": {"role": "user", "content": "작업 시작"}, "timestamp": "2026-08-05T00:00:00Z"}),
            json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": "준비됨"}],
                       "usage": {"input_tokens": 100, "output_tokens": 50}, "model": "claude-opus-5-20260101"},
                       "timestamp": "2026-08-05T00:00:01Z"}),
            # 서브에이전트 위임
            json.dumps({"message": {"role": "assistant", "content": [{"type": "tool_use",
                       "name": "Agent", "id": "haiku-task-2"}], "usage": {"input_tokens": 50, "output_tokens": 10},
                       "model": "claude-opus-5-20260101"}, "timestamp": "2026-08-05T00:00:02Z"}),
            # 진짜 사용자 메시지 (PIVOT_MARKERS "대신" 포함)
            json.dumps({"message": {"role": "user", "content": "그건 됐고 대신 다른 방식으로 해줄래?"},
                       "timestamp": "2026-08-05T00:00:11Z"}),
        ]
        with open(main_path, "w") as f:
            f.write("\n".join(main_lines) + "\n")

        # 서브에이전트 task 생성
        base = os.path.splitext(main_path)[0]
        subagents_dir = os.path.join(base, "subagents", "task-0")
        os.makedirs(subagents_dir, exist_ok=True)

        task_path = os.path.join(subagents_dir, "agent-haiku-task-2.jsonl")
        haiku_task_lines = [
            json.dumps({"message": {"role": "user", "content": "haiku 작업"}, "timestamp": "2026-08-05T00:00:03Z"}),
            json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": "완료"}],
                       "usage": {"input_tokens": 50, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 30},
                       "model": "claude-haiku-4-5-20251001"}, "timestamp": "2026-08-05T00:00:10Z"}),
        ]
        with open(task_path, "w") as f:
            f.write("\n".join(haiku_task_lines) + "\n")

        # meta.json
        meta_path = task_path[:-len(".jsonl")] + ".meta.json"
        meta = {"toolUseId": "haiku-task-2", "model": "claude-haiku-4-5-20251001", "agentType": "general-purpose",
                "description": "테스트 haiku 작업"}
        with open(meta_path, "w") as f:
            json.dump(meta, f)

        # capture_failures 호출
        log_path = os.path.join(d, "test-failures.jsonl")
        candidates = measure.capture_failures(main_path, log_path=log_path)

        # 기대: user_correction_follow 후보가 정확히 1개 생성됨
        assert len(candidates) == 1, f"expected 1 candidate, got {len(candidates)}: {candidates}"
        assert candidates[0]["type"] == "user_correction_follow"
        assert "대신" in candidates[0]["user_text_snippet"] or "다른" in candidates[0]["user_text_snippet"]


def test_similar_desc_filters_re_review_templates():
    """실험13 위양성 사례 2건 — 재검토 정형 문구가 반복되는 워크플로우에서 오탐 방지.
    수정 전: self-describing 단어(re, review, fix)만 겹쳐서 자카드 0.5+ 오탐
    수정 후: 이들 단어를 stopword로 필터링 + 임계값 0.7 상향으로 False."""
    # 케이스 1: 실험13에서 실제로 확인된 false positive
    desc1_a = "Re-review Task 1 fix round 1"
    desc1_b = "Re-review final review fix wave"
    result1 = measure._similar_desc(desc1_a, desc1_b)
    assert result1 is False, (
        f"expected False for '{desc1_a}' vs '{desc1_b}' (실험13 위양성 사례 1), "
        f"got {result1}"
    )

    # 케이스 2: 같은 false positive 패턴의 다른 예시
    desc2_a = "Re-review Task 3 fix round 1"
    desc2_b = "Re-review final review fix wave"
    result2 = measure._similar_desc(desc2_a, desc2_b)
    assert result2 is False, (
        f"expected False for '{desc2_a}' vs '{desc2_b}' (실험13 위양성 사례 2), "
        f"got {result2}"
    )


def test_similar_desc_still_detects_true_escalations():
    """과잉수정 방지: 진짜로 관련 있는 설명들(구체적 내용어가 겹치는 경우)은 여전히 True로 판정."""
    # 케이스: 로그인 관련 버그 수정과 그 재시도 — "login"·"parsing" 같은 도메인 단어가 겹침
    desc_a = "로그인 파싱 버그 수정"
    desc_b = "로그인 파싱 버그 수정 재시도"
    result = measure._similar_desc(desc_a, desc_b)
    # 교집합: {로그인, 파싱, 버그, 수정}, 합집합: {로그인, 파싱, 버그, 수정, 재시도} (5개)
    # 자카드 = 4/5 = 0.8 >= 0.7 → True 기대
    assert result is True, (
        f"expected True for related descriptions '{desc_a}' vs '{desc_b}', "
        f"got {result}"
    )


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
