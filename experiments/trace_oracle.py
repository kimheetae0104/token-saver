"""Experiment 7 oracle — multi-step state tracking boundary.
10 programs at 5 difficulty levels. Ground truth via exec().
"""
import json, sys

PROGRAMS = [
    {
        "id": "L1a", "level": 1,
        "code": "a = 7\nb = a * 3 - 2\nc = b % a + 1\na = c * 2 - b",
        "report_vars": ["a", "b", "c"],
        "desc": "linear arithmetic",
    },
    {
        "id": "L1b", "level": 1,
        "code": "x = 13\ny = x // 4\nz = x - y * 4\nx = z ** 2 + y",
        "report_vars": ["x", "y", "z"],
        "desc": "integer division and power",
    },
    {
        "id": "L2a", "level": 2,
        "code": "total = 0\nn = 1\nfor i in range(5):\n    total += n\n    n = n * 2 + 1",
        "report_vars": ["total", "n"],
        "desc": "loop with doubling sequence",
    },
    {
        "id": "L2b", "level": 2,
        "code": "s = 100\nfor i in range(1, 7):\n    if s > 50:\n        s = s - i * 5\n    else:\n        s = s + i * 3",
        "report_vars": ["s"],
        "desc": "loop with branching threshold",
    },
    {
        "id": "L3a", "level": 3,
        "code": "grid = [[0]*4 for _ in range(4)]\nfor i in range(4):\n    for j in range(4):\n        if (i + j) % 3 == 0:\n            grid[i][j] = i * 4 + j + 1\n        elif i > j:\n            grid[i][j] = -1\ntotal = sum(grid[i][i] for i in range(4))",
        "report_vars": ["grid", "total"],
        "desc": "2D grid with modular condition",
    },
    {
        "id": "L3b", "level": 3,
        "code": "arr = list(range(1, 9))\nfor i in range(len(arr)):\n    if arr[i] % 2 == 0:\n        arr[i] = arr[i] // 2\n    else:\n        arr[i] = arr[i] * 3 + 1\nfor i in range(0, len(arr)-1, 2):\n    arr[i], arr[i+1] = arr[i+1], arr[i]\nresult = sum(arr[::2]) - sum(arr[1::2])",
        "report_vars": ["arr", "result"],
        "desc": "array transform, pair swap, slice difference",
    },
    {
        "id": "L4a", "level": 4,
        "code": "matrix = [[0]*5 for _ in range(5)]\nfor i in range(5):\n    found = False\n    for j in range(5):\n        val = (i * 3 + j * 7) % 11\n        if val > 9:\n            matrix[i][j] = -val\n            found = True\n            break\n        matrix[i][j] = val\n    if not found:\n        matrix[i][4] = 99\ndiag = [matrix[i][i] for i in range(5)]",
        "report_vars": ["matrix", "diag"],
        "desc": "nested loop with break/sentinel, modular arithmetic",
    },
    {
        "id": "L4b", "level": 4,
        "code": "data = [3, 1, 4, 1, 5, 9, 2, 6]\nwindow = 3\nresult = []\nfor i in range(len(data) - window + 1):\n    chunk = data[i:i+window]\n    median = sorted(chunk)[1]\n    result.append(median)\n    if median > data[i+1]:\n        data[i+1] = median",
        "report_vars": ["data", "result"],
        "desc": "sliding window median with forward mutation",
    },
    {
        "id": "L5a", "level": 5,
        "code": "mem = [0] * 8\npc_a, pc_b = 0, 0\nreg_a, reg_b = 1, 1\nfor step in range(12):\n    if step % 2 == 0:\n        idx = pc_a % 8\n        mem[idx] = (mem[idx] + reg_a) % 17\n        reg_a = mem[(idx + 3) % 8] + 1\n        pc_a += reg_a\n    else:\n        idx = pc_b % 8\n        old = mem[idx]\n        mem[idx] = (old * reg_b + 1) % 13\n        reg_b = (old + reg_b) % 5 + 1\n        pc_b += 2\nfinal_sum = sum(mem)",
        "report_vars": ["mem", "reg_a", "reg_b", "pc_a", "pc_b", "final_sum"],
        "desc": "interleaved dual state machines on shared memory",
    },
    {
        "id": "L5b", "level": 5,
        "code": "memo = {}\ndef f(n):\n    if n in memo: return memo[n]\n    if n <= 1: result = 1\n    elif n % 3 == 0: result = f(n // 3) + f(n - 1)\n    elif n % 3 == 1: result = f(n - 1) * 2 + 1\n    else: result = f(n - 1) + f(n - 2) + n\n    memo[n] = result\n    return result\nqueries = [7, 3, 11, 5, 12]\nanswers = [f(q) for q in queries]",
        "report_vars": ["answers"],
        "desc": "recursive function with memo, scrambled call order",
    },
]


def compute_all():
    results = {}
    for p in PROGRAMS:
        ns = {"__builtins__": __builtins__}
        exec(p["code"], ns, ns)
        results[p["id"]] = {v: ns[v] for v in p["report_vars"]}
    return results


def make_prompt(p):
    vars_str = ", ".join(p["report_vars"])
    return (
        f"아래 Python 프로그램을 정확히 실행(트레이스)하여 최종 변수값을 보고하라.\n\n"
        f"```python\n{p['code']}\n```\n\n"
        f"보고할 변수: {vars_str}\n"
        f"각 변수의 최종값을 values 객체에 담아라. 배열은 JSON 배열, 숫자는 숫자로."
    )


def score(pid, candidate, truth):
    expected = truth[pid]
    errors = []
    for var, exp_val in expected.items():
        got = candidate.get(var)
        if got != exp_val:
            errors.append(f"{var}: expected {json.dumps(exp_val)}, got {json.dumps(got)}")
    return len(errors) == 0, errors


if __name__ == "__main__":
    gt = compute_all()
    for pid, vals in sorted(gt.items()):
        p = next(x for x in PROGRAMS if x["id"] == pid)
        print(f"[{pid}] L{p['level']} {p['desc']}")
        for k, v in vals.items():
            print(f"  {k} = {json.dumps(v)}")
    if "--json" in sys.argv:
        print("\n" + json.dumps(gt))
    else:
        print(f"\nGround truth: {len(gt)} programs OK.")
