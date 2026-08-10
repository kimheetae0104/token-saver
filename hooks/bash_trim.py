#!/usr/bin/env python3
"""PostToolUse hook (matcher: Bash) — Bash 출력이 과도하게 길 때(기본 200줄↑) 상위/하위
일부만 남기고 중간을 생략해 컨텍스트에 들어가는 토큰을 줄인다. grep_trim.py와 같은
설계(head+tail 유지, 생략 건수 항상 명시, LLM 호출 없음)를 Bash 출력에 적용한 자매 hook —
CLAUDE.md "큰 도구 출력(로그·ls -R)은 head/grep/wc로 좁혀서. 그대로 받지 않는다"를
사용자 개입 없이도 최소한으로 강제한다.

grep_trim(임계값 100)보다 임계값을 높게(200) 잡은 이유: Bash 출력은 grep 매치와 달리
테스트 스위트·빌드 로그처럼 100~200줄이 정상 범위인 경우가 흔하다 — 지나치게 낮으면
정상적인 출력까지 잘라 정보 손실 위험이 커진다(CLAUDE.md "필요한 추론은 자르지 마라").
KEEP_TAIL도 grep_trim보다 넉넉히(20줄) 잡아 테스트 요약·종료 코드 같은 마지막 결론이
잘리지 않게 한다.

LLM 호출 없음, 결정론(줄 수 세기·슬라이싱만). stdlib만 사용.
킬스위치: TOKEN_SAVER_DISABLE_BASH_TRIM=1 이면 무조건 원본 그대로.
fail-open: stdin 파싱 실패, tool_output 없음/문자열 아님 등 어떤 예외든 조용히 원본 유지.

DIY 설정(2026-08-09): config.json(config_store.py 참고)이 있으면 disabled·
line_threshold·keep_head·keep_tail을 오버라이드한다. read_guard.py와 동일한 이유로
env kill switch가 항상 config보다 우선.
"""
import json
import os
import sys
import tempfile
import time

LINE_THRESHOLD = 200
KEEP_HEAD = 40
KEEP_TAIL = 20


def config_path():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    return os.path.join(data_dir, "config.json") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-config.json")


def load_config():
    try:
        with open(config_path(), "r") as f:
            return json.load(f).get("bash_trim", {})
    except Exception:
        return {}


def savings_log_dir():
    """read_guard.py·grep_trim.py와 동일한 경로 규약(공유 모듈 없음 — hook은 각자
    self-contained, 레포 기존 스타일). measure.py의 token_savings_for_session()이 이
    경로와 정확히 일치해야 한다."""
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    d = os.path.join(data_dir, "token_savings") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-token-savings")
    os.makedirs(d, exist_ok=True)
    return d


def estimate_tokens(text):
    return max(1, len(text) // 4)


def log_savings(session_id, source, estimated_tokens):
    if not session_id:
        return
    try:
        path = os.path.join(savings_log_dir(), f"{session_id}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps({
                "source": source, "estimated_tokens": estimated_tokens, "ts": time.time(),
            }) + "\n")
    except Exception:
        pass


# grep_trim.py와 동일한 방어적 후보 순서 — 문서상 필드명 확인됐어도 실제 배선 차이 대비.
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
    cfg = load_config()
    if os.environ.get("TOKEN_SAVER_DISABLE_BASH_TRIM") == "1" or cfg.get("disabled"):
        return allow()
    line_threshold = cfg.get("line_threshold", LINE_THRESHOLD)
    keep_head = cfg.get("keep_head", KEEP_HEAD)
    keep_tail = cfg.get("keep_tail", KEEP_TAIL)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return allow()

    if payload.get("tool_name") != "Bash":
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
    if total <= line_threshold:
        return allow()

    # grep_trim.py와 동일한 클램프(그쪽 주석 참고) — line_threshold를 config로 head+tail
    # 합보다 작게 낮추면 클램프 없이는 head·tail 슬라이스가 겹쳐 같은 줄이 중복 출력되고
    # omitted가 음수로 찍히는 채 결과물이 원본보다 커진다.
    keep_head = max(0, min(keep_head, total))
    keep_tail = max(0, min(keep_tail, total - keep_head))
    if total - keep_head - keep_tail <= 0:
        # grep_trim.py와 동일한 이유(그쪽 주석 참고) — 생략할 게 없으면 원본 그대로 허용.
        return allow()

    head = lines[:keep_head]
    tail = lines[-keep_tail:] if keep_tail else []
    omitted = total - len(head) - len(tail)
    note = (f"... (중간 {omitted}줄 생략, 전체 {total}줄 출력 — 필요한 부분만 보려면 "
            f"head/grep/wc로 좁혀서 재실행하세요) ...")
    omitted_lines = lines[keep_head: total - keep_tail if keep_tail else total]
    log_savings(payload.get("session_id"), "bash_trim",
                estimate_tokens("\n".join(omitted_lines)))
    trimmed = "\n".join(head + [note] + tail)
    return rewrite(trimmed)


if __name__ == "__main__":
    main()
