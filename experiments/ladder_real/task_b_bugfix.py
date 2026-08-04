"""Task B oracle — bug+lint. 버그 있는 find_duplicates를 고쳐서
(1) 기능 테스트 통과 (2) 결정론 lint 규칙 통과 해야 함.
"""
import ast

BUGGY_CODE = '''
def find_duplicates(items, seen=[]):
    dupes = []
    for i in items:
        try:
            if i in seen:
                dupes.append(i)
            else:
                seen.append(i)
        except:
            pass
    return dupes
'''

TEST_CASES = [
    ([1, 2, 2, 3, 3, 3], [2, 3, 3]),
    ([], []),
    (["a", "b", "a"], ["a"]),
    ([1, 1, 1, 1], [1, 1, 1]),
]


def check_functional(candidate_fn):
    failures = []
    for items, expected in TEST_CASES:
        try:
            got = candidate_fn(list(items))
        except Exception as e:
            failures.append(f"{items!r}: raised {e!r}")
            continue
        if got != expected:
            failures.append(f"{items!r}: expected {expected}, got {got!r}")
    return len(failures) == 0, failures


def check_lint(source_code: str):
    """결정론 규칙: 타입힌트 有, bare except 無, 가변 기본인자 無."""
    issues = []
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        return False, [f"syntax error: {e}"]

    func = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)), None)
    if func is None:
        return False, ["no function found"]

    if func.returns is None:
        issues.append("missing return type hint")
    for arg in func.args.args:
        if arg.annotation is None:
            issues.append(f"missing type hint on param '{arg.arg}'")

    for default in func.args.defaults:
        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
            issues.append("mutable default argument")

    for node in ast.walk(func):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append("bare except")

    return len(issues) == 0, issues


if __name__ == "__main__":
    def reference(items: list) -> list:
        seen: set = set()
        dupes = []
        for i in items:
            if i in seen:
                dupes.append(i)
            else:
                seen.add(i)
        return dupes
    ok, fails = check_functional(reference)
    print("functional:", "OK" if ok else fails)
