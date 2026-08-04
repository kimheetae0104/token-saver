"""Task A oracle — code+test. 후보 parse_duration(s)->int 를 이 스위트로 채점."""
import re

CASES = [
    ("45s", 45),
    ("1h30m", 5400),
    ("2d3h", 183600),
    ("1d", 86400),
    ("90m", 5400),
    ("1h1m1s", 3661),
    ("0s", 0),
    ("3d12h30m15s", 302 * 3600 + 15 + 12 * 3600 - 12 * 3600),  # placeholder overwritten below
]
CASES[-1] = ("3d12h30m15s", 3 * 86400 + 12 * 3600 + 30 * 60 + 15)


def run(candidate_fn):
    failures = []
    for s, expected in CASES:
        try:
            got = candidate_fn(s)
        except Exception as e:
            failures.append(f"{s!r}: raised {e!r}")
            continue
        if got != expected:
            failures.append(f"{s!r}: expected {expected}, got {got!r}")
    return len(failures) == 0, failures


if __name__ == "__main__":
    def reference(s: str) -> int:
        total = 0
        for num, unit in re.findall(r"(\d+)([dhms])", s):
            n = int(num)
            total += n * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
        return total
    ok, fails = run(reference)
    print("reference OK" if ok else fails)
