"""mcp/server.py의 JSON-RPC 프로토콜 동작 검증(프로세스 스폰, stdin/stdout 파이프).
실행: python3 tests/test_mcp_server.py
실서비스 트랜스크립트 성공 경로는 여기서 안 다룬다(~/.claude/projects/ 오염 방지) —
그건 Task 7 실사용 검증에서 다룬다. 여기선 프로토콜 정합성 + '못 찾음' 진단 경로만."""
import json
import os
import subprocess
import sys

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
