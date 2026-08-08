#!/usr/bin/env python3
"""PostToolUse hook (matcher: Grep) — 매치가 과도하게 많을 때(기본 100줄↑) 상위/하위 일부만
남기고 중간을 생략해 컨텍스트에 들어가는 토큰을 줄인다. read_guard(PreToolUse, 재독 차단)와
다른 능력을 쓴다 — PostToolUse는 도구 실행 자체를 막지 않고 결과만 `updatedToolOutput`으로
바꿔치기한다(공식 스키마: hookSpecificOutput.updatedToolOutput).

전체 매치 건수는 항상 그대로 알려준다 — "더 있다"는 신호를 숨기면 안 됨(정보 손실 최소화,
CLAUDE.md "필요한 추론은 자르지 마라" 원칙). 넓은 패턴으로 100건 넘게 쏟아지는 경우가
대상이고, 애초에 필요한 매치가 소수인 정상적인 grep은 건드리지 않는다.

LLM 호출 없음, 결정론(줄 수 세기·슬라이싱만). stdlib만 사용.
킬스위치: TOKEN_SAVER_DISABLE_GREP_TRIM=1 이면 무조건 원본 그대로.
fail-open: stdin 파싱 실패, tool_output 없음/문자열 아님 등 어떤 예외든 조용히 원본 유지.
"""
import json
import os
import sys

MATCH_THRESHOLD = 100
KEEP_HEAD = 30
KEEP_TAIL = 10

# 문서상 필드명이 tool_output으로 확인됐으나, 실제 배선에서 다를 가능성에 대비해
# 여러 후보를 순서대로 시도한다(방어적 — 하나도 안 맞으면 fail-open으로 원본 유지).
OUTPUT_FIELD_CANDIDATES = ("tool_output", "tool_response", "output")


def allow():
    sys.exit(0)


def rewrite(text):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": text,
        }
    }))
    sys.exit(0)


def main():
    if os.environ.get("TOKEN_SAVER_DISABLE_GREP_TRIM") == "1":
        return allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return allow()

    if payload.get("tool_name") != "Grep":
        return allow()

    tool_output = None
    for field in OUTPUT_FIELD_CANDIDATES:
        if field in payload:
            tool_output = payload[field]
            break

    if not isinstance(tool_output, str):
        return allow()

    lines = tool_output.split("\n")
    total = len(lines)
    if total <= MATCH_THRESHOLD:
        return allow()

    head = lines[:KEEP_HEAD]
    tail = lines[-KEEP_TAIL:] if KEEP_TAIL else []
    omitted = total - len(head) - len(tail)
    note = f"... (중간 {omitted}건 생략, 전체 {total}건 매치 — 패턴을 좁히거나 파일 glob을 추가하세요) ..."
    trimmed = "\n".join(head + [note] + tail)
    return rewrite(trimmed)


if __name__ == "__main__":
    main()
