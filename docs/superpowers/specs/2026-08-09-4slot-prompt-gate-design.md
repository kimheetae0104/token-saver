# 4슬롯 강제 게이트 — 설계 스펙 (2026-08-09)

## 목적
`hooks/intent_gate.py`(UserPromptSubmit)는 모호한 착수형 요청을 감지해 "💡 착수 전 확인:
..." 넛지를 어시스턴트 컨텍스트에 주입하지만, 이건 **넛지일 뿐 강제가 아니다** — Claude가
그 줄을 무시하고 바로 도구 호출로 들어가도 아무것도 막지 않는다. CLAUDE.md 자체에 "hook이
잡은 애매한 요청조차 echo 없이 넘어가는 사례가 실측돼(예: 초단문 지시) 상시 echo로 강화"라는
정정 이력이 남아 있을 만큼, 넛지만으로는 실전에서 새는 경우가 이미 확인됐다. 목표: 모호하다고
판단된 턴의 **첫 도구 호출을 실제로 막아**, Claude가 무언가 말을 하고 나서야 작업을 시작하게
만든다.

## 범위 밖(의도적, 이번 spec 대상 아님)
이번 요청은 원래 5개 서브프로젝트(4슬롯 강제 / 라우팅 사다리·모델선정 도구 / 프로젝트
파일 읽기·쓰기 관리 / 사용자 대상 절감 안내 / 기타 발굴 기능)를 함께 요청했으나, 브레인스토밍
과정에서 사용자 확인 하에 **이 spec은 4슬롯 강제만** 다룬다. 나머지 4개는 각각 별도 spec으로
분리 — 지금 단계에서는 우선순위·의존관계 문서화만 하고 설계는 하지 않는다(아래 "다른
서브프로젝트" 참고).

## 핵심 제약 (설계를 좌우한 실측 사실)
PreToolUse 훅은 그 턴에서 Claude가 지금까지 낸 텍스트를 payload로 받지 못한다(payload는
`tool_name`·`tool_input` 등 도구 호출 자체에 관한 정보뿐). 이 repo의 유일한 선례인
`hooks/read_guard.py`도 `transcript_path`를 참조하지 않고 **자체 상태파일**만으로 동작한다 —
"이번 메시지의 앞선 텍스트 블록이 PreToolUse 시점에 transcript에 이미 반영돼 있는지"는 이
repo에서 검증된 적이 없다. 검증 없이 이 가정에 기대어 설계하면, 가정이 틀릴 경우 게이트가
상시 무통과이거나 상시 차단이 되는 조용한 실패로 이어진다.

그래서 이 spec은 **transcript 접근이 전혀 필요 없는 설계**를 기본으로 채택한다.

## 설계: 1회성 트립 게이트
```
UserPromptSubmit                         PreToolUse (전체 도구 매칭)
┌──────────────────┐                     ┌─────────────────────┐
│ intent_gate.py    │  상태파일 기록 →    │ prompt_gate.py (신규) │
│ (기존 로직 + 상태  │  {flagged, tripped} │  상태 읽기            │
│  파일 쓰기 추가)   │                     │  → allow/deny 결정     │
└──────────────────┘                     └─────────────────────┘
```

1. **`hooks/intent_gate.py`(기존 파일 수정)**: 기존 휴리스틱으로 4슬롯 중 빠진 게 있는지
   판단하는 로직은 그대로 두고, 매 턴 끝에 상태파일에 `{"flagged": bool, "tripped": false}`를
   쓰는 부수효과를 추가한다(모호하지 않은 턴이면 `flagged: false`로 덮어써 이전 턴 상태가
   새 턴에 새지 않게 함 — 매 UserPromptSubmit마다 파일을 새로 씀).
2. **`hooks/prompt_gate.py`(신규 PreToolUse 훅, matcher: 전체 도구)**:
   - 상태파일이 없거나 `flagged: false` → 그냥 허용.
   - `flagged: true` and `tripped: false` → **deny**(`permissionDecision: "deny"`,
     사유: "모호한 요청으로 판단됨 — 먼저 의도·제약·성공기준·위임경계 파싱본을 텍스트로
     밝히고 나서 다시 시도하세요") + 상태파일을 `tripped: true`로 갱신.
   - `flagged: true` and `tripped: true`(이미 한 번 막았음) → 허용. 같은 턴 안의 후속 도구
     호출은 더 막지 않는다(1턴당 딱 1번).
   - 이 훅은 **텍스트 내용을 검증하지 않는다** — "존재하는지"조차 transcript로 확인하지
     않는다(위 핵심 제약 때문에 불가능하다고 판단). 대신 "denied 사유를 본 Claude가 재시도
     전에 뭔가 말할 수밖에 없는 구조"로 같은 효과를 유도한다. deny 메시지 자체가 도구
     result로 Claude에게 보이므로, 자연스러운 다음 행동은 그 사유에 응답하는 텍스트를 내는
     것 — 강제하진 못해도 구조적으로 유도한다.

## 상태파일
`hooks/read_guard.py`의 `state_dir()`와 동일한 경로 컨벤션(`CLAUDE_PLUGIN_DATA` 있으면 그
아래, 없으면 공유 tempdir 폴백) 재사용, 별도 서브디렉터리:
```
${CLAUDE_PLUGIN_DATA:-tempdir}/prompt_gate/<session_id>.json
{"flagged": true, "tripped": false}
```
세션당 파일 하나, 매 턴 덮어씀(append 아님 — 과거 턴 상태가 쌓이지 않아야 함).

## DIY 설정·킬스위치
기존 `config_store.py` 컨벤션 그대로 확장:
```python
DEFAULTS = {
    ...,
    "prompt_gate": {"disabled": False},
}
```
`_TYPES`에 새 키 추가 불필요(disabled만 있음, 이미 bool 타입 등록됨). 이 한 줄 추가만으로
`token_saver_config_get/set/reset` MCP 툴이 `prompt_gate`도 자동으로 다뤄준다(hook_name을
매개변수로 받는 범용 구현이라 하드코딩된 분기 없음 — 기존 3개 hook과 동일 패턴).
env kill switch `TOKEN_SAVER_DISABLE_PROMPT_GATE=1`이 config보다 항상 우선(기존 컨벤션).

## 에러 처리 (fail-open 원칙, 기존 hooks와 동일)
- `session_id` 없음, 상태파일 파싱 실패, 디렉터리 접근 실패 → 무조건 허용(도구 호출을
  절대 깨뜨리지 않는다).
- 같은 메시지 안에서 여러 도구 호출이 병렬로 발화하는 경우(레이스 컨디션): 상태파일 쓰기가
  파일 I/O 하나뿐이라 완전한 원자성은 없음 — 최악의 경우 같은 턴에 deny가 2번 나갈 수 있음.
  기능은 깨지지 않고(둘 다 재시도하면 통과), 다음 이터레이션에서 파일 락으로 강화할 수
  있다는 점만 문서화하고 이번 spec에서는 손대지 않음(YAGNI — 실측된 문제 아님).

## 테스트
`tests/test_prompt_gate.py`(신규) — `read_guard`/`grep_trim` 테스트와 같은 서브프로세스
호출 패턴(stdlib assert, PASS/FAIL 러너):
- flagged=false 상태 → 허용.
- flagged=true, tripped=false → 최초 호출 deny, 상태파일이 tripped=true로 갱신됨.
- flagged=true, tripped=true → 허용(2번째 호출부터).
- 상태파일 없음 → 허용(fail-open).
- 상태파일 손상(JSON 파싱 실패) → 허용(fail-open).
- 킬스위치(`TOKEN_SAVER_DISABLE_PROMPT_GATE=1`) → flagged=true라도 무조건 허용.
- config.json `prompt_gate.disabled=true` → 무조건 허용.
- env 킬스위치가 config보다 우선.

`tests/test_intent_gate.py`(기존 파일 확장) — 상태파일 쓰기 회귀:
- 모호한 프롬프트 → 상태파일에 `flagged: true, tripped: false` 기록됨.
- 명확한 프롬프트(4슬롯 다 충족) → `flagged: false` 기록됨(이전 턴이 true였어도 덮어씀).

## 배포 체크리스트 (이 세션에서 배운 교훈 반영)
구현 완료 후 `hooks/hooks.json`에 `PreToolUse` 항목 추가(matcher를 "전체 도구"로 지정하는
정확한 문법은 구현 단계에서 Claude Code 공식 문서로 확인 — 지금 이 repo의 기존 matcher는
`"Read"`/`"Grep"`/`"Bash"`처럼 특정 도구명만 써봤고 "전체" 매칭 사례가 없어 실측 필요).
`plugin.json` 버전 범프 → `git push` → `claude plugin marketplace update token-saver-tools`
→ `claude plugin update token-saver@token-saver-tools` → 캐시 디렉터리에서 `prompt_gate.py`
실제 존재 확인 → 재시작 안내까지 마쳐야 "완료"(13차에서 확립된 배포 체인, 생략 금지).

## 향후 과제 (이번 spec 범위 밖, feasibility 확인되면 후속 spec)
PreToolUse 시점에 `transcript_path`로 이번 메시지의 선행 텍스트 블록이 실제로 읽히는지
확인하는 작은 진단 스파이크(신규 진단 훅으로 payload 전체를 파일에 덤프해 실제 발화 1회로
확인)를 향후 별도로 돌려볼 수 있다. 만약 가능하다고 확인되면, "1회 트립 후 무조건 허용"을
"트립 후에도 텍스트 블록이 실제로 있는지 확인"으로 강화하는 걸 다음 spec으로 제안한다.
지금은 **미착수**로 남긴다(가정 검증 없이 만들지 않는다는 것 자체가 이번 spec의 핵심 결정).

## 다른 서브프로젝트 (spec 미작성, 우선순위만 기록)
사용자가 함께 요청한 나머지 4개 — 순서는 다음 세션에서 다시 확인:
1. 라우팅 사다리·모델선정·에이전트 활용 도구 — 세션이 CLAUDE.md 사다리 규칙(Haiku→검증→
   승격)을 실제로 따르는지 측정/안내하는 도구. `measure.py`의 기존 cache-thrash 프록시와
   연결 가능성 있음.
2. 프로젝트 파일 읽기·쓰기 관리 — `read_guard.py`가 이미 다루는 Read 중복 차단 외에,
   Write/Edit 쪽 낭비 패턴(있다면)을 조사부터 시작해야 함 — 아직 실측된 낭비 패턴 없음.
3. 사용자 대상 절감 안내 확장 — 이번 세션에서 이미 추가한 페이스 라인(`_pace_line()`) 외에
   추가로 필요한 안내가 무엇인지부터 사용자와 다시 확인 필요.
4. 기타 발굴 기능 — 열린 상태, 구체적 후보 없음.

각각 "구독제 주간/5시간 사용량 실사용 기준 50% 이상 절감"이라는 전체 목표에 기여하는 정도는
실사용 데이터가 쌓여야 판단 가능 — 이 목표 자체는 **가설**이며, 이번 세션 안에서 검증 완료를
선언할 수 없다(종단 실측 필요, `measure.py --all`로 세션 누적 시 추적).
