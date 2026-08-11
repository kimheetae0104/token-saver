#!/usr/bin/env python3
"""token-saver 설정 저장소 — read_guard·grep_trim·bash_trim의 임계값·kill switch를
DIY로 조회·변경할 수 있게 하는 오버레이 레이어.

우선순위: env var kill switch(TOKEN_SAVER_DISABLE_*, 기존 동작) > 이 config.json
오버라이드 > 하드코딩 기본값. env var가 항상 최우선인 이유 — 운영 중 문제 생기면
즉시 끌 수 있는 기존 수단을 이 기능이 절대 약화시키면 안 된다.

Windows Desktop Code 탭은 hooks가 안 뜨므로(desktop/desktop#22138, Windows 11 한정
재현 — macOS Desktop Code 탭은 hooks 정상 발화, experiments/PROTOCOL.md 실험11로
정정) MCP token_saver_config_set이 유일한 조회/변경 경로 — CLI/IDE·macOS Desktop에선
훅들이 같은 config.json을 직접 읽어 반영한다.

DEFAULTS는 각 hook 파일의 실제 하드코딩 상수와 반드시 일치해야 한다(단일 진실
소스는 이쪽이 아니라 각 hook 파일 — 훅은 여전히 self-contained 유지, 이 모듈을
import하지 않고 자체 load_config()로 직접 config.json을 읽는다. 이 모듈은
MCP 서버의 조회/검증/변경 전용). stdlib만 사용, LLM 호출 없음.
"""
import json
import os
import tempfile

DEFAULTS = {
    "read_guard": {"disabled": False, "large_file_lines": 500},
    "grep_trim": {"disabled": False, "match_threshold": 100, "keep_head": 30, "keep_tail": 10},
    "bash_trim": {"disabled": False, "line_threshold": 200, "keep_head": 40, "keep_tail": 20},
    "prompt_gate": {"disabled": False},
    "ladder_gate": {"disabled": False},
    "check_gate": {"disabled": False},
}
_TYPES = {
    "disabled": bool,
    "large_file_lines": int, "match_threshold": int, "keep_head": int, "keep_tail": int,
    "line_threshold": int,
}


def config_path():
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    return os.path.join(data_dir, "config.json") if data_dir else os.path.join(
        tempfile.gettempdir(), "token-saver-config.json")


def load_raw():
    try:
        with open(config_path(), "r") as f:
            return json.load(f)
    except Exception:
        return {}


def effective(hook_name):
    """기본값 위에 config.json 오버라이드를 얹은 딕셔너리. 알 수 없는 hook_name -> {}."""
    defaults = DEFAULTS.get(hook_name)
    if defaults is None:
        return {}
    merged = dict(defaults)
    merged.update(load_raw().get(hook_name, {}))
    return merged


def get_all():
    return {name: effective(name) for name in DEFAULTS}


def _coerce(key, value):
    t = _TYPES[key]
    if t is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ("true", "1", "yes", "on"):
                return True
            if value.lower() in ("false", "0", "no", "off"):
                return False
        raise ValueError(f"{key}는 true/false 값이어야 합니다: {value!r}")
    if t is int:
        try:
            return int(value)
        except Exception:
            raise ValueError(f"{key}는 정수여야 합니다: {value!r}")
    raise ValueError(f"알 수 없는 설정 키: {key}")


def set_value(hook_name, key, value):
    """검증 후 config.json에 반영. 성공 시 (True, 적용된 값), 실패 시 (False, 오류 메시지).
    알 수 없는 hook/key는 명시적으로 거부(오타로 조용히 무시되는 설정 없게)."""
    if hook_name not in DEFAULTS:
        return False, f"알 수 없는 hook: {hook_name!r} (가능: {', '.join(DEFAULTS)})"
    if key not in DEFAULTS[hook_name]:
        return False, f"{hook_name}에 없는 설정 키: {key!r} (가능: {', '.join(DEFAULTS[hook_name])})"
    try:
        coerced = _coerce(key, value)
    except ValueError as e:
        return False, str(e)
    raw = load_raw()
    raw.setdefault(hook_name, {})[key] = coerced
    _write(raw)
    return True, coerced


def reset(hook_name=None):
    """hook_name 지정 시 그 hook 설정만 기본값으로, 없으면 config.json 전체를 삭제."""
    raw = load_raw()
    if hook_name is None:
        raw = {}
    else:
        raw.pop(hook_name, None)
    if not raw:
        try:
            os.remove(config_path())
        except FileNotFoundError:
            pass
        return
    _write(raw)


def _write(raw):
    """고정된 '.tmp' 이름을 여러 호출이 동시에 열면, 뒤 호출이 앞 호출의 os.replace로
    이미 사라진 tmp 파일을 다시 replace하려다 FileNotFoundError로 죽는다(실측: 16개
    동시 set_value 중 10개 크래시). 호출마다 고유한 임시파일(mkstemp)로 그 레이스를
    없앤다. (참고: 동시 set_value의 read-modify-write 순서 자체는 여전히 last-writer-wins
    — 이 함수는 크래시만 없앨 뿐 그 경합까지 직렬화하진 않는다. 저빈도 설정 변경
    유스케이스에선 감내 가능한 수준으로 판단, out of scope.)"""
    path = config_path()
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
