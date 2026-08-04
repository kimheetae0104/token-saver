#!/usr/bin/env python3
"""UserPromptSubmit hook: 모호한 착수형 요청에 4슬롯 리마인더 주입.
결정론 휴리스틱만 사용(LLM 호출 없음 — AI-YAGNI). 사소한 요청은 침묵.
"""
import json
import re
import sys

ACTION_WORDS = r"(만들|구현|개발|작성|추가|리팩터|고쳐|수정|바꿔|변경|설계|빌드|생성)"
SUCCESS_WORDS = r"(기준|완료되면|성공|테스트|검증|확인되면|되면 끝|승인)"
SCOPE_WORDS = r"(파일|모듈|디렉터리|폴더|전체|~까지|만|만큼|범위)"

WORD_COUNT_MAX = 25  # 이보다 길면 이미 맥락이 충분하다고 간주


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        return
    prompt = prompt.strip()
    if not prompt:
        return

    words = re.findall(r"\S+", prompt)
    if len(words) > WORD_COUNT_MAX:
        return  # 이미 충분히 길게 씀 — 넛지 불필요

    has_action = re.search(ACTION_WORDS, prompt) is not None
    if not has_action:
        return  # 착수형 요청이 아니면(질문·확인 등) 대상 아님

    has_success = re.search(SUCCESS_WORDS, prompt) is not None
    has_scope = re.search(SCOPE_WORDS, prompt) is not None

    if has_success and has_scope:
        return  # 이미 충분

    missing = []
    if not has_scope:
        missing.append("범위(어디까지)")
    if not has_success:
        missing.append("성공기준(뭐가 되면 끝)")

    print(f"💡 착수 전 확인: {', '.join(missing)}이 불명확하면 되묻고, 명확하면 파싱본 echo 후 진행 권장.")


if __name__ == "__main__":
    main()
