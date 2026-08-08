"""experiments/scoped_backtest.py — 실험12 후속 과제: 이 프로젝트 자신의 세션 디렉터리로만
한정한 백테스트. 실험12가 다른 프로젝트 세션까지 스캔해 결과를 전량 폐기한 재발을 막기 위해,
경로 검증을 하드코딩(다른 base_dir를 넘겨도 이 레포 경로가 아니면 예외).
"""
import glob
import json
import os

OWN_SESSION_DIR = os.path.expanduser(
    "~/.claude/projects/-Volumes-Extreme-SSD-worktree-token-saver/")


def list_own_sessions(base_dir=None):
    base_dir = base_dir or OWN_SESSION_DIR
    if "-Volumes-Extreme-SSD-worktree-token-saver" not in base_dir:
        raise ValueError(
            f"scope violation: {base_dir} is not this project's session dir — "
            "실험12 재발 방지, 다른 프로젝트 세션 스캔 금지")
    if not os.path.isdir(base_dir):
        return []
    return sorted(glob.glob(os.path.join(base_dir, "*.jsonl")))


def scan_line_range_overlaps(session_paths):
    """read_guard가 이미 잡는 '정확 범위 재중복' 대신, 겹치는(overlap) 범위의 재독 빈도를 센다.
    Read 툴 호출의 file_path+offset+limit를 파싱해 같은 파일 내 구간이 겹치는 호출 수를 카운트.

    같은 파일의 **모든 이전 read range**와 비교한다(직전 1개만 비교하면 A(0-50)→A(100-150)→
    A(30-80) 같은 순서에서 3번째가 1번째와 겹치는 걸 놓친다 — 실측으로 확인된 과소집계 버그,
    최종 브랜치 리뷰 Critical finding). 완전동일 range 제외(그건 read_guard의 정확중복 담당)는
    유지.
    """
    total_reads = 0
    overlap_events = 0
    for path in session_paths:
        reads_by_file = {}
        for line in open(path, encoding="utf-8", errors="ignore"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            for block in _tool_use_blocks(rec):
                if block.get("name") != "Read":
                    continue
                inp = block.get("input", {})
                fp = inp.get("file_path")
                if not fp:
                    continue
                offset = inp.get("offset", 0) or 0
                limit = inp.get("limit")
                end = offset + limit if limit else float("inf")
                total_reads += 1
                prev_ranges = reads_by_file.setdefault(fp, [])
                for p_off, p_end in prev_ranges:
                    if offset < p_end and end > p_off and (offset, end) != (p_off, p_end):
                        overlap_events += 1
                        break
                prev_ranges.append((offset, end))
    return {"total_reads": total_reads, "overlap_events": overlap_events,
            "sessions_scanned": len(session_paths)}


def _tool_use_blocks(rec):
    msg = rec.get("message", {})
    content = msg.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block


def _run_tests():
    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"PASS {name}")
        else:
            failed += 1
            print(f"FAIL {name}")

    try:
        list_own_sessions(base_dir="/tmp/some-other-project/")
        check("rejects_out_of_scope_dir", False)
    except ValueError:
        check("rejects_out_of_scope_dir", True)

    check("empty_dir_returns_empty_list", list_own_sessions(base_dir="/tmp/-Volumes-Extreme-SSD-worktree-token-saver-nonexistent/") == [])

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s1.jsonl")
        with open(p, "w") as f:
            f.write(json.dumps({"message": {"content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": "/a.py", "offset": 0, "limit": 50}}]}}) + "\n")
            f.write(json.dumps({"message": {"content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": "/a.py", "offset": 30, "limit": 50}}]}}) + "\n")
        result = scan_line_range_overlaps([p])
        check("detects_overlap", result["overlap_events"] == 1)
        check("counts_total_reads", result["total_reads"] == 2)

    # 회귀 테스트: A(0-50) -> A(100-150) -> A(30-80). 3번째는 직전(2번째, 100-150)과는
    # 안 겹치지만 1번째(0-50)와는 겹친다. "직전 1개만 비교"하던 구버전은 이 케이스를
    # 놓쳤다(overlap_events == 0) — "모든 이전 range와 비교"해야 잡힌다.
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s2.jsonl")
        with open(p, "w") as f:
            for offset, limit in [(0, 50), (100, 50), (30, 50)]:
                f.write(json.dumps({"message": {"content": [
                    {"type": "tool_use", "name": "Read",
                     "input": {"file_path": "/a.py", "offset": offset, "limit": limit}}]}}) + "\n")
        result = scan_line_range_overlaps([p])
        check("detects_overlap_with_non_adjacent_previous_read", result["overlap_events"] == 1)
        check("counts_total_reads_non_adjacent_case", result["total_reads"] == 3)

    print(f"\n{passed}/{passed + failed} passed")
    return failed == 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        sys.exit(0 if _run_tests() else 1)

    sessions = list_own_sessions()
    print(f"세션 {len(sessions)}개 발견 (스코프: {OWN_SESSION_DIR})")
    print(scan_line_range_overlaps(sessions))
