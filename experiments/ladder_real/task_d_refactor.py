"""Task D oracle — 소규모 리팩터. 중복된 elif 분기를 정리한 describe_grade를 채점.
기능 동등성(functional) + 구조적 개선(단일 return, 즉 분기별 중복 return 제거) 둘 다 확인.
"""
import ast
import inspect
import textwrap

MESSY_CODE = '''
def describe_grade(score):
    if score >= 90:
        letter = "A"
        message = "Excellent work, grade: " + letter
        return message
    elif score >= 80:
        letter = "B"
        message = "Good work, grade: " + letter
        return message
    elif score >= 70:
        letter = "C"
        message = "Average work, grade: " + letter
        return message
    elif score >= 60:
        letter = "D"
        message = "Below average work, grade: " + letter
        return message
    else:
        letter = "F"
        message = "Failing work, grade: " + letter
        return message
'''

CASES = [
    (100, "Excellent work, grade: A"),
    (90, "Excellent work, grade: A"),
    (89, "Good work, grade: B"),
    (80, "Good work, grade: B"),
    (79, "Average work, grade: C"),
    (70, "Average work, grade: C"),
    (69, "Below average work, grade: D"),
    (60, "Below average work, grade: D"),
    (59, "Failing work, grade: F"),
    (0, "Failing work, grade: F"),
]


def check_functional(candidate_fn):
    failures = []
    for score, expected in CASES:
        try:
            got = candidate_fn(score)
        except Exception as e:
            failures.append(f"{score!r}: raised {e!r}")
            continue
        if got != expected:
            failures.append(f"{score!r}: expected {expected!r}, got {got!r}")
    return len(failures) == 0, failures


def check_structural(candidate_fn):
    """리팩터 신호: elif 분기(반복되는 if/elif/return 중복 패턴)가 제거됐는지."""
    try:
        src = textwrap.dedent(inspect.getsource(candidate_fn))
        tree = ast.parse(src)
    except (OSError, TypeError, SyntaxError) as e:
        return False, [f"source unavailable: {e!r}"]
    func = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)), None)
    if func is None:
        return False, ["no function found"]
    n_elif = sum(
        1 for n in ast.walk(func)
        if isinstance(n, ast.If) and len(n.orelse) == 1 and isinstance(n.orelse[0], ast.If)
    )
    if n_elif > 0:
        return False, [f"elif 분기 {n_elif}개 남음 — 중복 if/elif/return 구조가 그대로임"]
    return True, []


if __name__ == "__main__":
    def reference(score: int) -> str:
        labels = [(90, "A", "Excellent"), (80, "B", "Good"), (70, "C", "Average"),
                  (60, "D", "Below average"), (0, "F", "Failing")]
        for threshold, letter, adj in labels:
            if score >= threshold:
                return f"{adj} work, grade: {letter}"
        return "Failing work, grade: F"
    ok, fails = check_functional(reference)
    print("functional:", "OK" if ok else fails)
    ok2, fails2 = check_structural(reference)
    print("structural:", "OK" if ok2 else fails2)
