def parse_duration(s: str) -> int:
    import re
    units = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
    total_seconds = 0
    matches = re.findall(r'(\d+)([dhms])', s)
    for value, unit in matches:
        total_seconds += int(value) * units[unit]
    return total_seconds
