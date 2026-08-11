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
          include_session_id=True):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": {}}
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
