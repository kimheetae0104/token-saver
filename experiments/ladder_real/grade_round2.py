"""실험9 후속5 — 정규식 결정론 오라클로 round2(N=20 추가분) 채점."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from task_g_oracle_less import grade

DIR = os.path.join(os.path.dirname(__file__), "attempts_g_round2")

if __name__ == "__main__":
    fails = []
    for path in sorted(glob.glob(os.path.join(DIR, "*.txt"))):
        name = os.path.basename(path)
        task_key = name.split("_")[0].upper()
        with open(path, encoding="utf-8") as f:
            text = f.read()
        ok, desc = grade(task_key, text)
        status = "PASS" if ok else "FAIL"
        print(f"{name}: {status}  ({desc})")
        if not ok:
            fails.append(name)
    print(f"\n{len(fails)} FAIL / {len(glob.glob(os.path.join(DIR, '*.txt')))} total")
    if fails:
        print("FAILs:", fails)
