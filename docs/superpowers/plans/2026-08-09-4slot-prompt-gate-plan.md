# 4슬롯 강제 게이트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모호하다고 판단된 턴의 첫 도구 호출을 실제로 1회 막아, Claude가 4슬롯(의도·제약·성공기준·위임경계) 파싱을 말하고 나서야 작업을 시작하게 만든다.

**Architecture:** `hooks/intent_gate.py`(UserPromptSubmit, 기존 파일)가 매 턴 세션별 상태파일에 `{"flagged": bool, "tripped": false}`를 쓴다. 신규 `hooks/prompt_gate.py`(PreToolUse, matcher 없음 = 전체 도구)가 그 상태를 읽어 `flagged: true`이고 `tripped: false`인 턴의 첫 도구 호출만 deny하고 즉시 `tripped: true`로 갱신, 이후 호출은 통과시킨다. transcript 파싱 없음(핵심 제약: PreToolUse는 Claude가 그 턴에 이미 낸 텍스트를 payload로 못 받음).

**Tech Stack:** Python 3(stdlib만), Claude Code PreToolUse/UserPromptSubmit hooks, 기존 `config_store.py` DIY 설정 레이어.

## Global Constraints
- LLM 호출 없음, 전부 결정론 (CLAUDE.md AI-YAGNI).
- 모든 훅은 fail-open: session_id 없음·상태파일 손상·예외 발생 시 무조건 허용(도구 호출을 절대 깨뜨리지 않음).
- 킬스위치 우선순위: env var(`TOKEN_SAVER_DISABLE_*`) > `config.json` 오버라이드 > 하드코딩 기본값(기존 3개 hook과 동일 컨벤션).
- stdlib만 사용, 외부 의존성 추가 금지.
- 테스트는 pytest 없이 stdlib assert + PASS/FAIL 러너(레포 기존 컨벤션 그대로, `tests/test_*.py` 각 파일 하단 `main()` 패턴).
- `prompt_gate.py`는 텍스트 내용을 검증하지 않는다 — 상태값(`flagged`/`tripped`)만 본다(설계 스펙에서 확정된 결정, 재논의 대상 아님).
- 배포는 코드 완료로 끝나지 않는다: `plugin.json` 버전 범프 → `git push` → `claude plugin marketplace update token-saver-tools` → `claude plugin update token-saver@token-saver-tools` → 캐시 디렉터리에서 신규 파일 실존 확인까지 마쳐야 "완료"(13차 교훈, HANDOFF.md 참고).
- `git push`는 실행 전 사용자에게 명시적으로 확인받는다(글로벌 CLAUDE.md "Boundary: local-only" — 이 프로젝트의 로컬 규칙보다 우선하는 상위 규칙).
- 참고 spec: `docs/superpowers/specs/2026-08-09-4slot-prompt-gate-design.md`.

---

### Task 1: `prompt_gate`를 설정 저장소·MCP 스키마에 등록

**Files:**
- Modify: `config_store.py`
- Modify: `mcp/server.py:133-163`
- Modify: `tests/test_config_store.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: 없음(이 태스크가 최초).
- Produces: `config_store.DEFAULTS["prompt_gate"] == {"disabled": False}` — Task 2·3에서 `hooks/prompt_gate.py`·`hooks/intent_gate.py`가 각자 자체 `load_config()`로 이 값과 동일한 스키마(`{"disabled": bool}`)를 `config.json`의 `"prompt_gate"` 키에서 읽는다(단, 훅 자체는 이 모듈을 import하지 않음 — self-contained 컨벤션 유지, 이 태스크는 MCP 조회/검증/변경 전용 등록만).

- [ ] **Step 1: 실패하는 테스트 작성 — `config_store.effective("prompt_gate")`**

`tests/test_config_store.py`의 `test_get_all_covers_all_hooks` 바로 위에 추가:

```python
def test_prompt_gate_defaults():
    d = _isolated()
    try:
        cfg = config_store.effective("prompt_gate")
        check("prompt_gate_defaults", cfg == {"disabled": False}, cfg)
    finally:
        d.cleanup()
```

같은 파일의 `test_get_all_covers_all_hooks` 안 기존 줄을 이렇게 바꾼다:

```python
        check("get_all_keys",
              set(all_cfg) == {"read_guard", "grep_trim", "bash_trim", "prompt_gate"}, all_cfg)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_config_store.py`
Expected: `FAIL prompt_gate_defaults ...`(아직 `DEFAULTS`에 `prompt_gate` 없음) + `FAIL get_all_keys ...`

- [ ] **Step 3: `config_store.py`에 `prompt_gate` 등록**

`config_store.py`의 `DEFAULTS` 딕셔너리를 다음으로 교체:

```python
DEFAULTS = {
    "read_guard": {"disabled": False, "large_file_lines": 500},
    "grep_trim": {"disabled": False, "match_threshold": 100, "keep_head": 30, "keep_tail": 10},
    "bash_trim": {"disabled": False, "line_threshold": 200, "keep_head": 40, "keep_tail": 20},
    "prompt_gate": {"disabled": False},
}
```

`_TYPES`는 수정 불필요 — `"disabled": bool` 매핑이 이미 있음.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_config_store.py`
Expected: 마지막 줄이 이전 통과 개수 + 1 (예: 이전 18/18이었다면 19/19)

- [ ] **Step 5: MCP 서버 스키마·설명에 `prompt_gate` 반영 — 실패하는 테스트 먼저**

`tests/test_mcp_server.py`의 `test_config_reset_restores_default` 아래에 추가:

```python
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
```

- [ ] **Step 6: 테스트 실패 확인**

Run: `python3 tests/test_mcp_server.py`
Expected: `test_config_get_includes_prompt_gate` FAIL(`prompt_gate` 텍스트 없음) — `test_config_set_accepts_prompt_gate_hook`도 FAIL 가능(스키마 `enum`에 없어 클라이언트단 검증은 우회되지만 `set_value` 자체는 `DEFAULTS`에 이미 있어 성공할 수도 있음, 어느 쪽이든 다음 스텝 진행).

- [ ] **Step 7: `mcp/server.py` 수정**

`mcp/server.py:133-163`의 `token_saver_config_set`·`token_saver_config_reset` 항목을 다음으로 교체(설명 문구와 `enum` 배열 둘 다 변경):

```python
    "token_saver_config_set": {
        "description": (
            "read_guard·grep_trim·bash_trim·prompt_gate 중 하나의 임계값 또는 kill switch를 "
            "DIY로 변경한다. hook: 'read_guard'|'grep_trim'|'bash_trim'|'prompt_gate'. key: "
            "read_guard는 'disabled'|'large_file_lines', grep_trim은 'disabled'|"
            "'match_threshold'|'keep_head'|'keep_tail', bash_trim은 'disabled'|"
            "'line_threshold'|'keep_head'|'keep_tail', prompt_gate는 'disabled'만. value: "
            "숫자 또는 true/false. 변경 즉시 config.json에 저장되고 해당 hook의 다음 "
            "실행부터 반영된다(현재 실행 중인 호출엔 소급 적용 안 됨)."
        ),
        "handler": tool_config_set,
        "input_schema": {
            "type": "object",
            "properties": {
                "hook": {"type": "string",
                          "enum": ["read_guard", "grep_trim", "bash_trim", "prompt_gate"]},
                "key": {"type": "string"},
                "value": {},
            },
            "required": ["hook", "key", "value"],
        },
    },
    "token_saver_config_reset": {
        "description": (
            "token_saver_config_set으로 바꾼 값을 기본값으로 되돌린다. hook을 지정하면 "
            "그 hook만, 생략하면 전체(read_guard·grep_trim·bash_trim·prompt_gate 모두)를 "
            "초기화한다."
        ),
        "handler": tool_config_reset,
        "input_schema": {
            "type": "object",
            "properties": {"hook": {"type": "string",
                                     "enum": ["read_guard", "grep_trim", "bash_trim", "prompt_gate"]}},
        },
    },
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `python3 tests/test_mcp_server.py`
Expected: 전부 PASS.

- [ ] **Step 9: 커밋**

```bash
git add config_store.py mcp/server.py tests/test_config_store.py tests/test_mcp_server.py
git commit -m "feat(config): prompt_gate를 설정 저장소·MCP 스키마에 등록"
```

---

### Task 2: `hooks/prompt_gate.py` — 1회성 트립 게이트 본체

**Files:**
- Create: `hooks/prompt_gate.py`
- Test: `tests/test_prompt_gate.py`

**Interfaces:**
- Consumes: `config_store.DEFAULTS["prompt_gate"]`(Task 1)와 동일 스키마의 `config.json`(직접 import 안 함, 자체 `load_config()`로 읽음). 상태파일 스키마 `{"flagged": bool, "tripped": bool}` — Task 3에서 `hooks/intent_gate.py`가 쓰는 것과 같은 파일·같은 스키마를 읽는다.
- Produces: `state_dir()`, `state_path(session_id)` — 두 함수 이름과 경로 규칙(`${CLAUDE_PLUGIN_DATA}/prompt_gate/<session_id>.json`, 폴백 `tempdir()/token-saver-prompt-gate/<session_id>.json`)을 Task 3이 **그대로 복제**해서 쓴다(self-contained 컨벤션 — import 아님, 코드 중복이지만 경로 문자열은 반드시 일치해야 함).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_prompt_gate.py` 새로 작성(전체 파일):

```python
#!/usr/bin/env python3
"""hooks/prompt_gate.py 검증 — PreToolUse 1회성 트립 게이트. pytest 없음, stdlib assert +
PASS/FAIL 러너(레포 컨벤션). 실행: python3 tests/test_prompt_gate.py
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "prompt_gate.py")


def _call(session_id="sess-1", tool_name="Bash", data_dir=None, disable=False):
    payload = {"session_id": session_id, "hook_event_name": "PreToolUse",
               "tool_name": tool_name, "tool_input": {}}
    env = dict(os.environ)
    if data_dir:
        env["CLAUDE_PLUGIN_DATA"] = data_dir
    if disable:
        env["TOKEN_SAVER_DISABLE_PROMPT_GATE"] = "1"
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    out = proc.stdout.strip()
    if not out:
        return None  # 허용
    return json.loads(out)


def _write_state(data_dir, session_id, state):
    d = os.path.join(data_dir, "prompt_gate")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{session_id}.json"), "w") as f:
        json.dump(state, f)


def _write_config(data_dir, cfg):
    with open(os.path.join(data_dir, "config.json"), "w") as f:
        json.dump({"prompt_gate": cfg}, f)


def test_no_state_file_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        resp = _call(data_dir=data_dir)
        assert resp is None


def test_not_flagged_allows():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": False, "tripped": False})
        resp = _call(data_dir=data_dir)
        assert resp is None


def test_flagged_untripped_denies_and_trips():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is not None
        assert resp["hookSpecificOutput"]["permissionDecision"] == "deny"
        with open(os.path.join(data_dir, "prompt_gate", "sess-1.json")) as f:
            state = json.load(f)
        assert state["tripped"] is True, state


def test_flagged_and_tripped_allows_retry():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": True})
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is None


def test_corrupt_state_file_fails_open():
    with tempfile.TemporaryDirectory() as data_dir:
        d = os.path.join(data_dir, "prompt_gate")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sess-1.json"), "w") as f:
            f.write("not json{{{")
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is None


def test_missing_session_id_allows():
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {}}
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=dict(os.environ), timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_malformed_stdin_fails_open():
    proc = subprocess.run([sys.executable, HOOK], input="not json{{{",
                          capture_output=True, text=True, env=dict(os.environ), timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_kill_switch_disables():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        resp = _call(session_id="sess-1", data_dir=data_dir, disable=True)
        assert resp is None


def test_config_disabled_skips_gate():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        _write_config(data_dir, {"disabled": True})
        resp = _call(session_id="sess-1", data_dir=data_dir)
        assert resp is None


def test_env_kill_switch_wins_over_config_enabled():
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        _write_config(data_dir, {"disabled": False})
        resp = _call(session_id="sess-1", data_dir=data_dir, disable=True)
        assert resp is None


def test_applies_regardless_of_tool_name():
    """matcher 없이 전체 도구에 적용되는 설계 확인 — Bash 아닌 다른 도구명으로도 차단."""
    with tempfile.TemporaryDirectory() as data_dir:
        _write_state(data_dir, "sess-1", {"flagged": True, "tripped": False})
        resp = _call(session_id="sess-1", tool_name="Write", data_dir=data_dir)
        assert resp is not None


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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_prompt_gate.py`
Expected: `ERROR ... No such file or directory` 류(`hooks/prompt_gate.py`가 아직 없음)

- [ ] **Step 3: `hooks/prompt_gate.py` 작성(전체 파일)**

```python
#!/usr/bin/env python3
"""PreToolUse hook(matcher 없음 — 전체 도구. 선례: 공식 hookify 플러그인
~/.claude/plugins/marketplaces/claude-plugins-official/plugins/hookify/hooks/hooks.json이
동일하게 matcher 생략으로 전체 도구에 적용됨, 2026-08-09 실측 확인) — 모호한 요청으로
판단된 턴의 첫 도구 호출을 1회만 막아 Claude가 뭔가 말하고 나서 시작하게 유도한다
("1회성 트립 게이트", docs/superpowers/specs/2026-08-09-4slot-prompt-gate-design.md).

hooks/intent_gate.py(UserPromptSubmit)가 매 턴 상태파일에 {"flagged": bool, "tripped":
false}를 쓴다. 이 훅은 그 상태만 읽는다 — transcript_path는 쓰지 않는다(PreToolUse는 이
턴에 Claude가 이미 낸 텍스트를 payload로 못 받고, hooks/read_guard.py도 같은 이유로 자체
상태파일만 쓴다 — 그 선례를 그대로 재사용). 내용 검증은 하지 않는다(존재 여부조차 확인
불가) — deny 사유를 본 Claude가 자연스럽게 설명하며 재시도하는 구조로 같은 효과를 유도한다.

LLM 호출 없음, 결정론. stdlib만 사용.
킬스위치: TOKEN_SAVER_DISABLE_PROMPT_GATE=1 이면 무조건 허용.
fail-open: session_id 없음, 상태파일 없음/손상, 어떤 예외든 조용히 허용 — 도구 호출을
절대 깨뜨리지 않는다.
DIY 설정: config.json(config_store.py)의 prompt_gate.disabled로도 끌 수 있음. env
킬스위치가 항상 config보다 우선.
"""
import json
import os
import sys
import tempfile


def state_dir():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    d = os.path.join(data_dir, "prompt_gate") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-prompt-gate")
    os.makedirs(d, exist_ok=True)
    return d


def state_path(session_id):
    return os.path.join(state_dir(), f"{session_id}.json")


def config_path():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    return os.path.join(data_dir, "config.json") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-config.json")


def load_config():
    try:
        with open(config_path(), "r") as f:
            return json.load(f).get("prompt_gate", {})
    except Exception:
        return {}


def load_state(session_id):
    try:
        with open(state_path(session_id), "r") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else None
    except Exception:
        return None


def write_state(session_id, state):
    try:
        path = state_path(session_id)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except Exception:
        pass


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
    if os.environ.get("TOKEN_SAVER_DISABLE_PROMPT_GATE") == "1" or cfg.get("disabled"):
        return allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return allow()

    session_id = payload.get("session_id")
    if not session_id:
        return allow()

    state = load_state(session_id)
    if not state or not state.get("flagged"):
        return allow()
    if state.get("tripped"):
        return allow()

    write_state(session_id, {"flagged": True, "tripped": True})
    return deny(
        "모호한 요청으로 판단됨 — 먼저 의도·제약·성공기준·위임경계 파싱본을 텍스트로 "
        "밝히고 나서 다시 시도하세요."
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_prompt_gate.py`
Expected: `11/11 passed`

- [ ] **Step 5: 커밋**

```bash
git add hooks/prompt_gate.py tests/test_prompt_gate.py
git commit -m "feat(hooks): prompt_gate.py — 1회성 트립 게이트 본체"
```

---

### Task 3: `hooks/intent_gate.py`가 상태파일을 쓰도록 확장

**Files:**
- Modify: `hooks/intent_gate.py`
- Modify: `tests/test_intent_gate.py`

**Interfaces:**
- Consumes: Task 2의 `state_path(session_id)` 경로 규칙을 **복제**(import 아님 — self-contained 컨벤션). 정확히 `${CLAUDE_PLUGIN_DATA}/prompt_gate/<session_id>.json`(폴백: `tempdir()/token-saver-prompt-gate/<session_id>.json`), 내용은 `{"flagged": bool, "tripped": false}`.
- Produces: 매 UserPromptSubmit 호출마다 이 상태파일을 덮어씀(append 아님) — Task 2의 `prompt_gate.py`가 다음 PreToolUse에서 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_intent_gate.py` 맨 위 import 블록을 다음으로 교체:

```python
import json
import os
import subprocess
import sys
import tempfile
```

파일 맨 아래 `def main():` 바로 위에 추가:

```python
def _call_with_session(prompt, session_id="sess-1", data_dir=None):
    payload = {"prompt": prompt, "session_id": session_id}
    env = dict(os.environ)
    if data_dir:
        env["CLAUDE_PLUGIN_DATA"] = data_dir
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, f"hook exited {proc.returncode}, stderr={proc.stderr!r}"
    return proc.stdout.strip()


def _read_state(data_dir, session_id):
    path = os.path.join(data_dir, "prompt_gate", f"{session_id}.json")
    with open(path) as f:
        return json.load(f)


def test_vague_prompt_writes_flagged_state():
    with tempfile.TemporaryDirectory() as data_dir:
        _call_with_session("더 강화시켜", data_dir=data_dir)
        state = _read_state(data_dir, "sess-1")
        assert state == {"flagged": True, "tripped": False}, state


def test_clear_prompt_writes_unflagged_state():
    with tempfile.TemporaryDirectory() as data_dir:
        _call_with_session(
            "measure.py의 check_line 함수만 수정해줘, 기존 포맷 절대 깨지 말고, "
            "테스트 통과하면 완료로 간주", data_dir=data_dir)
        state = _read_state(data_dir, "sess-1")
        assert state == {"flagged": False, "tripped": False}, state


def test_state_overwritten_each_turn():
    """이전 턴이 flagged=True였어도, 다음 턴이 명확하면 flagged=False로 덮어써야
    한다(과거 턴 상태가 새 턴에 새면 안 됨)."""
    with tempfile.TemporaryDirectory() as data_dir:
        _call_with_session("더 강화시켜", data_dir=data_dir)
        assert _read_state(data_dir, "sess-1")["flagged"] is True
        _call_with_session(
            "measure.py의 check_line 함수만 수정해줘, 기존 포맷 절대 깨지 말고, "
            "테스트 통과하면 완료로 간주", data_dir=data_dir)
        assert _read_state(data_dir, "sess-1")["flagged"] is False


def test_no_session_id_does_not_crash():
    out = _call("더 강화시켜")  # 기존 _call(), session_id 없음
    assert "의도" in out, out  # stdout 동작은 그대로 — 상태 쓰기만 스킵(fail-open)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_intent_gate.py`
Expected: `test_vague_prompt_writes_flagged_state`·`test_clear_prompt_writes_unflagged_state`·
`test_state_overwritten_each_turn`가 `FileNotFoundError`로 ERROR(상태파일이 아직 안 만들어짐).
`test_no_session_id_does_not_crash`는 이미 PASS(기존 동작 그대로라 무회귀).

- [ ] **Step 3: `hooks/intent_gate.py` 수정**

`import` 블록을 다음으로 교체:

```python
import json
import os
import re
import sys
import tempfile
```

`WORD_COUNT_MAX`/`SHORT_INTENT_MAX` 정의 블록 뒤, `def main():` 앞에 추가:

```python
def state_dir():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    d = os.path.join(data_dir, "prompt_gate") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-prompt-gate")
    os.makedirs(d, exist_ok=True)
    return d


def state_path(session_id):
    return os.path.join(state_dir(), f"{session_id}.json")


def write_flag_state(session_id, flagged):
    """hooks/prompt_gate.py(PreToolUse)가 읽는 상태파일 — 매 턴 덮어써서 이전 턴 상태가
    새 턴에 새지 않게 한다. session_id 없으면 아무것도 안 씀(fail-open)."""
    if not session_id:
        return
    try:
        path = state_path(session_id)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"flagged": flagged, "tripped": False}, f)
        os.replace(tmp, path)
    except Exception:
        pass
```

`main()` 전체를 다음으로 교체:

```python
def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    session_id = payload.get("session_id")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        write_flag_state(session_id, False)
        return
    prompt = prompt.strip()
    if not prompt:
        write_flag_state(session_id, False)
        return

    words = re.findall(r"\S+", prompt)
    if len(words) > WORD_COUNT_MAX:
        write_flag_state(session_id, False)
        return

    has_action = re.search(ACTION_WORDS, prompt) is not None
    if not has_action:
        write_flag_state(session_id, False)
        return

    has_constraint = re.search(CONSTRAINT_WORDS, prompt) is not None
    has_success = re.search(SUCCESS_WORDS, prompt) is not None
    is_broad = re.search(BROAD_WORDS, prompt) is not None
    has_delegation = re.search(DELEGATION_WORDS, prompt) is not None

    missing = []
    if len(words) <= SHORT_INTENT_MAX:
        missing.append("의도(무엇을 대상으로)")
    if not has_constraint:
        missing.append("제약(하지 말아야 할 것·범위)")
    if not has_success:
        missing.append("성공기준(뭐가 되면 끝)")
    if is_broad and not has_delegation:
        missing.append("위임경계(직접 할지 위임할지)")

    write_flag_state(session_id, bool(missing))
    if not missing:
        return

    print(f"💡 착수 전 확인: {', '.join(missing)}이 불명확하면 되묻고, 명확하면 파싱본 echo 후 진행 권장.")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_intent_gate.py`
Expected: 전부 PASS(이전 8/8 + 신규 4개 = 12/12).

- [ ] **Step 5: 커밋**

```bash
git add hooks/intent_gate.py tests/test_intent_gate.py
git commit -m "feat(hooks): intent_gate.py가 prompt_gate 상태파일을 매 턴 기록하도록 확장"
```

---

### Task 4: `hooks/hooks.json` 배선 + 회귀 전수 확인

**Files:**
- Modify: `hooks/hooks.json`

**Interfaces:**
- Consumes: `hooks/prompt_gate.py`(Task 2)의 파일 경로.
- Produces: 없음(배선 전용, 이후 태스크 없음).

- [ ] **Step 1: `hooks/hooks.json`의 `PreToolUse` 배열 수정**

기존:
```json
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/read_guard.py\"" }
        ]
      }
    ],
```

다음으로 교체(matcher 없는 항목 추가 — 공식 hookify 플러그인과 동일한 문법으로 전체 도구에 적용됨, 2026-08-09 `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/hookify/hooks/hooks.json` 확인):

```json
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/read_guard.py\"" }
        ]
      },
      {
        "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/prompt_gate.py\"" }
        ]
      }
    ],
```

- [ ] **Step 2: JSON 유효성 확인**

Run: `python3 -c "import json; json.load(open('hooks/hooks.json'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: 전체 테스트 스위트 회귀 확인**

Run:
```bash
for f in tests/test_*.py; do python3 "$f" || echo "FAILED: $f"; done
```
Expected: 모든 파일이 `N/N passed`로 끝나고 `FAILED:` 줄이 하나도 안 나옴.

- [ ] **Step 4: 커밋**

```bash
git add hooks/hooks.json
git commit -m "feat(hooks): prompt_gate.py를 PreToolUse(전체 도구)에 배선"
```

---

### Task 5: 배포 — 버전 범프·푸시·마켓플레이스 반영 확인

**Files:**
- Modify: `.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: Task 1~4에서 커밋된 모든 변경.
- Produces: 없음(최종 태스크).

- [ ] **Step 1: 버전 범프**

`.claude-plugin/plugin.json`의 `"version"`을 현재 값(구현 시점에 `cat .claude-plugin/plugin.json`으로 실제 값 확인 후) 다음 patch 버전으로 올리고, `"description"`에 "PreToolUse gate forcing a 4-slot echo on ambiguous turns" 류 문구를 자연스럽게 추가.

- [ ] **Step 2: 커밋**

```bash
git add .claude-plugin/plugin.json
git commit -m "chore(plugin): 버전 범프 — 4슬롯 강제 게이트 반영"
```

- [ ] **Step 3: 사용자에게 푸시 확인**

이 태스크를 실행하는 주체(서브에이전트 또는 이 세션)는 **여기서 반드시 멈추고** 사용자에게
"Task 1~5 커밋 완료, N/N 테스트 통과. 푸시할까요?"를 확인한다. 자동으로 `git push` 하지
않는다(글로벌 CLAUDE.md "Boundary: local-only").

- [ ] **Step 4: 승인 후 푸시·마켓플레이스 반영**

사용자 승인 후:
```bash
git push origin main
claude plugin marketplace update token-saver-tools
claude plugin update token-saver@token-saver-tools
```

- [ ] **Step 5: 캐시 반영 실측 확인**

Run: `ls ~/.claude/plugins/cache/token-saver-tools/token-saver/<새 버전>/hooks/ | grep prompt_gate`
Expected: `prompt_gate.py` 출력됨. 안 나오면 배포 체인이 끊긴 것 — 13차 사례(버전 미범프로
마켓플레이스가 새 커밋을 못 봄)를 다시 확인.

- [ ] **Step 6: 사용자에게 재시작 필요 안내**

"플러그인 N.N.N 반영 확인. 재시작해야 이번 세션에 적용됩니다."라고 알린다.

---

## 완료 기준
- 5개 태스크 전부 커밋 완료.
- `for f in tests/test_*.py; do python3 "$f"; done` 전 파일 `N/N passed`, 실패 0.
- `claude plugin update token-saver@token-saver-tools` 결과가 새 버전으로 실제 갱신됨 +
  캐시 디렉터리에 `prompt_gate.py` 실존 확인.
- **50% 절감 목표는 이 플랜의 완료 기준이 아니다** — 원 spec에 명시했듯 가설이며 종단
  실측(`measure.py --all`)이 필요, 단일 기능 하나로 검증할 수 없음.
