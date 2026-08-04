def apply_defaults(config: dict) -> dict:
    from copy import deepcopy
    result = deepcopy(config)
    if 'timeout_seconds' not in result:
        result['timeout_seconds'] = 30
    if 'retry' not in result:
        result['retry'] = {}
    if 'backoff_seconds' not in result['retry']:
        result['retry']['backoff_seconds'] = 2
    return result
