"""실험8 N=10 채점기 — attempts_n10/{a,b,c}_haiku_NN.py 를 오라클로 채점.
결정론 채점만 사용(LLM 판단 없음 — AI-YAGNI). 실패 항목은 Sonnet 에스컬레이션 후보로 표시.
"""
import glob
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import task_a_duration as oracle_a
import task_b_bugfix as oracle_b
import task_c_normalize as oracle_c

ATTEMPTS_DIR = os.path.join(os.path.dirname(__file__), "attempts_n10")


def _load_fn(path, fn_name):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, fn_name)


def grade_task(letter, fn_name, grader):
    results = []
    for path in sorted(glob.glob(os.path.join(ATTEMPTS_DIR, f"{letter}_haiku_*.py"))):
        try:
            fn = _load_fn(path, fn_name)
            ok, detail = grader(fn)
        except Exception as e:
            ok, detail = False, [f"load/exec error: {e!r}"]
        results.append((os.path.basename(path), ok, detail))
    return results


def grade_b(fn):
    from task_b_bugfix import check_functional, check_lint, BUGGY_CODE
    import inspect
    func_ok, func_fail = check_functional(fn)
    src = inspect.getsource(fn)
    lint_ok, lint_fail = check_lint(src)
    ok = func_ok and lint_ok
    detail = (func_fail if not func_ok else []) + (lint_fail if not lint_ok else [])
    return ok, detail


def grade_c(fn):
    from task_c_normalize import check, RAW
    try:
        out = fn(RAW)
    except Exception as e:
        return False, [f"raised {e!r}"]
    return check(out)


def main():
    all_results = {}
    all_results["A"] = grade_task("a", "parse_duration", oracle_a.run)
    all_results["B"] = grade_task("b", "find_duplicates", grade_b)
    all_results["C"] = grade_task("c", "normalize", grade_c)

    total_pass = 0
    total_n = 0
    for letter, results in all_results.items():
        n = len(results)
        n_pass = sum(1 for _, ok, _ in results if ok)
        total_pass += n_pass
        total_n += n
        print(f"\n=== Task {letter}: {n_pass}/{n} PASS ===")
        for name, ok, detail in results:
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {name}" + (f"  {detail}" if not ok else ""))

    print(f"\n=== 종합: {total_pass}/{total_n} PASS ({total_pass/total_n*100:.0f}%) ===")
    fails = [(letter, name) for letter, results in all_results.items()
             for name, ok, _ in results if not ok]
    if fails:
        print("에스컬레이션 후보(Sonnet 재시도 필요):")
        for letter, name in fails:
            print(f"  - Task {letter}: {name}")
    else:
        print("실패 0건 — 에스컬레이션 불필요.")


if __name__ == "__main__":
    main()
