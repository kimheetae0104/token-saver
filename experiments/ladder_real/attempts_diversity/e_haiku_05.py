def apply_defaults(config: dict) -> dict:
    if "timeout_seconds" not in config:
        config["timeout_seconds"] = 30

    if "retry" not in config:
        config["retry"] = {}

    if "backoff_seconds" not in config["retry"]:
        config["retry"]["backoff_seconds"] = 2

    return config
