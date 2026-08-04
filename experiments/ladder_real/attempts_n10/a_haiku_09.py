import re
def parse_duration(s: str) -> int:
    units = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
    total_seconds = 0
    for match in re.finditer(r'(\d+)([dhms])', s):
        value, unit = int(match.group(1)), match.group(2)
        total_seconds += value * units[unit]
    return total_seconds
