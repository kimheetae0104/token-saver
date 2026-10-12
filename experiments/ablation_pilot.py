"""experiments/ablation_pilot.py — 부품별 끄기 실험 3단계 파일럿
(docs/superpowers/specs/2026-10-12-harness-ablation-design.md).

같은 과제를 9개 조건(전부 켬, 전부 끔, 하나만 끔 7개)으로 `claude -p`에 돌리고,
비용(total_cost_usd)·턴 수·정답(외부 오라클)을 기록한다.

격리: `--setting-sources project`로 사용자 설정(전역 설치된 token-saver, 사용자 훅)을 빼고
`--plugin-dir`로 이 저장소의 token-saver만 싣는다. 부품 끄기는 env 킬스위치로 한다
(CLAUDE_PLUGIN_DATA는 Claude Code가 플러그인마다 정하므로 config.json 경로를 고정할 수 없다).
CLAUDE_CODE_ENTRYPOINT=cli로 고정한다 — 비워 두면 sdk-cli가 되어 habit_coaching이 스스로
꺼지고(실험24 뒤 수정), "habit_coaching만 끔" 조건이 "전부 켬"과 같아진다.

과제: ladder_real/task_b_bugfix(버그+lint). 프롬프트는 일부러 짧게 둬 4슬롯 부품이 발화하게
한다. 요구사항은 작업 폴더의 README.txt에 있고, 정답 판정은 모델이 고칠 수 없는 바깥
오라클(task_b의 check_functional·check_lint)로 한다.

되묻기: 첫 호출 뒤 오라클이 실패하면 사람 답을 흉내 낸 고정 후속 프롬프트(FOLLOWUP)를
같은 세션에 한 번 보낸다(--resume). 2026-10-12 시험 실행에서 4슬롯 부품이 켜진 조건은 첫 호출에서
고치지 않고 되물은 채 끝났다 — 대화형이라면 사람이 답했을 자리라, 한 번은 답해 준다.
비용·턴은 두 호출을 합친다.

예산: 누적 비용이 --budget(기본 5달러)을 넘을 것 같으면 다음 실행을 시작하지 않는다.
실행마다 --max-budget-usd로도 묶는다.

실행: python3 experiments/ablation_pilot.py --reps 1   # 비용 확인용 1바퀴
결과: experiments/ablation_pilot_results.jsonl (실행마다 한 줄 덧붙임)
"""
import argparse
import importlib.util
import json
import os
import subprocess
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(REPO, "experiments", "ablation_pilot_results.jsonl")
TASK_B = os.path.join(REPO, "experiments", "ladder_real", "task_b_bugfix.py")

PARTS = {
    "read_guard": ["TOKEN_SAVER_DISABLE_GUARD"],
    "trim": ["TOKEN_SAVER_DISABLE_GREP_TRIM", "TOKEN_SAVER_DISABLE_BASH_TRIM"],
    "ladder_gate": ["TOKEN_SAVER_DISABLE_LADDER_GATE"],
    "four_slot": ["TOKEN_SAVER_DISABLE_INTENT_GATE", "TOKEN_SAVER_DISABLE_PROMPT_GATE"],
    "habit_coaching": ["TOKEN_SAVER_DISABLE_HABIT_COACHING"],
    "measure_check": ["TOKEN_SAVER_DISABLE_MEASURE_CHECK"],
    "check_gate": ["TOKEN_SAVER_DISABLE_CHECK_GATE"],
}
CONDITIONS = ["all_on", "all_off"] + [f"off_{p}" for p in PARTS]

PROMPT = "dupes.py 고쳐줘"
FOLLOWUP = "README.txt에 적힌 요구사항대로 dupes.py를 고치고 끝내줘. 다른 파일은 건드리지 마."
README = """dupes.py의 find_duplicates를 고친다.
- 두 번째 이후로 나온 값을 나온 순서대로 돌려준다. 예: [1,2,2,3,3,3] -> [2,3,3], ["a","b","a"] -> ["a"]
- 여러 번 불러도 결과가 서로 섞이지 않아야 한다.
- 모든 인자와 반환값에 타입 힌트를 단다. 가변 기본 인자와 맨 except(bare except)는 쓰지 않는다.
"""


def load_task_b():
    spec = importlib.util.spec_from_file_location("task_b", TASK_B)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def oracle(task_b, workdir):
    path = os.path.join(workdir, "dupes.py")
    try:
        src = open(path).read()
    except OSError:
        return False, ["dupes.py 없음"]
    lint_ok, issues = task_b.check_lint(src)
    ns = {}
    try:
        exec(compile(src, path, "exec"), ns)
        fn = ns["find_duplicates"]
        fn([1, 1])  # 두 번 불러 상태 누수 확인
        func_ok, failures = task_b.check_functional(fn)  # (통과 여부, 실패 목록)
    except Exception as e:
        return False, [f"실행 오류: {e}"]
    return lint_ok and func_ok, issues + ([] if func_ok else [f"기능 실패: {failures}"])


def env_for(condition):
    env = {k: v for k, v in os.environ.items() if not k.startswith("TOKEN_SAVER_DISABLE_")}
    env["CLAUDE_CODE_ENTRYPOINT"] = "cli"
    off = []
    if condition == "all_off":
        off = [v for vs in PARTS.values() for v in vs]
    elif condition.startswith("off_"):
        off = PARTS[condition[4:]]
    for v in off:
        env[v] = "1"
    return env


def call(cmd_tail, workdir, env, model, per_run_cap):
    cmd = ["claude", "-p", *cmd_tail, "--model", model, "--output-format", "json",
           "--setting-sources", "project", "--plugin-dir", REPO,
           "--max-budget-usd", str(per_run_cap),
           "--allowedTools", "Read", "Edit", "Write", "Grep", "Glob", "Bash(python3 *)",
           "mcp__plugin_token-saver_token-saver__token_saver_suggest_tier",
           "mcp__plugin_token-saver_token-saver__token_saver_check"]
    p = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=900)
    try:
        return json.loads(p.stdout), p.returncode
    except Exception:
        return {"parse_error": p.stdout[-500:], "stderr": p.stderr[-500:]}, p.returncode


def run_once(task_b, condition, model, per_run_cap):
    workdir = tempfile.mkdtemp(prefix=f"ablation_{condition}_")
    with open(os.path.join(workdir, "dupes.py"), "w") as f:
        f.write(task_b.BUGGY_CODE.lstrip())
    with open(os.path.join(workdir, "README.txt"), "w") as f:
        f.write(README)
    env = env_for(condition)
    t0 = time.time()
    out, code = call([PROMPT], workdir, env, model, per_run_cap)
    ok, issues = oracle(task_b, workdir)
    followups = 0
    cost = out.get("total_cost_usd") or 0
    turns = out.get("num_turns") or 0
    first_pass = ok
    if not ok and out.get("session_id"):
        out2, code = call([FOLLOWUP, "--resume", out["session_id"]], workdir, env, model, per_run_cap)
        followups = 1
        cost += out2.get("total_cost_usd") or 0
        turns += out2.get("num_turns") or 0
        ok, issues = oracle(task_b, workdir)
        out = out2
    elapsed = time.time() - t0
    usage = out.get("usage") or {}
    return {
        "condition": condition, "model": model, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cost_usd": round(cost, 6), "num_turns": turns, "followups": followups,
        "first_call_pass": first_pass,
        "is_error": out.get("is_error"), "subtype": out.get("subtype"),
        "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
        "cache_read": usage.get("cache_read_input_tokens"),
        "cache_creation": usage.get("cache_creation_input_tokens"),
        "oracle_pass": ok, "oracle_issues": issues, "elapsed_s": round(elapsed, 1),
        "exit_code": code, "workdir": workdir,
    }


def spent_so_far():
    total = 0.0
    try:
        for line in open(RESULTS):
            total += json.loads(line).get("cost_usd") or 0  # invalid 표시된 줄도 쓴 돈이라 센다
    except OSError:
        pass
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--budget", type=float, default=5.0, help="결과 파일 누적 비용 상한(달러)")
    ap.add_argument("--per-run-cap", type=float, default=0.4)
    ap.add_argument("--conditions", default=",".join(CONDITIONS))
    args = ap.parse_args()

    task_b = load_task_b()
    conds = args.conditions.split(",")
    for rep in range(args.reps):
        for c in conds:  # 조건을 번갈아 돌려 시간대 효과가 한 조건에 몰리지 않게
            spent = spent_so_far()
            if spent + args.per_run_cap > args.budget:
                print(f"예산 중단: 누적 ${spent:.3f}, 다음 실행 상한 ${args.per_run_cap} → 상한 ${args.budget} 초과 가능")
                return
            r = run_once(task_b, c, args.model, args.per_run_cap)
            with open(RESULTS, "a") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"[{rep+1}] {c:20s} ${r['cost_usd']}  턴 {r['num_turns']}  정답 {r['oracle_pass']}  "
                  f"후속 {r['followups']}  {r['elapsed_s']}s  누적 ${spent_so_far():.3f}")


if __name__ == "__main__":
    main()
