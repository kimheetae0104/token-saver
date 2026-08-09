#!/usr/bin/env python3
"""PreToolUse hook (matcher: Read) — 같은 세션 안에서 정확히 같은 범위를 재독하거나,
이미 읽은 더 넓은 범위의 부분집합을 재독하거나, 이미 본 대형 파일을 스코프 없이 다시
통째로 읽는 걸 결정론적으로 차단한다.

기존 hooks(intent_gate.py·habit_coaching.py 등)는 전부 advisory(텍스트 제안만) — 이
hook은 이 repo 최초로 실제 tool 호출을 deny할 수 있는 hook이다(PreToolUse는
permissionDecision:"deny"로 실행 자체를 막을 수 있음, UserPromptSubmit/Stop과 다름).

설계 배경: ~/.claude/plans/vast-marinating-newt.md(2026-08-08) — "자동으로(행동 안 바꿔도)
50% 이상 절감" 요청을 분석한 결과, 안전하게(품질손상 위험 없이) 결정론적으로 자동화할 수
있는 유일한 지점이 이 두 체크였음(컨텍스트 미압축·위임 오버헤드는 hook으로 원천 손댈 수
없고, 모델 자동 다운그레이드는 실험7 근거로 기각). 정직한 기대치: 5~15%, read-thrash 있는
세션에 한정.

체크1(정확한 범위 재독)·체크1b(부분집합 재독, 2026-08-09 추가)·체크2(대형파일 스코프없는
재독) 셋 다 **mtime이 그대로일 때만** 차단한다 — Read→Edit→Read(수정 확인) 패턴은 mtime이
바뀌므로 항상 허용되고, 이게 없으면 정상적인 재확인까지 막아 품질손상으로 이어진다. 최초
통독은 파일 크기와 무관하게 항상 허용(정당한 전체 이해 작업 보호). 체크1b는 offset/limit이
정확히 같지 않아도, 이미 읽은 범위 안에 완전히 포함되면 파일이 안 바뀐 이상 내용이 100%
동일하므로 정보 손실 없이 차단한다(체크1의 일반화 — 넓은 통독 후 그 안의 좁은 재독을 잡는
실사용 패턴 커버).

LLM 호출 없음, 전부 결정론(정규식 아님 — 상태 비교만). stdlib만 사용.
킬스위치: TOKEN_SAVER_DISABLE_GUARD=1 이면 무조건 허용(운영 중 문제 생기면 즉시 끌 수 있음).
fail-open: session_id/file_path 없음, 상태 파싱 실패, 대상 파일 접근 실패 등 어떤 예외든
조용히 허용 — tool 호출을 절대 깨뜨리지 않는다.

DIY 설정(2026-08-09): config.json(config_store.py 참고, 경로는 savings_log_dir과 같은
CLAUDE_PLUGIN_DATA 규약)이 있으면 disabled·large_file_lines를 오버라이드한다. Desktop
Code 탭은 hooks가 안 뜨므로 MCP token_saver_config_set이 이 파일을 쓰는 유일한 경로 —
CLI/IDE에서 이 hook이 직접 읽어 반영한다. env kill switch가 항상 config보다 우선.
"""
import json
import os
import sys
import tempfile
import time

LARGE_FILE_LINES = 500
STATE_MAX_AGE_SEC = 24 * 60 * 60


def state_dir():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    d = os.path.join(data_dir, "read_history") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-read-history")
    os.makedirs(d, exist_ok=True)
    return d


def state_path(session_id):
    return os.path.join(state_dir(), f"{session_id}.jsonl")


def config_path():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    return os.path.join(data_dir, "config.json") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-config.json")


def load_config():
    try:
        with open(config_path(), "r") as f:
            return json.load(f).get("read_guard", {})
    except Exception:
        return {}


def savings_log_dir():
    """차단·트림 hook들이 공유하는 '절대 토큰 절감(추정)' 로그 디렉터리. measure.py가 세션별로
    합산해 statusline/리포트에 노출한다(캐시 절감 $와는 다른 지표 — 이건 캐시 미스여도 애초에
    컨텍스트에 안 들어간 토큰 자체)."""
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    d = os.path.join(data_dir, "token_savings") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-token-savings")
    os.makedirs(d, exist_ok=True)
    return d


def estimate_tokens(text):
    """대략적 토큰 추정치(~4 chars/token, 업계 통용 근사). 청구서상 정확한 토큰 수가 아니라
    '차단되지 않았다면 컨텍스트에 들어갔을 크기'의 근사값 — 리포트에 항상 '추정'으로 표기."""
    return max(1, len(text) // 4)


def log_savings(session_id, source, estimated_tokens):
    try:
        path = os.path.join(savings_log_dir(), f"{session_id}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps({
                "source": source, "estimated_tokens": estimated_tokens, "ts": time.time(),
            }) + "\n")
    except Exception:
        pass


def _line_range(offset, limit, total_lines):
    """Read 툴 semantics(offset 1-index 시작 줄, limit 없으면 EOF까지)로 (시작, 끝) 줄
    번호를 계산. total_lines를 모르면(파일 접근 실패) None — 판단 불가로 안전하게 스킵."""
    if offset is None and limit is None:
        return (1, total_lines) if total_lines is not None else None
    start = offset if offset is not None else 1
    if limit is not None:
        return (start, start + limit - 1)
    return (start, total_lines) if total_lines is not None else None


def _slice_for_estimate(file_path, offset, limit):
    """Read 툴과 동일한 offset(1-index)/limit 의미로 파일을 슬라이스해, 차단된 재독이
    실제로 읽었을 텍스트 크기를 추정한다. 실패 시 빈 문자열(fail-open, 추정 0)."""
    try:
        with open(file_path, "r", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return ""
    if offset is None and limit is None:
        return "".join(lines)
    start = max(0, (offset or 1) - 1)
    end = start + limit if limit else len(lines)
    return "".join(lines[start:end])


def _cleanup_old(d):
    try:
        now = time.time()
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if now - os.path.getmtime(p) > STATE_MAX_AGE_SEC:
                os.remove(p)
    except Exception:
        pass


def load_records(path):
    records = []
    if not os.path.exists(path):
        return records
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    return records


def append_record(path, record):
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def allow():
    sys.exit(0)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    cfg = load_config()
    if os.environ.get("TOKEN_SAVER_DISABLE_GUARD") == "1" or cfg.get("disabled"):
        return allow()
    large_file_lines = cfg.get("large_file_lines", LARGE_FILE_LINES)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return allow()

    if payload.get("tool_name") != "Read":
        return allow()

    session_id = payload.get("session_id")
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    offset = tool_input.get("offset")
    limit = tool_input.get("limit")

    if not session_id or not file_path:
        return allow()

    try:
        current_mtime = os.path.getmtime(file_path)
    except Exception:
        return allow()

    try:
        path = state_path(session_id)
        records = load_records(path)
    except Exception:
        return allow()

    # 최신 레코드 기준으로 두 맵 구성 (같은 세션 내 append-only 로그, 뒤에 온 게 최신)
    exact_map = {}   # (file_path, offset, limit) -> mtime
    file_map = {}    # file_path -> mtime (그 파일에 대한 가장 최근 Read)
    for r in records:
        try:
            key = (r["file_path"], r.get("offset"), r.get("limit"))
            exact_map[key] = r["mtime"]
            file_map[r["file_path"]] = r["mtime"]
        except Exception:
            continue

    key = (file_path, offset, limit)

    # 체크1: 정확히 같은 범위 재독
    if exact_map.get(key) == current_mtime:
        log_savings(session_id, "read_guard_exact",
                    estimate_tokens(_slice_for_estimate(file_path, offset, limit)))
        return deny(
            f"이미 이 세션에서 정확히 같은 범위를 읽었습니다: {file_path} "
            f"(offset={offset}, limit={limit}), 그 이후 파일도 변경되지 않았습니다. "
            "다시 Read하지 말고 이전 결과를 그대로 활용하거나, Grep으로 특정 패턴만 조회하거나, "
            "아직 안 읽은 다른 offset/limit를 지정하세요."
        )

    # 체크1b: 이미 읽은 더 넓은 범위의 부분집합 재독. 체크1(정확히 같은 offset/limit)과
    # 달리 offset/limit이 다르더라도, 같은 mtime에 이미 읽은 범위 안에 완전히 포함되면
    # 파일 내용이 안 바뀐 이상 정보 손실 없이 차단 가능(설계 원칙: 품질 손상 위험 없는
    # 결정론적 자동화만). file_map에 이 파일 기록이 있을 때만 total_lines를 계산해
    # 첫 Read(가장 흔한 경로)에 불필요한 파일 I/O를 추가하지 않는다.
    if file_path in file_map:
        try:
            with open(file_path, "r", errors="replace") as f:
                _text = f.read()
            total_lines = _text.count("\n") + (1 if _text and not _text.endswith("\n") else 0)
        except Exception:
            total_lines = None
        cur_range = _line_range(offset, limit, total_lines)
        if cur_range:
            for r in records:
                try:
                    if r["file_path"] != file_path or r["mtime"] != current_mtime:
                        continue
                    prev_range = _line_range(r.get("offset"), r.get("limit"), total_lines)
                except Exception:
                    continue
                if (prev_range and prev_range[0] <= cur_range[0] and cur_range[1] <= prev_range[1]
                        and prev_range != cur_range):
                    log_savings(session_id, "read_guard_subset",
                                estimate_tokens(_slice_for_estimate(file_path, offset, limit)))
                    return deny(
                        f"{file_path}의 {cur_range[0]}~{cur_range[1]}줄은 이미 이 세션에서 읽은 "
                        f"{prev_range[0]}~{prev_range[1]}줄 범위에 완전히 포함되며, 그 이후 파일도 "
                        "변경되지 않았습니다. 다시 Read하지 말고 이전 결과를 그대로 활용하세요."
                    )

    # 체크2: 대형 파일을 스코프 없이 재독(부분이든 전체든 이미 한 번 본 파일 대상)
    if offset is None and limit is None and file_map.get(file_path) == current_mtime:
        try:
            with open(file_path, "r", errors="replace") as f:
                full_text = f.read()
            n_lines = full_text.count("\n") + (1 if full_text and not full_text.endswith("\n") else 0)
        except Exception:
            n_lines = 0
            full_text = ""
        if n_lines > large_file_lines:
            log_savings(session_id, "read_guard_large", estimate_tokens(full_text))
            return deny(
                f"{file_path}은 {n_lines}줄로 임계값({large_file_lines}줄)을 넘고, "
                "이 세션에서 이미 읽은 적이 있으며 그 이후 변경되지 않았습니다. "
                "전체를 다시 읽지 말고 Grep으로 필요한 위치를 먼저 찾거나 "
                "offset/limit로 필요한 범위만 지정하세요."
            )

    # 허용 -> 기록
    try:
        append_record(path, {"file_path": file_path, "offset": offset, "limit": limit,
                              "mtime": current_mtime})
        _cleanup_old(state_dir())
    except Exception:
        pass
    return allow()


if __name__ == "__main__":
    main()
