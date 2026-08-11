"""대형 파일 픽스처 생성기 (결정론적, LLM 불필요 — AI-YAGNI).
스케일 민감도 테스트용: 통독 비용은 파일 크기에 비례, grep은 무관 → 클수록 격차 커야 함.
매 7번째 함수에 @cached 데코레이터를 심는다(정답 = 그 인덱스들)."""
import os

LINES_TARGET = 60  # 함수 개수
out = ['"""자동생성 대형 모듈 — 스케일 테스트 픽스처. 손으로 편집 금지."""', "", "import functools", "", ""]
out += ["def cached(fn):", "    return functools.lru_cache(maxsize=None)(fn)", "", ""]
cached_idx = []
for i in range(LINES_TARGET):
    if i % 7 == 0:
        out.append("@cached")
        cached_idx.append(i)
    out.append(f"def compute_metric_{i:02d}(x, y):")
    out.append(f'    """Metric {i}: 가짜 비즈니스 로직 채우기용."""')
    out.append(f"    acc = x * {i + 1} + y")
    for j in range(6):  # 함수마다 여러 줄 → 통독 비용 부풀리기
        out.append(f"    acc = acc + {j} * {i} - ({j} ^ {i % 5})")
    out.append("    return acc")
    out.append("")
out.append("")
out.append(f"# ground-truth-cached-count={len(cached_idx)}")
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "big_module.py")
open(out_path, "w").write("\n".join(out))
print(f"generated {out_path}: {len(cached_idx)} cached functions at indices {cached_idx}")
