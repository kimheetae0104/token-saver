"""mcp/server.py의 JSON-RPC 프로토콜 동작 검증(프로세스 스폰, stdin/stdout 파이프).
실행: python3 tests/test_mcp_server.py
실서비스 트랜스크립트 성공 경로는 여기서 안 다룬다(~/.claude/projects/ 오염 방지) —
그건 Task 7 실사용 검증에서 다룬다. 여기선 프로토콜 정합성 + '못 찾음' 진단 경로만."""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(REPO, "mcp", "server.py")


def _call(requests, env_extra=None):
    """JSON-RPC 요청 리스트를 한 프로세스에 순서대로 보내고 응답 리스트를 받는다."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, SERVER],
        input="\n".join(json.dumps(r) for r in requests) + "\n",
        capture_output=True, text=True, env=env, timeout=10,
    )
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    return [json.loads(l) for l in lines]


def test_initialize_and_tools_list():
    resp = _call([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2026-06-18"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ])
    assert resp[0]["result"]["serverInfo"]["name"] == "token-saver"
    names = {t["name"] for t in resp[1]["result"]["tools"]}
    assert "token_saver_check" in names


def test_check_tool_reports_missing_transcript_diagnostically():
    # 존재하지 않을 게 거의 확실한 project_dir -> "못 찾음" 진단(숫자 지어내지 않음)
    resp = _call(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
          "params": {"name": "token_saver_check", "arguments": {}}}],
        env_extra={"CLAUDE_PROJECT_DIR": "/nonexistent/token-saver-test-fixture-xyz"},
    )
    text = resp[0]["result"]["content"][0]["text"]
    assert "못 찾음" in text
    assert "/nonexistent/token-saver-test-fixture-xyz" in text


def test_unknown_tool_returns_error():
    resp = _call([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "no_such_tool", "arguments": {}}}])
    assert resp[0]["error"]["code"] == -32601


def test_autopsy_tool_reports_missing_transcript_diagnostically():
    resp = _call(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
          "params": {"name": "token_saver_autopsy", "arguments": {}}}],
        env_extra={"CLAUDE_PROJECT_DIR": "/nonexistent/token-saver-test-fixture-xyz"},
    )
    text = resp[0]["result"]["content"][0]["text"]
    assert "못 찾음" in text
    assert "/nonexistent/token-saver-test-fixture-xyz" in text


def test_tools_list_includes_autopsy():
    resp = _call([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    names = {t["name"] for t in resp[0]["result"]["tools"]}
    assert "token_saver_autopsy" in names


def test_tools_list_includes_config_tools():
    resp = _call([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    names = {t["name"] for t in resp[0]["result"]["tools"]}
    assert {"token_saver_config_get", "token_saver_config_set", "token_saver_config_reset"} <= names


def test_config_get_shows_defaults():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_get", "arguments": {}}}],
            env_extra={"CLAUDE_PLUGIN_DATA": data_dir},
        )
        text = resp[0]["result"]["content"][0]["text"]
        assert "read_guard" in text and "grep_trim" in text and "bash_trim" in text
        assert "large_file_lines=500" in text


def test_config_set_then_get_reflects_change():
    with tempfile.TemporaryDirectory() as data_dir:
        env = {"CLAUDE_PLUGIN_DATA": data_dir}
        set_resp = _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_set",
                         "arguments": {"hook": "bash_trim", "key": "line_threshold", "value": 50}}}],
            env_extra=env,
        )
        set_text = set_resp[0]["result"]["content"][0]["text"]
        assert "적용됨" in set_text and "50" in set_text

        get_resp = _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_get", "arguments": {}}}],
            env_extra=env,
        )
        get_text = get_resp[0]["result"]["content"][0]["text"]
        assert "line_threshold=50*" in get_text


def test_config_set_rejects_unknown_key():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_set",
                         "arguments": {"hook": "bash_trim", "key": "not_a_key", "value": 1}}}],
            env_extra={"CLAUDE_PLUGIN_DATA": data_dir},
        )
        text = resp[0]["result"]["content"][0]["text"]
        assert "설정 실패" in text


def test_config_reset_restores_default():
    with tempfile.TemporaryDirectory() as data_dir:
        env = {"CLAUDE_PLUGIN_DATA": data_dir}
        _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_set",
                         "arguments": {"hook": "bash_trim", "key": "line_threshold", "value": 50}}}],
            env_extra=env,
        )
        reset_resp = _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_reset", "arguments": {"hook": "bash_trim"}}}],
            env_extra=env,
        )
        assert "기본값으로 복원" in reset_resp[0]["result"]["content"][0]["text"]

        get_resp = _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_get", "arguments": {}}}],
            env_extra=env,
        )
        get_text = get_resp[0]["result"]["content"][0]["text"]
        assert "line_threshold=200," in get_text or "line_threshold=200 " in get_text or get_text.count(
            "line_threshold=200") >= 1


def test_config_get_includes_prompt_gate():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_get", "arguments": {}}}],
            env_extra={"CLAUDE_PLUGIN_DATA": data_dir},
        )
        text = resp[0]["result"]["content"][0]["text"]
        assert "prompt_gate" in text, text


def test_config_set_accepts_prompt_gate_hook():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_set",
                         "arguments": {"hook": "prompt_gate", "key": "disabled", "value": True}}}],
            env_extra={"CLAUDE_PLUGIN_DATA": data_dir},
        )
        text = resp[0]["result"]["content"][0]["text"]
        assert "적용됨" in text, text


def test_config_get_includes_ladder_gate():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_get", "arguments": {}}}],
            env_extra={"CLAUDE_PLUGIN_DATA": data_dir},
        )
        text = resp[0]["result"]["content"][0]["text"]
        assert "ladder_gate" in text, text


def test_config_set_accepts_ladder_gate_hook():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "token_saver_config_set",
                         "arguments": {"hook": "ladder_gate", "key": "disabled", "value": True}}}],
            env_extra={"CLAUDE_PLUGIN_DATA": data_dir},
        )
        text = resp[0]["result"]["content"][0]["text"]
        assert "적용됨" in text, text


def test_tools_list_includes_suggest_tier():
    resp = _call([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    names = {t["name"] for t in resp[0]["result"]["tools"]}
    assert "token_saver_suggest_tier" in names


def test_suggest_tier_tool_default_recommends_sonnet():
    resp = _call([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "token_saver_suggest_tier", "arguments": {}}}])
    text = resp[0]["result"]["content"][0]["text"]
    assert text.startswith("추천: sonnet"), text


def test_suggest_tier_tool_with_oracle_recommends_haiku():
    resp = _call([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "token_saver_suggest_tier",
                              "arguments": {"has_oracle": True}}}])
    text = resp[0]["result"]["content"][0]["text"]
    assert text.startswith("추천: haiku"), text


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
