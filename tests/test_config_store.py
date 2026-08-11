#!/usr/bin/env python3
"""config_store.py 유닛 테스트. CLAUDE_PLUGIN_DATA를 매 테스트 격리된 tempdir로 잡아
실제 개발자 머신의 $TMPDIR을 오염시키지 않는다(test_grep_trim.py에서 실제로 겪은
버그와 같은 클래스 — tests/test_grep_trim.py의 _call() 참고)."""
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config_store  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name} {detail}")


def _isolated():
    d = tempfile.TemporaryDirectory()
    os.environ["CLAUDE_PLUGIN_DATA"] = d.name
    return d


def test_effective_returns_defaults_when_no_config_file():
    d = _isolated()
    try:
        cfg = config_store.effective("read_guard")
        check("effective_defaults", cfg == {"disabled": False, "large_file_lines": 500}, cfg)
    finally:
        d.cleanup()


def test_effective_unknown_hook_returns_empty():
    d = _isolated()
    try:
        check("effective_unknown_hook", config_store.effective("nope") == {})
    finally:
        d.cleanup()


def test_set_value_overrides_effective():
    d = _isolated()
    try:
        ok, result = config_store.set_value("read_guard", "large_file_lines", 900)
        check("set_ok", ok is True and result == 900, (ok, result))
        cfg = config_store.effective("read_guard")
        check("set_reflected", cfg["large_file_lines"] == 900, cfg)
        check("set_other_key_untouched", cfg["disabled"] is False, cfg)
    finally:
        d.cleanup()


def test_set_value_coerces_string_int():
    d = _isolated()
    try:
        ok, result = config_store.set_value("bash_trim", "line_threshold", "300")
        check("coerce_int", ok is True and result == 300, (ok, result))
    finally:
        d.cleanup()


def test_set_value_coerces_string_bool():
    d = _isolated()
    try:
        ok, result = config_store.set_value("grep_trim", "disabled", "true")
        check("coerce_bool_true", ok is True and result is True, (ok, result))
        ok2, result2 = config_store.set_value("grep_trim", "disabled", "false")
        check("coerce_bool_false", ok2 is True and result2 is False, (ok2, result2))
    finally:
        d.cleanup()


def test_set_value_rejects_unknown_hook():
    d = _isolated()
    try:
        ok, msg = config_store.set_value("no_such_hook", "disabled", True)
        check("reject_unknown_hook", ok is False and "알 수 없는 hook" in msg, msg)
    finally:
        d.cleanup()


def test_set_value_rejects_unknown_key():
    d = _isolated()
    try:
        ok, msg = config_store.set_value("read_guard", "not_a_key", 1)
        check("reject_unknown_key", ok is False and "없는 설정 키" in msg, msg)
    finally:
        d.cleanup()


def test_set_value_rejects_bad_type():
    d = _isolated()
    try:
        ok, msg = config_store.set_value("read_guard", "large_file_lines", "not-a-number")
        check("reject_bad_int", ok is False, msg)
        ok2, msg2 = config_store.set_value("grep_trim", "disabled", "maybe")
        check("reject_bad_bool", ok2 is False, msg2)
    finally:
        d.cleanup()


def test_prompt_gate_defaults():
    d = _isolated()
    try:
        cfg = config_store.effective("prompt_gate")
        check("prompt_gate_defaults", cfg == {"disabled": False}, cfg)
    finally:
        d.cleanup()


def test_ladder_gate_defaults():
    d = _isolated()
    try:
        cfg = config_store.effective("ladder_gate")
        check("ladder_gate_defaults", cfg == {"disabled": False}, cfg)
    finally:
        d.cleanup()


def test_get_all_covers_all_hooks():
    d = _isolated()
    try:
        all_cfg = config_store.get_all()
        check("get_all_keys",
              set(all_cfg) == {"read_guard", "grep_trim", "bash_trim", "prompt_gate",
                               "ladder_gate", "check_gate"},
              all_cfg)
    finally:
        d.cleanup()


def test_reset_single_hook_restores_default():
    d = _isolated()
    try:
        config_store.set_value("read_guard", "large_file_lines", 999)
        config_store.set_value("grep_trim", "match_threshold", 50)
        config_store.reset("read_guard")
        check("reset_hook_restored", config_store.effective("read_guard")["large_file_lines"] == 500)
        check("reset_hook_other_untouched", config_store.effective("grep_trim")["match_threshold"] == 50)
    finally:
        d.cleanup()


def test_reset_all_restores_everything():
    d = _isolated()
    try:
        config_store.set_value("read_guard", "disabled", True)
        config_store.set_value("bash_trim", "line_threshold", 42)
        config_store.reset(None)
        check("reset_all_read_guard", config_store.effective("read_guard")["disabled"] is False)
        check("reset_all_bash_trim", config_store.effective("bash_trim")["line_threshold"] == 200)
        check("reset_all_no_file", not os.path.isfile(config_store.config_path()))
    finally:
        d.cleanup()


def test_concurrent_set_value_does_not_crash():
    """실측된 버그: _write()가 고정된 '.tmp' 파일명을 써서, 동시 set_value 호출들이
    같은 tmp를 두고 경합하면 뒤 호출의 os.replace가 앞 호출이 이미 옮겨버린 tmp를
    찾다 FileNotFoundError로 죽는다(수정 전 실측: 16개 동시 호출 중 10개 크래시)."""
    d = _isolated()
    try:
        errors = []

        def worker(i):
            try:
                config_store.set_value("read_guard", "large_file_lines", 500 + i)
            except Exception as e:
                errors.append(repr(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        check("concurrent_set_value_no_crash", errors == [], errors)
        # 마지막 승자값 하나가 파일에 정상적으로 반영돼 있어야 한다(파일 자체는 안 깨짐).
        cfg = config_store.effective("read_guard")
        check("concurrent_set_value_file_intact", 500 <= cfg["large_file_lines"] <= 515, cfg)
    finally:
        d.cleanup()


def main():
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"\n{PASS}/{PASS + FAIL} passed")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
