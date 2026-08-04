import re
def parse_duration(s: str) -> int:
    units = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
    total = 0
    for value, unit in re.findall(r'(\d+)([dhms])', s):
        total += int(value) * units[unit]
    return total
