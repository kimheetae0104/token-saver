#!/usr/bin/env python3
"""UserPromptSubmit hook: 사용자 채팅 습관에서 토큰 낭비 패턴 감지.
장황, 방향전환, 불필요한 재확인 등을 한 줄 피드백으로 제시.
"""
import json
import re
import sys

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

    feedback = None

    # 패턴 1: 과도한 연결어 → 장황 경향(구어체 축약형 포함)
    connectors = len(re.findall(r"(그리고|또한|그런데|근데|그래서|하지만|그렇지만|그래도|게다가|혹시)", prompt))
    if connectors > 3:
        feedback = "💬 연결어 4개↑ — 문장 분리나 핵심 선별로 간결화"

    # 패턴 2: 과거 회고형 배경 서두 + 재확인 요청 결합(전형적 낭비 패턴)
    retro = re.search(r"^(어제|저번에|아까|전에|이전에)", prompt) is not None
    recheck = re.search(r"(맞죠|맞나|맞나요|맞게|확인해\s?주|다시\s?확인|정확\s?한가|진짜)", prompt) is not None
    if not feedback and retro and recheck:
        feedback = "💬 과거 회고 서두+재확인 결합 — 배경 생략하고 '결과만' 요청하면 절감"

    # 패턴 3: 방향전환 — 진행 중이던 작업을 폐기하고 다른 접근으로 재지시
    # (교정 마커와 달리 "틀렸다"가 아니라 "그 방향 말고 이 방향으로"류 — 이미 진행된
    # 작업의 컨텍스트가 그대로 버려지는 패턴이라 별도로 감지)
    pivot = re.search(
        r"(대신에?\s|차라리|방향을?\s?바꿔|방향\s?전환|처음부터\s?다시|"
        r"다른\s?방식으로|다른\s?방향으로|그거\s?말고|그건\s?됐고|말고\s?다른)",
        prompt,
    ) is not None
    if not feedback and pivot:
        feedback = "🔀 방향전환 감지 — 착수 전 방향을 먼저 확정하면 진행 중이던 작업 폐기를 줄일 수 있음"

    # 패턴 4: 불필요한 긴 배경 설명(300자↑, 의존문 적음)
    if not feedback and len(prompt) > 300:
        feedback = "💬 배경 설명 과다(300자↑) — 핵심 요청만 앞에 두고 나머지는 참고로"

    # 패턴 5: 재확인 반복(짧은 요청)
    if not feedback and recheck:
        words = len(re.findall(r"\S+", prompt))
        if words < 15:
            feedback = "💭 짧은 재확인 — 이전 결과를 신뢰하고 다음으로 (확신 부족 = 컨텍스트 비용)"

    # 패턴 6: 명령 앞에 이유/배경이 너무 길면
    if not feedback and re.search(r"(왜냐하면|이유는|배경은)", prompt):
        cmd_match = re.search(r"(만들|구현|고쳐|하자)", prompt)
        before_cmd = prompt[: cmd_match.start()] if cmd_match else ""
        if len(before_cmd) > 150:
            feedback = "💬 요청 전 배경이 150자↑ — 핵심만 앞에, 나머지 요청 중 언급"

    if feedback:
        print(feedback)


if __name__ == "__main__":
    main()
