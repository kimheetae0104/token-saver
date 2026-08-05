"""실험 9 — 오라클 없는 과제(G1~G5) 사전정의 루브릭. LLM 판단이 아니라 키워드/구조
기반 결정론 채점(AI-YAGNI). "정답"이 아니라 "필수 요소 포함 여부"만 확인 — 프로즈 채점의
근본적 한계이므로 이진 판정(핵심 요소 포함=PASS)만 하고 문체·유창성은 채점 대상 아님.

**위음성 경고(N=70 라운드 실측, PROTOCOL.md 참고)**: round2(N=20)에서 이 오라클이
7/20 FAIL 판정했으나 전부 재검증 결과 위음성으로 확인됨(G1: "부분" 대신 "일부만"·
"특정 필드만" 등 동의어 사용, G2: "블로킹"/"I/O-bound" 대신 "완료될 때까지 기다린다"·
"네트워크 요청/파일 읽기/DB 조회" 등 풀어쓴 표현). 아래 G1·G2 정규식은 그 두 가지를
반영해 보강했지만, **동의어를 계속 쫓는 건 밑 빠진 독**이다 — 표본이 늘수록 새로운
표현이 또 나올 수 있다. 그래서 이 오라클의 FAIL은 "진짜 실패" 확정이 아니라
"재검증 필요" 신호로만 취급할 것. 원문 그대로(요약 금지) Sonnet 배치판정으로
교차검증한 뒤에만 최종 판정 — 헬퍼는 `verify_fails.py` 참고.
"""
import re

TASKS = {
    "G1": {
        "prompt": "REST API에서 PATCH와 PUT의 차이가 왜 중요한지 3문장 이내로 설명해줘.",
        "rubric": lambda text: (
            bool(re.search(r"PUT.{0,40}(전체|idempotent|멱등)", text, re.I))
            and bool(re.search(r"PATCH.{0,40}(부분|일부만|특정.{0,10}필드|해당.{0,10}필드)", text, re.I))
        ),
        "rubric_desc": "PUT=전체교체/멱등 + PATCH=부분수정(동의어 포함) 둘 다 언급",
    },
    "G2": {
        "prompt": "동기 처리와 비동기 처리를 각각 언제 써야 하는지 설명해줘.",
        "rubric": lambda text: (
            bool(re.search(r"(블로킹|blocking|기다|대기)", text, re.I))
            and bool(re.search(
                r"(I/O|입출력).{0,30}(바운드|bound)"
                r"|네트워크\s*요청|파일\s*읽기|DB\s*조회|디스크\s*읽기",
                text, re.I))
        ),
        "rubric_desc": "블로킹/논블로킹(동의어 포함) 구분 + I/O-bound 상황(동의어 포함) 언급",
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
