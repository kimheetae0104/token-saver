"""매 턴 주입 부품 3개(intent_gate·habit_coaching·measure --check)의 끄기 스위치 검증.
부품별 끄기 실험(docs/superpowers/specs/2026-10-12-harness-ablation-design.md)용.
pytest 없음, stdlib assert + PASS/FAIL 러너(레포 컨벤션).
실행: python3 tests/test_ablation_switches.py
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTENT = os.path.join(REPO, "hooks", "intent_gate.py")
HABIT = os.path.join(REPO, "hooks", "habit_coaching.py")
MEASURE = os.path.join(REPO, "measure.py")

# 켜져 있으면 각 부품이 반드시 출력을 내는 입력
INTENT_PROMPT = "그거 고쳐"
HABIT_PROMPT = "그리고 또한 그런데 근데 그래서 이거 봐줘"


def _run(cmd, payload, data_dir, env_extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("TOKEN_SAVER_DISABLE_")}
    env["CLAUDE_PLUGIN_DATA"] = data_dir
    env.update(env_extra or {})
    proc = subprocess.run(cmd, input=json.dumps(payload), capture_output=True, text=True,
                          env=env, timeout=30)
    assert proc.returncode == 0, f"exit {proc.returncode}, stderr={proc.stderr!r}"
    return proc.stdout.strip()


def _write_config(data_dir, cfg):
    with open(os.path.join(data_dir, "config.json"), "w") as f:
        json.dump(cfg, f)


def _flag_state(data_dir, session_id):
    with open(os.path.join(data_dir, "prompt_gate", f"{session_id}.json")) as f:
        return json.load(f)["flagged"]


def test_intent_gate_on_by_default():
    with tempfile.TemporaryDirectory() as d:
        out = _run([sys.executable, INTENT], {"prompt": INTENT_PROMPT, "session_id": "s1"}, d)
        assert out, "켜진 상태에서 출력이 없음 — 테스트 입력이 더는 트리거되지 않음"
        assert _flag_state(d, "s1") is True


def test_intent_gate_config_disabled_silent_and_clears_flag():
    with tempfile.TemporaryDirectory() as d:
        _run([sys.executable, INTENT], {"prompt": INTENT_PROMPT, "session_id": "s1"}, d)
        _write_config(d, {"intent_gate": {"disabled": True}})
        out = _run([sys.executable, INTENT], {"prompt": INTENT_PROMPT, "session_id": "s1"}, d)
        assert out == "", out
        assert _flag_state(d, "s1") is False, "꺼졌는데 이전 턴 flag가 남아 prompt_gate가 막을 수 있음"


def test_intent_gate_env_kill_switch():
    with tempfile.TemporaryDirectory() as d:
        out = _run([sys.executable, INTENT], {"prompt": INTENT_PROMPT, "session_id": "s1"}, d,
                   {"TOKEN_SAVER_DISABLE_INTENT_GATE": "1"})
        assert out == "", out


def test_habit_coaching_on_by_default():
    with tempfile.TemporaryDirectory() as d:
        assert _run([sys.executable, HABIT], {"prompt": HABIT_PROMPT}, d)


def test_habit_coaching_config_disabled():
    with tempfile.TemporaryDirectory() as d:
        _write_config(d, {"habit_coaching": {"disabled": True}})
        assert _run([sys.executable, HABIT], {"prompt": HABIT_PROMPT}, d) == ""


def test_habit_coaching_env_kill_switch():
    with tempfile.TemporaryDirectory() as d:
        out = _run([sys.executable, HABIT], {"prompt": HABIT_PROMPT}, d,
                   {"TOKEN_SAVER_DISABLE_HABIT_COACHING": "1"})
        assert out == "", out


def test_habit_coaching_bad_config_fails_open():
    with tempfile.TemporaryDirectory() as d:
        _write_config(d, {"habit_coaching": "oops"})
        assert _run([sys.executable, HABIT], {"prompt": HABIT_PROMPT}, d)


def test_measure_check_config_disabled():
    with tempfile.TemporaryDirectory() as d:
        _write_config(d, {"measure_check": {"disabled": True}})
        assert _run([sys.executable, MEASURE, "--check"], {}, d) == ""


def test_measure_check_env_kill_switch():
    with tempfile.TemporaryDirectory() as d:
        out = _run([sys.executable, MEASURE, "--check"], {}, d,
                   {"TOKEN_SAVER_DISABLE_MEASURE_CHECK": "1"})
        assert out == "", out


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
