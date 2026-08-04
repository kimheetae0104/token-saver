"""실험 9 — 오라클 없는 과제(G1~G5) 사전정의 루브릭. LLM 판단이 아니라 키워드/구조
기반 결정론 채점(AI-YAGNI). "정답"이 아니라 "필수 요소 포함 여부"만 확인 — 프로즈 채점의
근본적 한계이므로 이진 판정(핵심 요소 포함=PASS)만 하고 문체·유창성은 채점 대상 아님.
"""
import re

TASKS = {
    "G1": {
        "prompt": "REST API에서 PATCH와 PUT의 차이가 왜 중요한지 3문장 이내로 설명해줘.",
        "rubric": lambda text: (
            bool(re.search(r"PUT.{0,40}(전체|idempotent|멱등)", text, re.I))
            and bool(re.search(r"PATCH.{0,40}(부분)", text, re.I))
        ),
        "rubric_desc": "PUT=전체교체/멱등 + PATCH=부분수정 둘 다 언급",
    },
    "G2": {
        "prompt": "동기 처리와 비동기 처리를 각각 언제 써야 하는지 설명해줘.",
        "rubric": lambda text: (
            bool(re.search(r"(블로킹|blocking)", text, re.I))
            and bool(re.search(r"(I/O|입출력).{0,30}(바운드|bound)", text, re.I))
        ),
        "rubric_desc": "블로킹/논블로킹 구분 + I/O-bound 상황 언급",
    },
    "G3": {
        "prompt": (
            "다음 코드에서 문제점을 지적해줘:\n\n"
            "def get_user(username):\n"
            "    query = \"SELECT * FROM users WHERE name = '\" + username + \"'\"\n"
            "    return db.execute(query)\n"
        ),
        "rubric": lambda text: bool(
            re.search(r"(SQL\s*injection|파라미터.{0,10}(쿼리|바인딩)|parameterized|prepared\s*statement)", text, re.I)
        ),
        "rubric_desc": "SQL injection 취약점 또는 파라미터화 쿼리 언급",
    },
    "G4": {
        "prompt": (
            "함수 이름 `proc_dat`을 더 명확하게 바꿔줘. "
            "이 함수는 사용자 입력을 검증하고 정규화한다."
        ),
        "rubric": lambda text: (
            bool(re.search(r"(validate|검증)", text, re.I))
            and bool(re.search(r"(normalize|정규화)", text, re.I))
        ),
        "rubric_desc": "제안된 이름에 validate/검증 + normalize/정규화 둘 다 개념 반영",
    },
    "G5": {
        "prompt": (
            "버그 3개가 있다: (1) 로그인 실패시 500에러로 스택트레이스가 노출됨, "
            "(2) 다크모드에서 버튼 위치가 살짝 어긋남, "
            "(3) 결제 완료 후 이메일 알림이 20초 지연됨. "
            "뭐부터 고쳐야 하는지와 이유를 말해줘."
        ),
        "rubric": lambda text: (
            bool(re.search(r"\(1\)|스택\s*트레이스|500\s*에러", text[:200]))
            and bool(re.search(r"(보안|정보\s*노출|security)", text, re.I))
        ),
        "rubric_desc": "(1)번을 최우선으로 지목 + 이유에 보안/정보노출 언급",
    },
}


def grade(task_key, candidate_text):
    task = TASKS[task_key]
    ok = task["rubric"](candidate_text or "")
    return ok, task["rubric_desc"]


if __name__ == "__main__":
    good_g1 = "PUT은 리소스 전체를 덮어써서 멱등적이고, PATCH는 일부 필드만 부분수정한다."
    bad_g1 = "둘 다 리소스를 수정하는 HTTP 메서드다."
    print("G1 good:", grade("G1", good_g1))
    print("G1 bad:", grade("G1", bad_g1))
