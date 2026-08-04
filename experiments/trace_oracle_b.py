"""Experiment 7b oracle — harder programs for Haiku boundary.
L6: long computation chains. L7: Python semantic traps.
"""
import json, sys

PROGRAMS = [
    {
        "id": "L6a", "level": 6,
        "code": "x, y = 3, 7\nfor i in range(1, 41):\n    if (x + y) % 5 < 2:\n        x = (x * 2 + y + i) % 199\n    elif x > y:\n        x, y = y, (x - y + i * 3) % 199\n    else:\n        y = (y * 2 - x + i) % 199",
        "report_vars": ["x", "y"],
        "desc": "40-step conditional chain with mod, simultaneous assignment",
    },
    {
        "id": "L6b", "level": 6,
        "code": "a, b = 1, 1\nfor i in range(25):\n    a, b = (a + b * (i % 3 + 1)) % 89, (b + a * (i % 4 + 1)) % 97",
        "report_vars": ["a", "b"],
        "desc": "25-step dual accumulator, simultaneous assignment trap",
    },
    {
        "id": "L7a", "level": 7,
        "code": "fns = [lambda x: x + i for i in range(5)]\nresults = [f(10) for f in fns]",
        "report_vars": ["results"],
        "desc": "late-binding closure trap",
    },
    {
        "id": "L7b", "level": 7,
        "code": "def add(val, lst=[]):\n    lst.append(val)\n    return lst\n\na = add(1)\nb = add(2)\nc = add(3, [])\nd = add(4)",
        "report_vars": ["a", "b", "c", "d"],
        "desc": "mutable default arg + object aliasing",
    },
    {
        "id": "L7c", "level": 7,
        "code": "a = [1, 2, 3, 4, 5]\na[0], a[a[0]] = a[a[0]], a[0]",
        "report_vars": ["a"],
        "desc": "tuple unpacking LHS mutation order",
    },
    {
        "id": "L7d", "level": 7,
        "code": "counters = {}\ndef inc(key, d=counters):\n    d[key] = d.get(key, 0) + 1\n    return d[key]\n\nfns = [lambda: inc(str(i)) for i in range(3)]\nr1 = fns[0]()\nr2 = fns[1]()\nr3 = fns[2]()\nr4 = fns[0]()\n\nfns2 = [lambda i=i: inc(str(i)) for i in range(3)]\nr5 = fns2[0]()\nr6 = fns2[1]()\nr7 = fns2[2]()\n\nresults = [r1, r2, r3, r4, r5, r6, r7]\nstate = dict(counters)",
        "report_vars": ["results", "state"],
        "desc": "combined: late-binding + mutable default + shared state super trap",
    },
]


def compute_all():
    results = {}
    for p in PROGRAMS:
        ns = {"__builtins__": __builtins__}
        exec(p["code"], ns, ns)
        vals = {}
        for v in p["report_vars"]:
            val = ns[v]
            if isinstance(val, tuple):
                val = list(val)
            vals[v] = val
        results[p["id"]] = vals
    return results


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
