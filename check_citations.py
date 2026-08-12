#!/usr/bin/env python3
"""문서 인용 정합성 검사 — TOKEN-GUIDE.md/README.md/README.en.md/HANDOFF.md가 인용하는
"실험N"(+ "N 후속M")이 experiments/PROTOCOL.md에 실존하는 섹션인지 grep 기반으로 결정론
검사한다. LLM 불필요(AI-YAGNI) — 2026-08-11 Task2에서 발견된 "PROTOCOL.md에 없는 실험을
인용" 오류 클래스의 재발을 값싸게 막기 위한 스크립트.

실행: python3 check_citations.py
종료 코드: 인용 오류 없으면 0, 있으면 1(CI/pre-commit에서 그대로 게이트로 쓸 수 있게).
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PROTOCOL = REPO / "experiments" / "PROTOCOL.md"
CHECKED_DOCS = [
    REPO / "docs" / "TOKEN-GUIDE.md",
    REPO / "README.md",
    REPO / "README.en.md",
    REPO / "HANDOFF.md",
]

# PROTOCOL.md 헤더: "### 실험 N — ..." 또는 "#### 실험 N 후속[ M] — ..."
_HEADER_RE = re.compile(r"^#{2,4}\s+실험\s*(\d+)(?:\s*(후속)\s*(\d+)?)?")
# 문서 인용: "실험N" 또는 "실험N 후속M"(공백 유무 무관)
_CITATION_RE = re.compile(r"실험\s*(\d+)(?:\s*(후속)\s*(\d+)?)?")


def _key(base, has_sub, sub_num):
    """(base실험번호, 후속번호|None) 정규화 키. 후속인데 번호가 없으면 첫 번째(1)로 취급."""
    if not has_sub:
        return (int(base), None)
    return (int(base), int(sub_num) if sub_num else 1)


def load_valid_keys(protocol_path):
    keys = set()
    for line in protocol_path.read_text(encoding="utf-8").splitlines():
        m = _HEADER_RE.match(line)
        if m:
            keys.add(_key(m.group(1), bool(m.group(2)), m.group(3)))
    return keys


def find_citations(doc_path):
    """(줄번호, 원문 인용 문자열, key) 목록."""
    out = []
    for lineno, line in enumerate(doc_path.read_text(encoding="utf-8").splitlines(), start=1):
        for m in _CITATION_RE.finditer(line):
            out.append((lineno, m.group(0), _key(m.group(1), bool(m.group(2)), m.group(3))))
    return out


def check(protocol_path=PROTOCOL, docs=CHECKED_DOCS):
    """(문제없음 여부, 문제 목록[(문서경로, 줄번호, 인용문자열)]) 반환."""
    valid_keys = load_valid_keys(protocol_path)
    problems = []
    for doc in docs:
        if not doc.exists():
            continue
        for lineno, raw, key in find_citations(doc):
            if key not in valid_keys:
                problems.append((doc, lineno, raw))
    return (len(problems) == 0, problems)


def main():
    ok, problems = check()
    if ok:
        print(f"OK — 인용 정합성 문제 없음 ({PROTOCOL.relative_to(REPO)} 기준)")
        return 0
    print(f"FAIL — PROTOCOL.md에 없는 인용 {len(problems)}건:")
    for doc, lineno, raw in problems:
        print(f"  {doc.relative_to(REPO)}:{lineno}: {raw!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
