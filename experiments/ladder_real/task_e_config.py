"""Task E oracle — 설정 편집. apply_defaults(config)가 누락된 필수 필드만 기본값으로
채우고 기존 값은 절대 덮어쓰지 않아야 함. jsonschema로 최종 형태 검증.
"""
import jsonschema

BASE_CONFIG = {
    "service_name": "billing-worker",
    "retry": {"max_attempts": 5},
}

SCHEMA = {
    "type": "object",
    "properties": {
        "service_name": {"type": "string", "minLength": 1},
        "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
        "retry": {
            "type": "object",
            "properties": {
                "max_attempts": {"type": "integer", "minimum": 1},
                "backoff_seconds": {"type": "number", "exclusiveMinimum": 0},
            },
            "required": ["max_attempts", "backoff_seconds"],
            "additionalProperties": False,
        },
    },
    "required": ["service_name", "timeout_seconds", "retry"],
    "additionalProperties": False,
}

DEFAULTS = {
    "timeout_seconds": 30,
    "retry": {"backoff_seconds": 2},
}


def check(candidate_output):
    try:
        jsonschema.validate(candidate_output, SCHEMA)
    except jsonschema.ValidationError as e:
        return False, [f"schema violation: {e.message}"]
    issues = []
    if candidate_output.get("service_name") != "billing-worker":
        issues.append("service_name 기존값이 바뀜(덮어쓰기 금지 위반)")
    if candidate_output.get("retry", {}).get("max_attempts") != 5:
        issues.append("retry.max_attempts 기존값이 바뀜(덮어쓰기 금지 위반)")
    if candidate_output.get("timeout_seconds") != 30:
        issues.append(f"timeout_seconds 기본값 30 기대, {candidate_output.get('timeout_seconds')!r}")
    if candidate_output.get("retry", {}).get("backoff_seconds") != 2:
        issues.append(f"retry.backoff_seconds 기본값 2 기대, {candidate_output.get('retry', {}).get('backoff_seconds')!r}")
    return len(issues) == 0, issues


if __name__ == "__main__":
    import copy

    def reference(config: dict) -> dict:
        out = copy.deepcopy(config)
        for key, val in DEFAULTS.items():
            if isinstance(val, dict):
                out.setdefault(key, {})
                for sub_key, sub_val in val.items():
                    out[key].setdefault(sub_key, sub_val)
            else:
                out.setdefault(key, val)
        return out

    ok, issues = check(reference(BASE_CONFIG))
    print("OK" if ok else issues)
