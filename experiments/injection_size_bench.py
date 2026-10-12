"""experiments/injection_size_bench.py — 부품별 끄기 실험 2단계
(docs/superpowers/specs/2026-10-12-harness-ablation-design.md): 매 턴 컨텍스트에 글을
넣는 UserPromptSubmit 부품 3개가 실제로 얼마나 자주, 몇 글자를 넣는지 잰다.

API 호출 없음. 실제 세션 트랜스크립트에서 사람이 친 프롬프트를 뽑아 intent_gate.py·
habit_coaching.py에 그대로 넣어 보고, measure.py는 세션마다 check_line()을 한 번 부른다
(세션 끝 시점 값이라 턴별 값의 근사 — 줄 길이는 턴 수·경고 유무로만 조금 변한다).
프롬프트 원문은 출력하지 않는다(통계만).

실행: python3 experiments/injection_size_bench.py [--limit N]
"""
import argparse
import glob
import json
import os
import statistics
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import measure  # noqa: E402

TRANSCRIPTS = os.path.expanduser("~/.claude/projects/*/*.jsonl")
HOOKS = {
    "intent_gate": os.path.join(REPO, "hooks", "intent_gate.py"),
    "habit_coaching": os.path.join(REPO, "hooks", "habit_coaching.py"),
}


def human_prompts(path):
    """(출처, 프롬프트) 목록. 문자열 content, 사이드체인 아님, 시스템 태그로 시작 안 함,
    promptSource=system(앱이 넣은 글) 제외. 출처: entrypoint가 claude-desktop이면 "사람",
    sdk-py·sdk-cli면 "자동"(예약 실행 등 사람이 직접 치지 않은 프롬프트)."""
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") != "user" or d.get("isSidechain"):
                    continue
                c = (d.get("message") or {}).get("content")
                if d.get("promptSource") == "system":
                    continue
                if isinstance(c, str) and c.strip() and not c.lstrip().startswith("<"):
                    src = "사람" if d.get("entrypoint") == "claude-desktop" else "자동"
                    out.append((src, c))
    except OSError:
        pass
    return out


def injected_chars(stdout):
    """훅 stdout에서 어시스턴트 컨텍스트로 들어가는 글(additionalContext) 글자 수."""
    if not stdout.strip():
        return 0
    try:
        d = json.loads(stdout)
        return len(d.get("hookSpecificOutput", {}).get("additionalContext", ""))
    except Exception:
        return len(stdout.strip())  # plain stdout도 컨텍스트로 들어간다


def run_hook(hook, prompt, env):
    p = subprocess.run([sys.executable, hook], input=json.dumps({"prompt": prompt, "session_id": "bench"}),
                       capture_output=True, text=True, env=env, timeout=10)
    return injected_chars(p.stdout)


def summarize(name, sizes, turns):
    fired = [s for s in sizes if s > 0]
    rate = len(fired) / turns if turns else 0
    mean_fired = statistics.mean(fired) if fired else 0
    per_turn = sum(sizes) / turns if turns else 0
    print(f"{name:15s} 발화 {len(fired):5d}/{turns} ({rate:6.1%})  발화당 평균 {mean_fired:6.1f}자  "
          f"턴당 평균 {per_turn:6.1f}자  최대 {max(sizes) if sizes else 0}자")
    return {"fired": len(fired), "turns": turns, "rate": rate,
            "mean_chars_when_fired": mean_fired, "chars_per_turn": per_turn}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="프롬프트 최대 개수(0=전부)")
    args = ap.parse_args()

    files = sorted(glob.glob(TRANSCRIPTS))
    prompts = [p for f in files for p in human_prompts(f)]
    if args.limit:
        prompts = prompts[: args.limit]

    with tempfile.TemporaryDirectory() as data_dir:
        env = {k: v for k, v in os.environ.items() if not k.startswith("TOKEN_SAVER_DISABLE_")}
        env["CLAUDE_PLUGIN_DATA"] = data_dir  # 실제 플러그인 상태 파일을 건드리지 않게
        sizes = {name: [(src, run_hook(h, p, env)) for src, p in prompts] for name, h in HOOKS.items()}

    check_sizes = []
    for f in files:
        try:
            check_sizes.append(len(measure.check_line(f) or ""))
        except Exception:
            continue

    print(f"세션 파일 {len(files)}개, 프롬프트 {len(prompts)}개\n")
    result = {}
    for src in ("사람", "자동"):
        n = sum(1 for s, _ in prompts if s == src)
        print(f"[{src}]")
        for name, rows in sizes.items():
            result[f"{name}/{src}"] = summarize(name, [v for s, v in rows if s == src], n)
    nonzero = [s for s in check_sizes if s > 0]
    print(f"{'measure_check':15s} 세션 {len(nonzero)}/{len(check_sizes)}에서 출력  "
          f"줄 길이 중앙값 {statistics.median(nonzero) if nonzero else 0:.0f}자  "
          f"최대 {max(nonzero) if nonzero else 0}자 (매 턴 발화)")
    result["measure_check"] = {"sessions": len(check_sizes), "nonzero": len(nonzero),
                               "median_chars": statistics.median(nonzero) if nonzero else 0}
    print("\n" + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
