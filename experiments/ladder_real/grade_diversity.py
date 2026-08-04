"""과제 다양성 확대(D/E/F) 채점기 — attempts_diversity/{d,e,f}_haiku_NN.py 를 오라클로 채점.
결정론 채점만 사용(LLM 판단 없음 — AI-YAGNI). grade_n10.py와 동일 패턴.
"""
import glob
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import task_d_refactor as oracle_d
import task_e_config as oracle_e
import task_f_multifile as oracle_f

ATTEMPTS_DIR = os.path.join(os.path.dirname(__file__), "attempts_diversity")


def _load_module(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_fn(path, fn_name):
    return getattr(_load_module(path), fn_name)


def grade_task(letter, fn_name, grader, inject=None):
    """inject: (module) -> None — 로드 직후, getattr 전에 후보 모듈 네임스페이스에
    의존성을 주입할 훅(F과제의 to_cents 헬퍼처럼 '이미 스코프에 있다고 가정'한 값)."""
    results = []
    for path in sorted(glob.glob(os.path.join(ATTEMPTS_DIR, f"{letter}_haiku_*.py"))):
        try:
            mod = _load_module(path)
            if inject:
                inject(mod)
            fn = getattr(mod, fn_name)
            ok, detail = grader(fn)
        except Exception as e:
            ok, detail = False, [f"load/exec error: {e!r}"]
        results.append((os.path.basename(path), ok, detail))
    return results


def grade_d(fn):
    func_ok, func_fail = oracle_d.check_functional(fn)
    struct_ok, struct_fail = oracle_d.check_structural(fn)
    ok = func_ok and struct_ok
    detail = (func_fail if not func_ok else []) + (struct_fail if not struct_ok else [])
    return ok, detail


def grade_e(fn):
    try:
        out = fn(dict(oracle_e.BASE_CONFIG))
    except Exception as e:
        return False, [f"raised {e!r}"]
    return oracle_e.check(out)


def grade_f(fn):
    func_ok, func_fail = oracle_f.check_functional(fn)
    helper_ok, helper_fail = oracle_f.check_uses_helper(fn)
    ok = func_ok and helper_ok
    detail = (func_fail if not func_ok else []) + (helper_fail if not helper_ok else [])
    return ok, detail


def main():
    all_results = {}
    all_results["D"] = grade_task("d", "describe_grade", grade_d)
    all_results["E"] = grade_task("e", "apply_defaults", grade_e)
    all_results["F"] = grade_task("f", "total_cents", grade_f,
                                   inject=lambda mod: setattr(mod, "to_cents", oracle_f.to_cents))

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
