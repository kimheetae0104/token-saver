#!/usr/bin/env python3
"""hooks/ladder_gate.py 검증 — Agent 위임 전 token_saver_suggest_tier 컨설트 강제 게이트.
pytest 없음, stdlib assert + PASS/FAIL 러너(레포 컨벤션). 실행: python3 tests/test_ladder_gate.py
"""
import json
import os
import subprocess
import sys
import tempfile
import threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "ladder_gate.py")


def _call(session_id="sess-1", mode=None, tool_name="Agent", data_dir=None, disable=False,
          include_session_id=True, tool_input=None, tool_output=None):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool_name,
               "tool_input": tool_input if tool_input is not None else {}}
    if tool_output is not None:
        payload["tool_output"] = tool_output
    if include_session_id:
        payload["session_id"] = session_id
    env = dict(os.environ)
    if data_dir:
        env["CLAUDE_PLUGIN_DATA"] = data_dir
    if disable:
        env["TOKEN_SAVER_DISABLE_LADDER_GATE"] = "1"
    args = [sys.executable, HOOK]
    if mode:
        args.append(mode)
    proc = subprocess.run(args, input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    out = proc.stdout.strip()
    if not out:
        return None  # 허용
    return json.loads(out)


def _write_config(data_dir, cfg):
    with open(os.path.join(data_dir, "config.json"), "w") as f:
        json.dump({"ladder_gate": cfg}, f)


def _state_path(data_dir, session_id):
    return os.path.join(data_dir, "ladder_gate", f"{session_id}.json")


def test_no_state_denies_by_default():
    """리셋 전(신규 세션) — 미확인 상태가 기본값이므로 첫 Agent 호출은 막힌다."""
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(data_dir=data_dir)
        assert resp is not None
        assert resp["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_reset_then_gate_denies():
    with tempfile.TemporaryDirectory() as data_dir:
        r = _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        assert r is None  # --reset은 항상 allow
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is not None
        assert "token_saver_suggest_tier" in resp["hookSpecificOutput"]["permissionDecisionReason"]


def test_mark_consulted_then_gate_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        r = _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        assert r is None
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is None


def test_consulted_allows_multiple_subsequent_agent_calls():
    """prompt_gate와 달리 1회성 트립이 아니다 — consulted 되면 이번 턴 내내 계속 허용."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        for _ in range(3):
            assert _call(session_id="sess-1", data_dir=data_dir) is None


def test_next_turn_reset_requires_consult_again():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        assert _call(session_id="sess-1", data_dir=data_dir) is None
        # 다음 턴 시작 -> 리셋
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is not None


def test_missing_session_id_allows():
    resp = _call(data_dir=None, include_session_id=False)
    assert resp is None


def test_malformed_stdin_fails_open():
    proc = subprocess.run([sys.executable, HOOK], input="not json{{{",
                          capture_output=True, text=True, env=dict(os.environ), timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_corrupt_state_file_fails_open_to_deny_default():
    """상태파일이 손상돼도 예외로 죽지 않는다 — read_state가 {}로 폴백해 미확인 취급(안전 기본값)."""
    with tempfile.TemporaryDirectory() as data_dir:
        d = os.path.join(data_dir, "ladder_gate")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sess-1.json"), "w") as f:
            f.write("not json{{{")
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is not None  # 손상 -> consulted 없음 취급 -> deny(도구 호출 자체는 안 깨짐)


def test_kill_switch_disables():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(session_id="sess-1", data_dir=data_dir, disable=True)
        assert resp is None


def test_config_disabled_skips_gate():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_config(data_dir, {"disabled": True})
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is None


def test_env_kill_switch_wins_over_config_enabled():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_config(data_dir, {"disabled": False})
        resp = _call(session_id="sess-1", data_dir=data_dir, disable=True)
        assert resp is None


def test_non_dict_config_value_fails_open():
    with tempfile.TemporaryDirectory() as data_dir:
        with open(os.path.join(data_dir, "config.json"), "w") as f:
            json.dump({"ladder_gate": "oops"}, f)
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is None


def test_concurrent_agent_calls_all_deny_consistently_when_unconsulted():
    """병렬 배치 패턴(CLAUDE.md 권장) — consulted 안 됐으면 동시에 여러 Agent 호출이 나가도
    prompt_gate처럼 '정확히 1개만'이 아니라 전부 동일하게 deny돼야 한다(단순 플래그 읽기라
    원자적 클레임 불필요 — 다르면 설계 위반)."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-race", mode="--reset", data_dir=data_dir)
        N = 8
        results = [None] * N

        def call(idx):
            resp = _call(session_id="sess-race", data_dir=data_dir)
            results[idx] = "DENY" if resp is not None else "ALLOW"

        threads = [threading.Thread(target=call, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count("DENY") == N, results


def test_mark_consulted_extracts_recommended_tier():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output="추천: haiku(effort=low) — 오라클로 저비용 검증 가능")
        with open(_state_path(data_dir, "sess-1")) as f:
            state = json.load(f)
        assert state["recommended_tier"] == "haiku", state


def test_mark_consulted_extracts_tier_from_mcp_content_shape():
    """MCP 응답이 {"content":[{"type":"text","text":...}]} 구조로 올 수도 있는 경로."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output={"content": [{"type": "text", "text": "추천: opus(effort=high) — ..."}]})
        with open(_state_path(data_dir, "sess-1")) as f:
            state = json.load(f)
        assert state["recommended_tier"] == "opus", state


def test_mark_consulted_extracts_tier_from_bare_list_shape():
    """실전 MCP 페이로드는 tool_response 필드 자체가 {"content":[...]} 딕셔너리가 아니라
    바로 [{"type":"text","text":...}] 리스트로 오는 경우가 있다(실측, 2026-08-11 로드맵 1순위 —
    그동안 이 경로가 없어 mismatch 재확인·usage 로깅이 조용히 죽어 있었다)."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output=[{"type": "text", "text": "추천: sonnet(effort=high) — ..."}])
        with open(_state_path(data_dir, "sess-1")) as f:
            state = json.load(f)
        assert state["recommended_tier"] == "sonnet", state


def test_mark_consulted_extracts_tier_from_multi_block_list_leading_non_text():
    """리스트에 여러 블록이 있고 첫 블록엔 text가 없는 경우 — 2026-08-12 적대적 재검증에서
    반박 성공한 케이스(당시 코드는 val[0]만 봐서 뒤쪽 블록의 유효한 text를 놓쳤다)."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output=[{"type": "other"}, {"type": "text", "text": "추천: opus(effort=high) — ..."}])
        with open(_state_path(data_dir, "sess-1")) as f:
            state = json.load(f)
        assert state["recommended_tier"] == "opus", state


def test_mark_consulted_extracts_tier_from_content_as_plain_string():
    """content가 리스트가 아니라 문자열 그대로 오는 배선(2026-08-12 적대적 재검증)."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output={"content": "추천: sonnet(effort=high) — ..."})
        with open(_state_path(data_dir, "sess-1")) as f:
            state = json.load(f)
        assert state["recommended_tier"] == "sonnet", state


def test_mark_consulted_extracts_tier_from_bare_content_block_dict():
    """"content" 래퍼 없이 단일 content-block dict({"type":"text","text":...})가 그대로
    오는 배선(bare-list 케이스의 dict 버전, 2026-08-12 적대적 재검증)."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output={"type": "text", "text": "추천: sonnet(effort=high) — ..."})
        with open(_state_path(data_dir, "sess-1")) as f:
            state = json.load(f)
        assert state["recommended_tier"] == "sonnet", state


def test_mismatched_tier_denies_once_then_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output="추천: haiku(effort=low) — ...")
        resp = _call(session_id="sess-1", data_dir=data_dir,
                     tool_input={"model": "claude-sonnet-5-20260101"})
        assert resp is not None
        assert "haiku" in resp["hookSpecificOutput"]["permissionDecisionReason"]
        assert "sonnet" in resp["hookSpecificOutput"]["permissionDecisionReason"]
        # 재시도는 통과(강제 차단이 아니라 1회 확인용)
        resp2 = _call(session_id="sess-1", data_dir=data_dir,
                      tool_input={"model": "claude-sonnet-5-20260101"})
        assert resp2 is None


def test_matching_tier_allows_without_extra_prompt():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output="추천: haiku(effort=low) — ...")
        resp = _call(session_id="sess-1", data_dir=data_dir,
                     tool_input={"model": "claude-haiku-4-5-20251001"})
        assert resp is None


def test_no_model_specified_skips_mismatch_check():
    """Agent 호출에 model을 아예 안 넘기면(흔한 경우 — 부모 모델 상속) 비교 자체를 생략."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output="추천: haiku(effort=low) — ...")
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={})
        assert resp is None


def test_no_recommended_tier_parsed_skips_mismatch_check():
    """suggest_tier 응답 파싱이 실패해도(형식 예상 밖) 기본 게이트는 그대로 동작 — fail-open."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output="이상한 형식의 응답")
        resp = _call(session_id="sess-1", data_dir=data_dir,
                     tool_input={"model": "claude-opus-5-20260101"})
        assert resp is None


def _events_path(data_dir, session_id):
    return os.path.join(data_dir, "ladder_gate_events", f"{session_id}.jsonl")


def _read_events(data_dir, session_id):
    path = _events_path(data_dir, session_id)
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def test_matched_call_logs_resolution_with_matched_true():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output="추천: haiku(effort=low) — ...")
        _call(session_id="sess-1", data_dir=data_dir,
              tool_input={"model": "claude-haiku-4-5-20251001"})
        events = _read_events(data_dir, "sess-1")
        assert len(events) == 1, events
        assert events[0]["recommended_tier"] == "haiku", events
        assert events[0]["requested_tier"] == "haiku", events
        assert events[0]["matched"] is True, events


def test_no_model_call_logs_resolution_with_matched_none():
    """model 파라미터를 안 넘긴 흔한 경우 — matched는 '모름'을 뜻하는 None으로 남는다."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output="추천: sonnet(effort=default) — ...")
        _call(session_id="sess-1", data_dir=data_dir, tool_input={})
        events = _read_events(data_dir, "sess-1")
        assert len(events) == 1, events
        assert events[0]["requested_tier"] is None, events
        assert events[0]["matched"] is None, events


def test_mismatch_then_retry_logs_matched_false_not_the_deny():
    """불일치 재확인(deny) 자체는 로그되지 않고, 그 뒤 실제로 통과된 호출만 로그된다 —
    deny는 병렬 재시도 등으로 여러 번 뜰 수 있어 그대로 로그하면 부풀려짐."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output="추천: haiku(effort=low) — ...")
        _call(session_id="sess-1", data_dir=data_dir,
              tool_input={"model": "claude-sonnet-5-20260101"})  # deny (불일치 1회)
        _call(session_id="sess-1", data_dir=data_dir,
              tool_input={"model": "claude-sonnet-5-20260101"})  # 재시도 -> allow
        events = _read_events(data_dir, "sess-1")
        assert len(events) == 1, events  # deny 턴은 로그 안 됨
        assert events[0]["matched"] is False, events
        assert events[0]["requested_tier"] == "sonnet", events


def test_multiple_agent_calls_same_turn_log_multiple_resolutions():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output="추천: haiku(effort=low) — ...")
        for _ in range(3):
            _call(session_id="sess-1", data_dir=data_dir,
                  tool_input={"model": "claude-haiku-4-5-20251001"})
        events = _read_events(data_dir, "sess-1")
        assert len(events) == 3, events


def test_no_recommended_tier_skips_resolution_logging():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir,
              tool_output="이상한 형식")  # 파싱 실패 -> recommended_tier 없음
        _call(session_id="sess-1", data_dir=data_dir,
              tool_input={"model": "claude-opus-5-20260101"})
        assert _read_events(data_dir, "sess-1") == []


def test_pipeline_signal_with_small_batch_denies_once_then_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "각 항목을 생성하고 판정한 뒤 비용을 측정해서 보고해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is not None
        reason = resp["hookSpecificOutput"]["permissionDecisionReason"]
        assert "다단계 파이프라인" in reason
        assert "3.495배" in reason
        # 재시도(2번째 호출)는 통과 — 강제 변경이 아니라 1회 확인
        resp2 = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp2 is None


def test_pipeline_signal_with_large_batch_allows_immediately():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "30건을 생성하고 판정한 뒤 측정해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is None


def test_single_stage_category_allows():
    """단계어가 1개 카테고리만 매치되면(다단계 아님) 배치 크기와 무관하게 허용."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "이 버그를 판정해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is None


def test_small_explicit_batch_denies():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "15건을 생성하고 판정해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is not None


def test_pipeline_batch_kill_switch_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "생성하고 판정한 뒤 측정해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt},
                     disable=True)
        assert resp is None


def test_pipeline_batch_config_disabled_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_config(data_dir, {"disabled": True})
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        prompt = "생성하고 판정한 뒤 측정해줘"
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is None


def test_reset_clears_pipeline_batch_acknowledged():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "생성하고 판정한 뒤 측정해줘"
        _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})  # 최초 deny
        # 다음 턴: --reset이 다시 돌면 acknowledged도 초기화되어야 함
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})
        assert resp is not None  # 리셋됐으니 다시 최초 deny


def test_pipeline_batch_flag_logs_event_each_time():
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        prompt = "생성하고 판정한 뒤 측정해줘"
        _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})  # deny
        events = [e for e in _read_events(data_dir, "sess-1")
                  if e["event"] == "pipeline_batch_flagged"]
        assert len(events) == 1, events
        assert events[0]["acknowledged"] is False, events

        _call(session_id="sess-1", data_dir=data_dir, tool_input={"prompt": prompt})  # 재시도, allow
        events2 = [e for e in _read_events(data_dir, "sess-1")
                   if e["event"] == "pipeline_batch_flagged"]
        assert len(events2) == 2, events2
        assert events2[1]["acknowledged"] is True, events2


def test_no_prompt_field_skips_pipeline_batch_check():
    """tool_input에 prompt가 아예 없으면(비정상 배선) 예외 없이 그냥 통과."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call(session_id="sess-1", mode="--reset", data_dir=data_dir)
        _call(session_id="sess-1", mode="--mark-consulted", data_dir=data_dir)
        resp = _call(session_id="sess-1", data_dir=data_dir, tool_input={})
        assert resp is None


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
