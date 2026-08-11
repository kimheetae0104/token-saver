#!/usr/bin/env python3
"""hooks/check_gate.py 검증 — token_saver_check MCP 툴의 중복 호출을 결정론적으로 막는다.
pytest 없음, stdlib assert + PASS/FAIL 러너(레포 컨벤션). 실행: python3 tests/test_check_gate.py

배경(실험11, HANDOFF.md): hooks가 정상 발화 중인데도(⟢ 줄이 이미 컨텍스트에 있는데도)
모델이 token_saver_check를 중복 호출하는 사례가 실측됐다 — skills/rules/SKILL.md의
"⟢ 줄이 보이면 호출하지 마라"는 프롬프트 수준 자기감지 지시가 실전에서 안 지켜졌기
때문. 이 훅은 그 판단을 프롬프트가 아니라 코드로 옮긴다: 이 PreToolUse 훅 자체가
실행됐다는 사실이 곧 이 환경에서 hooks가 살아있다는 결정론적 증거이므로(UserPromptSubmit이
같은 턴에 이미 먼저 발화해 ⟢ 줄을 넣었을 것), token_saver_check 호출을 무조건 deny한다.
hooks가 아예 안 뜨는 환경(Windows Desktop Code 탭)에서는 이 훅 자체가 호출되지 않으므로
자동으로 fail-open — 별도 분기 불필요.
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "check_gate.py")
TOOL_NAME = "mcp__plugin_token-saver_token-saver__token_saver_check"


def _call(data_dir=None, disable_env=False, stdin_text=None):
    env = dict(os.environ)
    if data_dir:
        env["CLAUDE_PLUGIN_DATA"] = data_dir
    if disable_env:
        env["TOKEN_SAVER_DISABLE_CHECK_GATE"] = "1"
    payload = stdin_text
    if payload is None:
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": TOOL_NAME,
                               "tool_input": {}})
    proc = subprocess.run([sys.executable, HOOK], input=payload,
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    out = proc.stdout.strip()
    if not out:
        return None  # 허용
    return json.loads(out)


def _write_config(data_dir, cfg):
    with open(os.path.join(data_dir, "config.json"), "w") as f:
        json.dump({"check_gate": cfg}, f)


def test_hook_invocation_itself_denies_the_call():
    """훅이 호출됐다는 사실 자체가 hooks 정상 발화의 증거 -> 무조건 deny."""
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(data_dir=data_dir)
        assert resp is not None
        assert resp["hookSpecificOutput"]["permissionDecision"] == "deny"
        reason = resp["hookSpecificOutput"]["permissionDecisionReason"]
        assert "⟢" in reason


def test_env_kill_switch_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(data_dir=data_dir, disable_env=True)
        assert resp is None


def test_config_disabled_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_config(data_dir, {"disabled": True})
        resp = _call(data_dir=data_dir)
        assert resp is None


def test_malformed_stdin_fails_open():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(data_dir=data_dir, stdin_text="not json")
        assert resp is None


def test_malformed_config_still_denies():
    """config.json 손상 시 "게이트 비활성화"가 아니라 "게이트 유지"가 fail-safe 방향
    (ladder_gate.py와 동일 규약 — 설정 손상으로 안전장치가 조용히 풀리면 안 됨)."""
    with tempfile.TemporaryDirectory() as data_dir:
        with open(os.path.join(data_dir, "config.json"), "w") as f:
            f.write("not json")
        resp = _call(data_dir=data_dir)
        assert resp is not None
        assert resp["hookSpecificOutput"]["permissionDecision"] == "deny"


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
