"""Task F oracle — 멀티파일 컨텍스트 버그수정. 후보는 total_cents(prices)만 고치되
반드시 기존 to_cents 헬퍼(수정 금지, 그대로 재사용)를 통해서 계산해야 함.
"""
import ast
import inspect
import textwrap

HELPER_SOURCE = '''
def to_cents(dollars: float) -> int:
    """money.py — 다른 모듈에서 가져다 쓰는 헬퍼. 수정 금지."""
    return round(dollars * 100)
'''

BUGGY_CALLER = '''
def total_cents(prices):
    """billing.py — to_cents를 잘못 써서 다시 달러로 나눠버리는 버그가 있음."""
    total = 0
    for p in prices:
        total += to_cents(p) / 100
    return total
'''

CASES = [
    ([19.99, 5.01], 2500),
    ([], 0),
    ([0.1, 0.2], 30),
    ([19.999], 2000),
    ([1.005, 1.005], 200),  # round()의 부동소수점 표현 특성상 1.005*100=100.49999...→100
]


def to_cents(dollars: float) -> int:
    return round(dollars * 100)


def check_functional(candidate_fn):
    failures = []
    for prices, expected in CASES:
        try:
            got = candidate_fn(list(prices))
        except Exception as e:
            failures.append(f"{prices!r}: raised {e!r}")
            continue
        if got != expected:
            failures.append(f"{prices!r}: expected {expected}, got {got!r}")
    return len(failures) == 0, failures


def check_uses_helper(candidate_fn):
    """to_cents 호출을 실제로 쓰는지(재구현으로 우회하지 않았는지) AST로 확인."""
    try:
        src = textwrap.dedent(inspect.getsource(candidate_fn))
        tree = ast.parse(src)
    except (OSError, TypeError, SyntaxError) as e:
        return False, [f"source unavailable: {e!r}"]
    calls_helper = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "to_cents"
        for n in ast.walk(tree)
    )
    if not calls_helper:
        return False, ["to_cents 헬퍼를 호출하지 않음(직접 재구현으로 우회한 것으로 보임)"]
    return True, []


if __name__ == "__main__":
    def reference(prices: list) -> int:
        total = 0
        for p in prices:
            total += to_cents(p)
        return total
    ok, fails = check_functional(reference)
    print("functional:", "OK" if ok else fails)
    ok2, fails2 = check_uses_helper(reference)
    print("uses_helper:", "OK" if ok2 else fails2)
