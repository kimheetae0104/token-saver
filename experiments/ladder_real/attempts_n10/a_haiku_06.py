import re
def parse_duration(s: str) -> int:
    units = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
    total = 0
    for match in re.finditer(r'(\d+)([dhms])', s):
        total += int(match.group(1)) * units[match.group(2)]
    return total
