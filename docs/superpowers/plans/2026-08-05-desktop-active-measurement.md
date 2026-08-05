# Desktop Code 탭 능동 계측 복원 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Desktop 앱 Code 탭(hooks 미발화, `desktop/desktop#22138` closed-as-not-planned)에서
token-saver의 능동 계측(매 턴 효율 줄·세션 부검·실패 사례 수집)을 MCP 서버로, 텍스트 코칭 규칙을
전역 Skill로 복원해 "설치한 모든 프로젝트"에 적용되게 한다.

**Architecture:** `measure.py`의 계산 로직을 파일-경로 인자만 받는 순수 함수로 추출해
CLI(`do_*`, stdin 기반)와 신규 MCP 서버(`mcp/server.py`, 인자 없음, 자체 프로젝트 탐색)가
공유한다. 전역 `skills/token-saver-rules/SKILL.md`가 두 MCP 툴(`token_saver_check`/
`token_saver_autopsy`) 호출 시점을 지시하고, hooks가 이미 발화 중이면 자기감지로 무동작한다.

**Tech Stack:** Python 3 stdlib만(기존 repo 컨벤션 유지, 신규 의존성 0). MCP는 SDK 없이 JSON-RPC
2.0 stdio를 손수 구현(환경에 `mcp`/`@modelcontextprotocol/sdk` 미설치 확인됨, AI-YAGNI).

## Global Constraints
- 신규 의존성 추가 금지 — stdlib만 사용(레포 기존 컨벤션, `experiments/desktop_mcp_probe/probe_server.py`에서 이미 검증된 패턴 재사용).
- 기존 CLI 동작(hooks 경로) 무회귀 — `latest_session()`/`TRANSCRIPT_DIR` 리팩터는 기본값 동작이 리팩터 전과 바이트 단위로 동일해야 함.
- 숫자를 지어내지 않는다 — MCP 툴이 트랜스크립트를 못 찾으면 "측정 불가" 진단 메시지를 반환하지, 값을 추정/생략하지 않는다.
- 모든 신규 함수·파일에 한국어 주석 스타일 유지(레포 기존 컨벤션).
- 스펙: `docs/superpowers/specs/2026-08-05-desktop-active-measurement-design.md` (모든 태스크의 근거).

---

### Task 1: `measure.py` — 순수 함수 추출 + 프로젝트 무관 일반화

**Files:**
- Modify: `measure.py:34-35` (TRANSCRIPT_DIR), `:359-362` (latest_session), `:566-577` (print_autopsy), `:636-665` (do_check), `:668-684` (do_capture_failures)
- Create: `tests/test_measure_refactor.py`

**Interfaces:**
- Produces: `measure.transcript_dir(project_dir=None) -> str`, `measure.latest_session(project_dir=None) -> str|None`, `measure.check_line(path) -> str`, `measure.autopsy_text(path) -> str`, `measure.capture_failures_text(path, data_dir=None) -> str` — Task 2/3의 `mcp/server.py`가 이 5개를 그대로 import해서 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_measure_refactor.py`:
```python
"""measure.py 순수 함수 리팩터 검증. pytest 없이 stdlib assert만(레포 컨벤션).
실행: python3 tests/test_measure_refactor.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import measure

FIXTURE = """\
{"message": {"role": "user", "content": "hello"}, "timestamp": "2026-08-05T00:00:00Z"}
{"message": {"role": "assistant", "content": [{"type": "text", "text": "hi there"}], "usage": {"input_tokens": 500, "cache_creation_input_tokens": 200, "cache_read_input_tokens": 1000, "output_tokens": 300}, "model": "claude-sonnet-5-20260101"}, "timestamp": "2026-08-05T00:00:01Z"}
{"message": {"role": "user", "content": "thanks"}, "timestamp": "2026-08-05T00:00:02Z"}
{"message": {"role": "assistant", "content": [{"type": "text", "text": "you're welcome"}], "usage": {"input_tokens": 100, "cache_creation_input_tokens": 50, "cache_read_input_tokens": 5000, "output_tokens": 80}, "model": "claude-sonnet-5-20260101"}, "timestamp": "2026-08-05T00:00:03Z"}
"""


def test_transcript_dir_sanitizes_and_defaults():
    # project_dir 명시 -> 비영숫자를 '-'로 치환한 경로
    got = measure.transcript_dir("/Volumes/Extreme SSD/worktree/token-saver")
    assert got == os.path.expanduser(
        "~/.claude/projects/-Volumes-Extreme-SSD-worktree-token-saver")
    # 인자 없으면 기존 TRANSCRIPT_DIR 상수와 완전히 동일(하위호환, 무회귀)
    assert measure.transcript_dir() == measure.TRANSCRIPT_DIR


def test_check_line_exact_output():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fake-session.jsonl")
        with open(path, "w") as f:
            f.write(FIXTURE)
        line = measure.check_line(path)
        assert line == "⟢ 턴2 · 7,230tok · hit 96% · $0.0068 · 효율74", line


def test_check_line_missing_file_returns_empty():
    assert measure.check_line("/no/such/file.jsonl") == ""
    assert measure.check_line(None) == ""


def test_autopsy_text_has_header():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fake-session.jsonl")
        with open(path, "w") as f:
            f.write(FIXTURE)
        text = measure.autopsy_text(path)
        assert text.startswith("== 낭비 부검 ==")
        assert os.path.basename(path) in text


def test_capture_failures_text_no_subagents_is_empty():
    # 서브에이전트 디렉터리가 없으면 candidates=[] -> "" (조용히, 파일 I/O 없음)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "fake-session.jsonl")
        with open(path, "w") as f:
            f.write(FIXTURE)
        assert measure.capture_failures_text(path) == ""


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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_measure_refactor.py`
Expected: `AttributeError: module 'measure' has no attribute 'transcript_dir'` (또는 `check_line`/`autopsy_text`/`capture_failures_text` 중 먼저 참조되는 것) — 아직 구현 전이라 실패.

- [ ] **Step 3: `measure.py` 리팩터**

`measure.py:34-35`을 다음으로 교체:
```python
def transcript_dir(project_dir=None):
    """Claude Code 세션 저장 규칙: ~/.claude/projects/<프로젝트 경로의 비영숫자를 '-'로 치환>/.
    project_dir 기본값은 이 스크립트 파일의 디렉터리 — 레포 자체를 CLI로 실행할 때 프로젝트
    폴더가 이동해도 안 깨지는 기존 설계를 그대로 보존한다(2026-08-04 실제로 겪은 문제, 위 주석
    참고). MCP 서버처럼 *다른* 프로젝트를 대신 찾아야 하는 호출부는 반드시 project_dir을 명시로
    넘길 것 — 안 그러면 이 스크립트가 설치된 플러그인 디렉터리를 프로젝트로 착각한다."""
    project_dir = project_dir or os.path.dirname(os.path.abspath(__file__))
    return os.path.expanduser(
        "~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", project_dir))


TRANSCRIPT_DIR = transcript_dir()  # 하위호환 상수 — print_all() 등 기존 참조부 그대로 동작
```

`measure.py:359-362`(`latest_session`)을 다음으로 교체:
```python
def latest_session(project_dir=None):
    files = sorted(glob.glob(os.path.join(transcript_dir(project_dir), "*.jsonl")),
                   key=os.path.getmtime)
    return files[-1] if files else None
```

`measure.py:566-577`(`print_autopsy`)을 다음으로 교체:
```python
def autopsy_text(path):
    """세션 낭비 부검 리포트 문자열. print_autopsy()·MCP 서버 공용."""
    if not path or not os.path.isfile(path):
        return ""
    sess = parse_session(path)
    tot, per_turn = aggregate(sess)
    px = proxies(sess, per_turn)
    finds = autopsy(tot, px, per_turn)
    lines = [f"== 낭비 부검 ==  {os.path.basename(path)}"]
    if not finds:
        lines.append("  이상 신호 없음. 효율 양호.")
    else:
        for f in finds:
            lines.append(f"  [{f['sev'].upper():4}] {f['name']}: {f['detail']}")
            lines.append(f"         → {f['tip']}")
    return "\n".join(lines)


def print_autopsy(path):
    text = autopsy_text(path)
    if text:
        print(text)
```

`measure.py:636-665`(`do_check`) 바로 앞에 `check_line`을 추가하고 `do_check` 본체를 축약:
```python
def check_line(path):
    """세션 효율 한 줄(+조건부 경고) 문자열. 없으면 "". do_check()·MCP 서버 공용."""
    if not path or not os.path.isfile(path):
        return ""
    sess = parse_session(path)
    tot, per_turn = aggregate(sess)
    if not per_turn:
        return ""
    px = proxies(sess, per_turn)
    score = efficiency_score(tot, px)
    msgs = [f"⟢ 턴{tot['turns']} · {fmt(tot['total_tokens'])}tok · "
            f"hit {tot['cache_hit']*100:.0f}% · {money(tot['cost'])} · 효율{score:.0f}"]
    last = per_turn[-1]["total_input"]
    if last > THRESH["sunk_input"]:
        msgs.append(f"⚠️ 컨텍스트 {last:,} 토큰 — 작업 경계면 /compact, 무관 작업이면 /clear 권장")
    if tot["cache_hit"] < THRESH["cache_hit_low"] and tot["turns"] > 6:
        msgs.append(f"⚠️ 캐시 적중률 {tot['cache_hit']*100:.0f}% — 모델·effort 전환 자제")
    return " ".join(msgs)


def do_check():
    """UserPromptSubmit hook용: stdin JSON → check_line() 결과 출력(있으면)."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    path = payload.get("transcript_path") or latest_session()
    line = check_line(path)
    if line:
        print(line)
```

`measure.py:668-684`(`do_capture_failures`)를 다음으로 교체:
```python
def capture_failures_text(path, data_dir=None):
    """실패 후보 포착 요약 문자열. 없으면 "". do_capture_failures()·MCP 서버 공용.
    data_dir이 주어지면(플러그인 설치 시 ${CLAUDE_PLUGIN_DATA}) 그 경로에 쓴다 —
    ${CLAUDE_PLUGIN_ROOT}는 플러그인 업데이트마다 바뀌는 임시 경로라 로그 유실 위험이 있어서다."""
    path = path or latest_session()
    if not path or not os.path.isfile(path):
        return ""
    log_path = os.path.join(data_dir, "production_failures.jsonl") if data_dir else None
    candidates = capture_failures(path, log_path=log_path)
    if not candidates:
        return ""
    kinds = {}
    for c in candidates:
        kinds[c["type"]] = kinds.get(c["type"], 0) + 1
    detail = ", ".join(f"{k}×{v}" for k, v in kinds.items())
    return f"📋 실패 후보 {len(candidates)}건 포착({detail}) → {log_path or PRODUCTION_LOG}"


def do_capture_failures(path, data_dir=None):
    text = capture_failures_text(path, data_dir=data_dir)
    if text:
        print(text)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_measure_refactor.py`
Expected: `5/5 passed`

- [ ] **Step 5: 기존 CLI 무회귀 수동 확인**

Run: `python3 measure.py --check < /dev/null` (최신 실세션 대상, 인자 없이 stdin 빈 값 → `latest_session()` 폴백 경로)
Expected: 이 세션의 실제 `⟢ 턴...` 줄이 리팩터 전과 같은 포맷으로 출력됨(에러 없음).

- [ ] **Step 6: 커밋**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver"
git add measure.py tests/test_measure_refactor.py
git commit -m "Extract measure.py's check/autopsy/capture-failures into path-only pure functions

Prep for the Desktop MCP server (Task 2+): it needs the same math without a
hook-supplied transcript_path or stdin. transcript_dir()/latest_session() also
gain an explicit project_dir param -- the module-level default stays anchored
to __file__ (unchanged, preserves the 2026-08-04 move-safety fix), but callers
representing a *different* project (e.g. the MCP server) can now pass one in.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `mcp/server.py` — JSON-RPC 코어 + `token_saver_check` 툴

**Files:**
- Create: `mcp/server.py`
- Create: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `measure.latest_session(project_dir=None)`, `measure.check_line(path)`, `measure.transcript_dir(project_dir=None)` (Task 1 산출물)
- Produces: `mcp/server.py`의 `TOOLS` dict(이름→`{"description", "handler"}`) — Task 3이 여기에 `token_saver_autopsy` 엔트리를 추가한다. `resolve_project_dir()` 함수도 Task 3에서 재사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_mcp_server.py`:
```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_mcp_server.py`
Expected: `FileNotFoundError` 또는 유사 오류 — `mcp/server.py`가 아직 없음.

- [ ] **Step 3: `mcp/server.py` 구현**

```python
#!/usr/bin/env python3
"""token-saver MCP 서버 — Desktop Code 탭에서 hooks 대신 능동 계측을 복원한다.

Desktop 앱 Code 탭(Claude Code를 stream-json server/API 모드로 구동)은 hooks가
발화하지 않는다(desktop/desktop#22138, closed as not planned) — 하지만 MCP는 살아있다
(experiments/desktop_mcp_probe/probe_server.py로 실측 확인, 2026-08-05). 이 서버가
measure.py의 계측 로직을 툴로 노출해 그 공백을 best-effort로 메운다.

의존성 없음(mcp/@modelcontextprotocol/sdk 미설치 환경 대응) — JSON-RPC 2.0을
stdin/stdout에 한 줄씩(뉴라인 구분, Content-Length 프레이밍 아님) 손수 구현.
로깅은 전부 stderr(그래야 stdout의 JSON-RPC 스트림이 안 깨짐).

설계: docs/superpowers/specs/2026-08-05-desktop-active-measurement-design.md
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import measure  # noqa: E402


def log(msg):
    print(f"[token-saver-mcp] {msg}", file=sys.stderr, flush=True)


def resolve_project_dir():
    """CLAUDE_PROJECT_DIR이 있으면 우선(플러그인 host가 넘겨줄 것으로 기대 — Desktop에서
    실제로 세팅되는지는 Task 7에서 실측 확인 예정). 없으면 cwd로 폴백해 최소한 로컬
    수동 실행은 항상 동작하게 한다."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def tool_check():
    project_dir = resolve_project_dir()
    path = measure.latest_session(project_dir=project_dir)
    line = measure.check_line(path)
    if line:
        return line
    return (f"세션 트랜스크립트를 못 찾음 — project_dir={project_dir}, "
            f"탐색 경로={measure.transcript_dir(project_dir)}")


TOOLS = {
    "token_saver_check": {
        "description": (
            "이 프로젝트의 현재 세션 토큰/비용/캐시적중률/효율점수를 한 줄로 반환한다. "
            "CLI/IDE에서는 시스템 컨텍스트에 '⟢ 턴...' 줄이 이미 자동으로 보이므로(훅 정상 "
            "발화 중) 이 툴을 다시 호출하지 말 것 — Desktop Code 탭처럼 그 줄이 안 보일 때만 호출."
        ),
        "handler": tool_check,
    },
}


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(msg):
    mid = msg.get("id")
    method = msg.get("method")

    if method == "initialize":
        send({
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": msg.get("params", {}).get("protocolVersion", "2026-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "token-saver", "version": "0.1.0"},
            },
        })
    elif method == "notifications/initialized":
        log("client initialized")
    elif method == "tools/list":
        send({
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "tools": [
                    {"name": name, "description": spec["description"],
                     "inputSchema": {"type": "object", "properties": {}}}
                    for name, spec in TOOLS.items()
                ]
            },
        })
    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        spec = TOOLS.get(name)
        if spec is None:
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": f"unknown tool {name}"}})
            return
        try:
            text = spec["handler"]()
        except Exception as e:
            log(f"tool {name} failed: {e}")
            text = f"내부 오류: {e}"
        send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}]}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    elif mid is not None:
        send({"jsonrpc": "2.0", "id": mid,
              "error": {"code": -32601, "message": f"unknown method {method}"}})
    # else: 미지원 notification -- 조용히 무시(스펙대로).


def main():
    log(f"server started, pid={os.getpid()}, tools={list(TOOLS)}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log(f"bad json: {line!r}")
            continue
        try:
            handle(msg)
        except Exception as e:
            log(f"handler error: {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_mcp_server.py`
Expected: `3/3 passed`

- [ ] **Step 5: 커밋**

```bash
git add mcp/server.py tests/test_mcp_server.py
git commit -m "Add token-saver MCP server core + token_saver_check tool

Dependency-free stdio JSON-RPC (same pattern as the probe spike). Wraps
measure.py's check_line() via an explicit project_dir so it works when
installed as a plugin in a different project than measure.py's own file.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `token_saver_autopsy` 툴 추가

**Files:**
- Modify: `mcp/server.py` (TOOLS dict에 엔트리 추가)
- Modify: `tests/test_mcp_server.py` (테스트 추가)

**Interfaces:**
- Consumes: `measure.autopsy_text(path)`, `measure.capture_failures_text(path, data_dir=None)` (Task 1 산출물), `resolve_project_dir()` (Task 2 산출물)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_mcp_server.py`에 추가(`test_unknown_tool_returns_error` 함수 뒤):
```python
def test_autopsy_tool_reports_missing_transcript_diagnostically():
    resp = _call(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
          "params": {"name": "token_saver_autopsy", "arguments": {}}}],
        env_extra={"CLAUDE_PROJECT_DIR": "/nonexistent/token-saver-test-fixture-xyz"},
    )
    text = resp[0]["result"]["content"][0]["text"]
    assert "못 찾음" in text


def test_tools_list_includes_autopsy():
    resp = _call([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    names = {t["name"] for t in resp[0]["result"]["tools"]}
    assert "token_saver_autopsy" in names
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_mcp_server.py`
Expected: `test_autopsy_tool_reports_missing_transcript_diagnostically` FAIL(`token_saver_autopsy` 툴이 없어 `error` 키만 있고 `result`가 없음 → KeyError), `test_tools_list_includes_autopsy` FAIL(assert False).

- [ ] **Step 3: `mcp/server.py`에 `tool_autopsy` + TOOLS 엔트리 추가**

`tool_check()` 함수 뒤에 추가:
```python
def tool_autopsy():
    project_dir = resolve_project_dir()
    path = measure.latest_session(project_dir=project_dir)
    if not path or not os.path.isfile(path):
        return f"세션 트랜스크립트를 못 찾음 — project_dir={project_dir}"
    parts = [measure.autopsy_text(path)]
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    cap = measure.capture_failures_text(path, data_dir=data_dir)
    if cap:
        parts.append(cap)
    return "\n".join(parts)
```

`TOOLS` dict을 다음으로 교체(엔트리 추가):
```python
TOOLS = {
    "token_saver_check": {
        "description": (
            "이 프로젝트의 현재 세션 토큰/비용/캐시적중률/효율점수를 한 줄로 반환한다. "
            "CLI/IDE에서는 시스템 컨텍스트에 '⟢ 턴...' 줄이 이미 자동으로 보이므로(훅 정상 "
            "발화 중) 이 툴을 다시 호출하지 말 것 — Desktop Code 탭처럼 그 줄이 안 보일 때만 호출."
        ),
        "handler": tool_check,
    },
    "token_saver_autopsy": {
        "description": (
            "이 프로젝트 현재 세션의 낭비 신호 부검(컨텍스트 비대·캐시 스래싱·rework 등)을 "
            "반환하고 실패 후보를 로그에 기록한다. 대화가 마무리되는 느낌일 때(사용자의 마무리 "
            "인사·'여기까지'류) 한 번만 호출해 요약을 짧게 보여주고 그 외엔 언급하지 말 것."
        ),
        "handler": tool_autopsy,
    },
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_mcp_server.py`
Expected: `5/5 passed`

- [ ] **Step 5: 커밋**

```bash
git add mcp/server.py tests/test_mcp_server.py
git commit -m "Add token_saver_autopsy MCP tool (waste report + failure capture)

Mirrors hooks/session_autopsy.sh's two calls (autopsy_text + capture_failures_text)
in one tool, since Desktop has no Stop event to split them across.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: 플러그인에 MCP 서버 등록 + validate

**Files:**
- Modify: `.mcp.json` (프로브 엔트리 → 프로덕션 엔트리로 교체)

**Interfaces:**
- Consumes: `mcp/server.py`(Task 2+3 산출물)

- [ ] **Step 1: `.mcp.json` 교체**

현재 내용(프로브용, 폐기):
```json
{
  "mcpServers": {
    "token-saver-probe": {
      "command": "python3",
      "args": ["${CLAUDE_PROJECT_DIR}/experiments/desktop_mcp_probe/probe_server.py"]
    }
  }
}
```
다음으로 교체:
```json
{
  "mcpServers": {
    "token-saver": {
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp/server.py"],
      "env": {
        "CLAUDE_PLUGIN_DATA": "${CLAUDE_PLUGIN_DATA}"
      }
    }
  }
}
```
(`${CLAUDE_PLUGIN_ROOT}` 사용 — 프로브 때 쓴 `${CLAUDE_PROJECT_DIR}`은 이 repo에서 개발 중엔
플러그인 위치와 프로젝트 위치가 같아 우연히 맞았을 뿐, 다른 프로젝트에 설치되면 틀린 경로가 됨.
공식 스키마 확인: code.claude.com/docs/en/plugins-reference "MCP servers" 섹션.
`CLAUDE_PLUGIN_DATA`를 `env`로 명시 재전달하는 건 `hooks/hooks.json`의 기존 Stop 훅과 동일한
방어적 패턴.)

- [ ] **Step 2: 플러그인 매니페스트 validate**

Run: `cd "/Volumes/Extreme SSD/worktree/token-saver" && claude plugin validate .`
Expected: 통과(에러 없음). 실패하면 `.mcp.json` 스키마 오류 메시지를 보고 수정.

- [ ] **Step 3: 로컬 스모크 재확인(등록 후 경로로)**

Run:
```bash
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-06-18"}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | CLAUDE_PLUGIN_ROOT="$(pwd)" python3 "$(pwd)/mcp/server.py"
```
Expected: `tools/list` 응답에 `token_saver_check`·`token_saver_autopsy` 둘 다 포함.

- [ ] **Step 4: 커밋**

```bash
git add .mcp.json
git commit -m "Register token-saver MCP server in the plugin manifest, retire the probe entry

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: 전역 Skill (`skills/token-saver-rules/SKILL.md`)

**Files:**
- Create: `skills/token-saver-rules/SKILL.md`

**Interfaces:**
- Consumes: Task 2+3의 툴 이름(`token_saver_check`, `token_saver_autopsy`) — 정확히 일치해야 모델이 올바른 이름으로 호출.

- [ ] **Step 1: Skill 작성**

```markdown
---
name: token-saver-rules
description: 모든 프로젝트에서 토큰 효율(신호 밀도 극대화) 규칙을 적용한다. hooks가 발화하는 CLI/IDE 환경에서는 이미 자동 적용 중이라 사실상 무동작이고, hooks가 없는 Claude Desktop Code 탭 같은 환경에서만 실질적으로 개입한다. 착수형 요청·연결어 과다·방향전환·교정 반복·장황함을 감지하거나, 매 턴 토큰/비용 확인이 필요할 때 사용.
---

# token-saver 규칙 (hooks 미지원 환경 자가 점검)

> `token-saver` 플러그인의 `UserPromptSubmit`/`Stop` hooks는 CLI·IDE 확장에서는 정상 발화해
> 매 턴 `⟢ 턴...` 효율 줄을 시스템 컨텍스트에 자동으로 넣는다. **그 줄이 이미 보이면 hooks가
> 정상 동작 중이라는 뜻이니 이 Skill의 지시를 다시 실행할 필요 없다.**
>
> 그 줄이 안 보이는 환경(대표 사례: Claude Desktop 앱 **Code 탭** — Claude Code를
> stream-json server/API 모드로 구동해 hooks 호출 경로 자체가 없음,
> [desktop/desktop#22138](https://github.com/desktop/desktop/issues/22138) closed as not
> planned, 이 플러그인 코드로 우회 불가한 업스트림 제약)에서는 아래 규칙을 **매 턴 스스로
> 적용**할 것.

## 매 턴 효율 확인
`⟢` 줄이 안 보이면 `token_saver_check` MCP 툴을 호출해 같은 정보를 얻어 한 줄로 보여준다.
툴 자체가 없거나 실패하면(이 환경에 플러그인의 MCP 서버가 연결 안 된 경우) **숫자를 지어내
측정한 것처럼 보고하지 말고** "이 환경에선 실측 불가"라고 명시한다.

## 세션 마무리 시 부검
대화가 끝나가는 신호(사용자의 마무리 인사·"여기까지"·"수고했어" 류)를 감지하면
`token_saver_autopsy` MCP 툴을 호출해 낭비 신호 요약을 한 번, 짧게 보여준다(그 외엔
언급하지 않음 — 매 턴 반복 금지).

## 텍스트 규칙 (MCP 없이도 항상 적용 가능)
- **[연결어 과다]** 사용자 메시지에 "그리고·또한·그런데·근데·그래서·하지만·그렇지만·그래도·
  게다가·혹시" 4개 이상 → 간결화 제안.
- **[착수 전 4슬롯]** 만들/구현/개발/작성/추가/리팩터/고쳐/수정/바꿔/변경/설계/빌드/생성 등
  착수형 요청이 25단어 이하이면서 성공기준·범위 단어가 없으면 → 되묻거나 파싱본 echo 후 진행.
- **[방향전환]** "대신·차라리·방향(을)?바꿔·처음부터 다시·다른 방식/방향으로·그거/그건 말고"
  감지 → 착수 전 방향부터 확정 제안.
- **[교정 반복]** "아니·틀렸·되돌·undo·revert" 같은 교정 마커가 반복되면 → 계획-후-실행으로
  전환 제안.
- **[체감 장황/컨텍스트 비대]** 정확한 수치는 MCP 툴 없이 못 재지만, 같은 내용을 반복
  요약하거나 답이 계속 길어지는 게 스스로 느껴지면 압축·요약 없이 바로 결론부터 제시.
```

- [ ] **Step 2: validate**

Run: `cd "/Volumes/Extreme SSD/worktree/token-saver" && claude plugin validate .`
Expected: 통과, 신규 skill이 컴포넌트 인벤토리에 잡힘(`claude plugin details token-saver`로도 확인 가능).

- [ ] **Step 3: 커밋**

```bash
git add skills/token-saver-rules/SKILL.md
git commit -m "Add global token-saver-rules Skill for hook-free environments

Generalizes CLAUDE.md's repo-local '자가 점검' section (text-only, zero cost)
and adds MCP tool-call instructions for the two things text rules can't fake:
real per-turn numbers and end-of-session waste findings.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: 정리 — probe 폐기 + 문서 갱신

**Files:**
- Delete: `experiments/desktop_mcp_probe/probe_server.py`, `experiments/desktop_mcp_probe/call_count.txt`(있으면)
- Modify: `CLAUDE.md`(Hook 미지원 섹션 축약), `README.md`(알려진 제한사항)

**Interfaces:** 없음(문서·정리 전용, 코드 인터페이스 변경 없음).

- [ ] **Step 1: probe 폐기**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver"
rm -f experiments/desktop_mcp_probe/probe_server.py experiments/desktop_mcp_probe/call_count.txt
rmdir experiments/desktop_mcp_probe 2>/dev/null || true
```

- [ ] **Step 2: `CLAUDE.md`의 "Hook 미지원 환경 자가 점검" 섹션을 다음으로 교체**

(전체 섹션, `## Hook 미지원 환경 자가 점검 (Desktop 등)`부터 마지막 불릿까지를 교체)
```markdown
## Hook 미지원 환경 자가 점검 (Desktop 등)
> 이 섹션은 전역 Skill `token-saver-rules`로 이전됐다(2026-08-05,
> `skills/token-saver-rules/SKILL.md`) — 플러그인을 설치한 모든 프로젝트에 적용되므로
> 이 repo 로컬 사본은 더 유지하지 않는다. hooks 미지원 환경(Desktop Code 탭 등)에서 적용할
> 규칙은 그 Skill 참고. 배경(왜 hooks가 안 도는지, MCP로 뭘 복원했는지)은
> `docs/superpowers/specs/2026-08-05-desktop-active-measurement-design.md` 참고.
```

- [ ] **Step 3: `README.md`의 "알려진 제한사항" 항목 갱신**

기존:
```markdown
- **Claude Desktop 앱에서는 hooks가 실행되지 않습니다**(2026-08-05 실사용 확인 — Desktop 앱은
  Claude Code를 stream-json server/API 모드로 구동해 interactive CLI 모드 전용인 hooks가 발화하지
  않음, [claude-code#63360](https://github.com/anthropics/claude-code/issues/63360) 미해결). 즉
  `habit_coaching.py`·`intent_gate.py`·`session_autopsy.sh`·`--statusline`·`--check` 전부 Desktop에서는
  침묵합니다. `CLAUDE.md`의 서술형 규칙(라우팅·출력통제 등)은 Claude가 프로젝트 컨텍스트를 읽는 한
  여전히 적용되는 것으로 보이나, 능동적 계측·코칭·`production_failures.jsonl` 수집은 CLI/IDE 확장
  (터미널·VS Code·JetBrains — 전부 동일 엔진 사용, hooks 정상 발화)에서만 동작합니다.
```
다음으로 교체:
```markdown
- **Claude Desktop 앱 Code 탭에서는 hooks가 실행되지 않습니다**(desktop/desktop#22138,
  closed as not planned — Anthropic 의도적 미지원, 우회 불가). `habit_coaching.py`·`intent_gate.py`·
  `session_autopsy.sh`·`--statusline`·`--check` 전부 Desktop Code 탭에서는 침묵합니다.
  2026-08-05부터 이 공백을 두 갈래로 best-effort 복원합니다: (1) 텍스트 코칭 규칙은 전역 Skill
  `token-saver-rules`로 이식돼 MCP 없이도 Desktop 포함 모든 환경에 적용됩니다. (2) 실제 트랜스크립트
  계산이 필요한 매 턴 효율 줄·세션 부검·실패 사례 수집은 MCP 서버(`mcp/server.py`,
  `token_saver_check`/`token_saver_autopsy` 툴)로 노출됩니다 — MCP는 hooks와 달리 Desktop Code 탭에서
  실측 연결 확인됨(단, hooks와 달리 모델의 tool_use 호출이라는 실제 비용이 듦, MCP 자체 상시연결이
  안 되는 Cowork에서는 이 경로도 안 통함 — Cowork와 Desktop Code 탭은 다른 제품). 상세:
  `docs/superpowers/specs/2026-08-05-desktop-active-measurement-design.md`,
  실측 결과: `experiments/PROTOCOL.md`.
```

- [ ] **Step 4: 커밋**

```bash
git add -A experiments/desktop_mcp_probe CLAUDE.md README.md
git commit -m "Retire the Desktop MCP probe spike, point docs at the shipped Skill+MCP design

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: 실사용 Desktop 검증 + 실험 기록

**Files:**
- Modify: `experiments/PROTOCOL.md` (신규 실험 항목 추가)
- Modify: `HANDOFF.md` (스레드 종료 기록)

**Interfaces:** 없음(측정·기록 전용). 이 태스크는 자동화 불가 — 사용자가 실제 Desktop Code 탭을 열어야 함.

- [ ] **Step 1: 사용자에게 실사용 세션 요청**

사용자에게 다음을 요청:
1. Desktop 앱 Code 탭에서 이 프로젝트(`/Volumes/Extreme SSD/worktree/token-saver`) 열기.
2. 플러그인이 활성화돼 있는지 확인(`token-saver` MCP 서버·`token-saver-rules` Skill 둘 다 목록에 뜨는지).
3. 여러 턴 대화 진행(최소 5턴 이상, 마무리 인사 포함) — `token_saver_check`가 실제로 매 턴 호출되는지, `⟢` 형식 줄이 사용자에게 보이는지, 마무리 시 `token_saver_autopsy` 호출 여부 관찰.
4. `CLAUDE_PROJECT_DIR` 관련 진단(만약 "못 찾음" 메시지가 나오면 그 안의 `project_dir=` 값 그대로 공유) — Task 2/3에서 미검증으로 남겨둔 항목을 여기서 실측 확정.

- [ ] **Step 2: 결과 분석**

세션 종료 후, 해당 트랜스크립트를 CLI에서 재분석:
```bash
python3 measure.py --autopsy   # latest_session()으로 방금 그 Desktop 세션 자동 탐색
```
확인할 것:
- 실제로 `token_saver_check`/`token_saver_autopsy` tool_use가 트랜스크립트에 기록됐는지(모델이 실제로 호출했는지).
- 호출당 토큰 오버헤드(tool 정의+호출+응답)를 `actor_breakdown()` 또는 수동 집계로 추정.
- `CLAUDE_PROJECT_DIR`가 실제로 설정돼 있었는지, 아니면 `os.getcwd()` 폴백이 쓰였는지(`resolve_project_dir()`의 어느 분기였는지).

- [ ] **Step 3: `experiments/PROTOCOL.md`에 실험 기록**

파일 끝(실험 템플릿 앞)에 새 절 추가:
```markdown
### 실험 11 — Desktop Code 탭 능동 계측 복원 (Skill+MCP)
Desktop Code 탭은 hooks가 원천 불가(desktop/desktop#22138, closed as not planned)지만 MCP는
연결됨(무의존성 stdio 프로브로 실측 확인). `measure.py`의 계산 로직을 path-only 순수 함수로
추출해 CLI(hooks)·MCP(Desktop) 공용화하고, `token_saver_check`/`token_saver_autopsy` 두 툴로
노출. 텍스트 코칭 규칙(4슬롯·연결어 과다 등)은 MCP 없이 전역 Skill로 이식(비용 0).

[실측 결과를 Step 2에서 얻은 실제 수치로 채운다 — MCP 호출당 토큰 오버헤드, 실제 project_dir
해석 경로, 호출 성공/실패 여부. 가정이 아니라 이 세션에서 나온 숫자로.]
```
(이 스텝은 Step 2의 실측값이 있어야 채울 수 있음 — placeholder 대괄호 문구를 실측값으로
바꿔서 커밋할 것.)

- [ ] **Step 4: `HANDOFF.md` 갱신**

"열린 스레드" 관련 섹션 최상단(가장 최근 섹션 뒤)에 추가:
```markdown
## Desktop Code 탭 능동 계측 복원 (2026-08-05, 8차)
hooks가 Desktop Code 탭에서 안 되는 건 업스트림 확정 제약(desktop/desktop#22138, closed as not
planned) — 우회 대신 MCP(살아있음, 실측 확인)로 최대한 복원. 텍스트 규칙은 전역 Skill
`token-saver-rules`로, 실측 필요한 부분(매턴 효율 줄·부검·실패수집)은 `mcp/server.py`
(`token_saver_check`/`token_saver_autopsy`)로. `measure.py`는 CLI/MCP 공용 순수 함수로 리팩터
(`check_line`/`autopsy_text`/`capture_failures_text`/`transcript_dir(project_dir)`). 실측 결과:
`experiments/PROTOCOL.md` 실험11. 설계: `docs/superpowers/specs/2026-08-05-desktop-active-measurement-design.md`.
```

- [ ] **Step 5: 커밋**

```bash
git add experiments/PROTOCOL.md HANDOFF.md
git commit -m "Record Desktop Code-tab MCP active-measurement experiment results

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
