"""실험 4 오라클 — 계산기 구현 과제의 결정론적 채점기.

ground truth: 아래 reference_calculate (실험자가 작성, 자체검증됨).
후보 코드는 calculate(s)->int 를 제공해야 하고, 이 스위트로 pass/fail 채점.
난이도 함정: unary minus, 0쪽 절삭 나눗셈(-7/2==-3), 중첩 괄호, 공백, 연산자 우선순위.
"""
import math


def _tdiv(a, b):
    """0 방향 절삭 나눗셈 (파이썬 // 는 -inf 방향이라 부적합)."""
    return int(a / b) if b != 0 else None


def reference_calculate(s: str) -> int:
    # 재귀적 하강 파서: expr = term (('+'|'-') term)* ; term = factor (('*'|'/') factor)* ;
    # factor = number | '(' expr ')' | '-' factor | '+' factor
    s = s.replace(" ", "")
    pos = 0

    def peek():
        return s[pos] if pos < len(s) else ""

    def parse_expr():
        nonlocal pos
        val = parse_term()
        while peek() in ("+", "-"):
            op = s[pos]; pos += 1
            rhs = parse_term()
            val = val + rhs if op == "+" else val - rhs
        return val

    def parse_term():
        nonlocal pos
        val = parse_factor()
        while peek() in ("*", "/"):
            op = s[pos]; pos += 1
            rhs = parse_factor()
            val = val * rhs if op == "*" else int(val / rhs)  # 0쪽 절삭
        return val

    def parse_factor():
        nonlocal pos
        c = peek()
        if c == "-":
            pos += 1
            return -parse_factor()
        if c == "+":
            pos += 1
            return parse_factor()
        if c == "(":
            pos += 1
            val = parse_expr()
            pos += 1  # skip ')'
            return val
        start = pos
        while pos < len(s) and s[pos].isdigit():
            pos += 1
        return int(s[start:pos])

    return parse_expr()


# 함정 위주 테스트 케이스 (expr, expected)
TESTS = [
    ("1 + 1", 2),
    ("2-1 + 2", 3),
    ("(1+(4+5+2)-3)+(6+8)", 23),
    ("3+2*2", 7),
    (" 3/2 ", 1),
    (" 3+5 / 2 ", 5),
    ("2*3+4", 10),
    ("2+3*4-1", 13),
    ("-3+2", -1),                 # unary minus 선두
    ("2*-3", -6),                 # 이항 뒤 unary
    ("-(3+4)", -7),               # 괄호 앞 unary
    ("7/-2", -3),                 # 0쪽 절삭 (-4 아님)
    ("-7/2", -3),                 # 0쪽 절삭 (-4 아님)
    ("(-7)/2", -3),
    ("6/(-4)", -1),               # 절삭 (-2 아님)
    ("10 - 2 * 3", 4),
    ("100 * ( 2 + 12 ) / 14", 100),
    ("2*(5-(3+1))", 2),
    ("- -3", 3),                  # 이중 unary
    ("3 - - - 4", -1),            # 삼중 unary
    ("1-(-2)", 3),
    ("((2))", 2),
    ("14-3/2", 13),               # 3/2=1
    ("0-2147483647", -2147483647),
    ("2*3*4*5", 120),
]


def grade(calculate):
    """calculate callable을 TESTS로 채점. (passed, total, failures) 반환."""
    passed, failures = 0, []
    for expr, expected in TESTS:
        try:
            got = calculate(expr)
        except Exception as e:
            got = f"ERROR:{type(e).__name__}:{e}"
        if got == expected:
            passed += 1
        else:
            failures.append((expr, expected, got))
    return passed, len(TESTS), failures


if __name__ == "__main__":
    # 자체검증: 레퍼런스는 만점이어야 함. 또한 expected 가 파이썬 트릭과 일치하는지 교차확인.
    p, t, f = grade(reference_calculate)
    print(f"reference: {p}/{t}")
    for expr, exp, got in f:
        print(f"  FAIL {expr!r}: expected {exp}, got {got}")
    assert p == t, "레퍼런스가 자체 테스트를 통과하지 못함 — 테스트 오류"
    print("OK: 오라클 자체검증 통과")
