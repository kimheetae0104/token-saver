"""check_citations.py 검증 — 문서의 "실험N" 인용이 PROTOCOL.md에 실존하는지 검사.
pytest 없이 stdlib assert만(레포 컨벤션). 실행: python3 tests/test_check_citations.py"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_citations as cc

PROTOCOL_FIXTURE = """\
# 실험 프로토콜

### 실험 1 — 뭔가 (2026-08-01)
본문.

### 실험 9 — 오라클 없는 과제 (2026-08-04, 가설 기각)
본문.

#### 실험 9 후속 — 판정 입력 절단 (2026-08-04)
본문.

#### 실험 9 후속 2 — 배치 판정 (2026-08-04)
본문.

### 실험 23 — 규모 임계값 탐색 (2026-08-11)
본문.
"""


def _write(dirpath, name, text):
    p = Path(dirpath) / name
    p.write_text(text, encoding="utf-8")
    return p


def test_plain_citation_matching_header_passes():
    with tempfile.TemporaryDirectory() as d:
        protocol = _write(d, "PROTOCOL.md", PROTOCOL_FIXTURE)
        doc = _write(d, "GUIDE.md", "실험23이 근거다.\n")
        ok, problems = cc.check(protocol_path=protocol, docs=[doc])
        assert ok, problems
        assert problems == []


def test_citation_for_nonexistent_experiment_fails():
    with tempfile.TemporaryDirectory() as d:
        protocol = _write(d, "PROTOCOL.md", PROTOCOL_FIXTURE)
        doc = _write(d, "GUIDE.md", "실험99가 근거다.\n")
        ok, problems = cc.check(protocol_path=protocol, docs=[doc])
        assert not ok
        assert len(problems) == 1
        assert problems[0][1] == 1  # 1번째 줄
        assert "실험99" in problems[0][2]


def test_sub_experiment_citation_with_number_matches_numbered_header():
    with tempfile.TemporaryDirectory() as d:
        protocol = _write(d, "PROTOCOL.md", PROTOCOL_FIXTURE)
        doc = _write(d, "GUIDE.md", "실험9후속2에서 재측정.\n")
        ok, problems = cc.check(protocol_path=protocol, docs=[doc])
        assert ok, problems


def test_sub_experiment_citation_without_number_matches_unnumbered_header():
    """"실험9 후속"(번호 없음)은 PROTOCOL.md의 번호 없는 "실험 9 후속" 헤더(=1번째)와 매칭."""
    with tempfile.TemporaryDirectory() as d:
        protocol = _write(d, "PROTOCOL.md", PROTOCOL_FIXTURE)
        doc = _write(d, "GUIDE.md", "실험9 후속에서 처음 시도.\n")
        ok, problems = cc.check(protocol_path=protocol, docs=[doc])
        assert ok, problems


def test_sub_experiment_citation_with_unknown_number_fails():
    with tempfile.TemporaryDirectory() as d:
        protocol = _write(d, "PROTOCOL.md", PROTOCOL_FIXTURE)
        doc = _write(d, "GUIDE.md", "실험9후속9는 존재 안 함.\n")
        ok, problems = cc.check(protocol_path=protocol, docs=[doc])
        assert not ok
        assert len(problems) == 1


def test_base_experiment_number_confused_with_sub_number_not_matched():
    """"실험2"(기본) 인용은 "실험 9 후속 2" 헤더가 있어도 매칭되면 안 된다(번호 오염 방지)."""
    with tempfile.TemporaryDirectory() as d:
        protocol = _write(d, "PROTOCOL.md", PROTOCOL_FIXTURE)
        doc = _write(d, "GUIDE.md", "실험2는 존재하지 않는 기본 실험이다.\n")
        ok, problems = cc.check(protocol_path=protocol, docs=[doc])
        assert not ok, "실험2 기본 인용이 실험9후속2 헤더에 잘못 매칭됨"


def test_missing_doc_file_is_skipped_without_error():
    with tempfile.TemporaryDirectory() as d:
        protocol = _write(d, "PROTOCOL.md", PROTOCOL_FIXTURE)
        missing = Path(d) / "NOPE.md"
        ok, problems = cc.check(protocol_path=protocol, docs=[missing])
        assert ok
        assert problems == []


def test_citation_split_across_soft_wrapped_lines_is_still_caught():
    """2026-08-12 적대적 재검증 실측: 소프트 줄바꿈으로 인용이 두 줄에 걸치면
    (예: "실험 9\\n후속 99") 존재하지 않는 조합인데도 놓치지 않아야 한다 —
    수정 전엔 앞줄의 "실험 9"만 단독 매칭돼 유효 판정으로 조용히 통과했다."""
    with tempfile.TemporaryDirectory() as d:
        protocol = _write(d, "PROTOCOL.md", PROTOCOL_FIXTURE)
        doc = _write(d, "GUIDE.md", "이 결과는 실험 9\n후속 99에서 재확인됨.\n")
        ok, problems = cc.check(protocol_path=protocol, docs=[doc])
        assert not ok, "줄바꿈으로 갈라진 인용의 존재하지 않는 조합이 감지되지 않음"


def test_real_repo_docs_currently_pass():
    """실제 레포 문서 기준 회귀 검사 — 이 테스트가 깨지면 실제로 새 인용 오류가 생긴 것."""
    ok, problems = cc.check()
    assert ok, problems


if __name__ == "__main__":
    import inspect
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name} {e}")
    total = sum(1 for n in globals() if n.startswith("test_"))
    print(f"\n{total - fails}/{total} passed")
    sys.exit(1 if fails else 0)
