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


def _merge_intervals(intervals):
    """겹치거나 맞닿은 구간을 병합. 병합된 구간에 완전히 포함되는 새 range만
    '진짜 100% 중복'이다 — 부분만 겹치는 range는 미독 구간을 포함하므로 다르게 취급한다."""
    if not intervals:
        return []
    merged = [list(sorted(intervals)[0])]
    for st, en in sorted(intervals)[1:]:
        if st <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], en)
        else:
            merged.append([st, en])
    return merged


def _is_full_subset(rng, merged):
    off, end = rng
    return any(st <= off and end <= en for st, en in merged)


def scan_overlap_severity(session_paths):
    """겹침 재독을 두 종류로 나눠 센다:
    - full_subset: 새 range가 그 시점까지의 이전 range들 union에 완전히 포함 —
      미독 구간이 전혀 없는 100% 중복. read_guard의 체크1/2와 같은 안전 불변식
      ("요청 범위 전체가 이미 전달된 경우에만 차단")을 만족해 차단해도 위험이 없다.
    - partial_overlap: 일부만 겹침 — 새로 읽는 구간이 실제로 존재해서, 전체를 차단하면
      그 미독 구간까지 막아버리는 기능 손상 위험이 있다. read_guard로 안전하게 구현할 수
      없는 부류(설계 결정: 이 부류는 구현 대상에서 제외).
    """
    total_reads = 0
    full_subset = 0
    partial_only = 0
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
                is_exact_dup = (offset, end) in prev_ranges
                merged = _merge_intervals(prev_ranges)
                has_overlap = any(offset < p_end and end > p_off for p_off, p_end in prev_ranges)
                # 정확히 동일한 단일 range 재독은 read_guard 체크1의 담당 영역이라 여기서 센다면
                # 그 몫과 겹친다 — 이 함수는 체크1 밖의 "여러 range가 합쳐져야만 커버되는"
                # 순수 신규 기회만 본다.
                if has_overlap and not is_exact_dup:
                    if _is_full_subset((offset, end), merged):
                        full_subset += 1
                    else:
                        partial_only += 1
                prev_ranges.append((offset, end))
    return {"total_reads": total_reads, "full_subset": full_subset,
            "partial_only": partial_only, "sessions_scanned": len(session_paths)}


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

    # full_subset vs partial_only 분류: A(0-50) 완독 후 A(10-30)은 완전포함(full_subset),
    # A(30-80)은 부분만 겹침(partial_only, 50-80은 미독).
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s3.jsonl")
        with open(p, "w") as f:
            for offset, limit in [(0, 50), (10, 20), (30, 50)]:
                f.write(json.dumps({"message": {"content": [
                    {"type": "tool_use", "name": "Read",
                     "input": {"file_path": "/a.py", "offset": offset, "limit": limit}}]}}) + "\n")
        result = scan_overlap_severity([p])
        check("classifies_full_subset", result["full_subset"] == 1)
        check("classifies_partial_only", result["partial_only"] == 1)
        check("severity_total_reads", result["total_reads"] == 3)

    # 인접(맞닿은) 두 range의 union을 포함하는 새 range도 full_subset이어야 한다.
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s4.jsonl")
        with open(p, "w") as f:
            for offset, limit in [(0, 50), (50, 50), (10, 80)]:
                f.write(json.dumps({"message": {"content": [
                    {"type": "tool_use", "name": "Read",
                     "input": {"file_path": "/a.py", "offset": offset, "limit": limit}}]}}) + "\n")
        result = scan_overlap_severity([p])
        check("merges_adjacent_ranges_for_subset", result["full_subset"] == 1)

    print(f"\n{passed}/{passed + failed} passed")
    return failed == 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        sys.exit(0 if _run_tests() else 1)

    sessions = list_own_sessions()
    print(f"세션 {len(sessions)}개 발견 (스코프: {OWN_SESSION_DIR})")
    print(scan_line_range_overlaps(sessions))
    print(scan_overlap_severity(sessions))
