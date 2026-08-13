# 다단계 파이프라인 소배치 통위임 차단 — 설계 스펙 (2026-08-13)

## 목적
CLAUDE.md는 "다단계 파이프라인(생성→판정→비용측정 등) 통위임 금지"를 규칙으로 적고,
실험10(오버헤드 포함 시 74.1%→11.5% 절감으로 축소)·실험17(N<20 소배치에서 baseline 대비
3.495배 손해)로 근거까지 실측해뒀다. 그런데 이 규칙은 지금 **Claude가 매번 기억해서
지키는 프롬프트 정책**일 뿐이다 — `hooks/ladder_gate.py`(Agent PreToolUse)는 "티어
컨설트했는지"·"추천 티어와 model이 일치하는지"만 강제하고, 정작 실측 손해가 난 이 패턴
자체는 걸러내지 않는다. 사람이 프롬프트를 정교하게 쓰든 평문으로 대충 쓰든, 위임 판단
자체가 결정론 코드로 걸리게 만드는 것이 목표 — Claude의 그때그때 판단이나 사용자의
프롬프트 숙련도에 기대지 않는다.

## 범위 밖(의도적)
- 평문 원문을 실제로 압축·치환하는 프롬프트 재작성 레이어 — 브레인스토밍에서 사용자가
  명시적으로 기각(LLM 호출 필요=AI-YAGNI 위반, 결정론 불가능).
- 사후 실측 기반 임계값 자동 튜닝 — 로그만 남기고 이번 spec에서는 손대지 않음(YAGNI,
  아래 "향후 과제").
- CLAUDE.md의 다른 미집행 규칙들(왕복 최소화의 병렬 호출, 출력 통제 등) — 이번 스펙은
  "다단계 파이프라인 소배치 통위임" 한 패턴만 다룬다.

## 핵심 제약
`ladder_gate.py`는 Agent 도구의 `tool_input.prompt`(자유 서술 텍스트) 하나만 보고 판단해야
한다 — 같은 턴에 다른 Agent 호출이 몇 개 더 나가는지(병렬 팬아웃 여부)는 훅 payload에서
알 수 없다(기존 파일의 실측 제약과 동일, `_extract_recommended_tier`의 필드 드리프트
문제와 같은 종류). 그래서 "하나의 서브에이전트에게 여러 단계를 한 번에 시키는 프롬프트인가"를
그 프롬프트 텍스트 자체의 신호로만 판단한다 — 진짜로 서브에이전트가 내부에서 여러 번
Bash를 호출할지는 사전에 알 수 없고(그건 사후 시점에야 확인 가능), 텍스트 신호를 근사치로
쓴다는 한계를 그대로 안고 간다(다른 게이트들과 동일한 오탐 감수 원칙).

## 설계: 정규식 휴리스틱 + 1회성 확인 (기존 티어 불일치 패턴 재사용)

`ladder_gate.py` 기본 모드(Agent PreToolUse, consulted 확인 이후)에 조건 분기 추가.
새 파일 없음.

```python
# 단계 카테고리 3종 — 서로 다른 카테고리 2개 이상 매치되면 "다단계 파이프라인 신호"
_GEN_RE     = re.compile(r"(생성|만들|작성)")
_JUDGE_RE   = re.compile(r"(판정|판단|평가|채점|검증)")
_MEASURE_RE = re.compile(r"(측정|계산|집계|비용)")

# 배치 크기: "20건"/"15개"/"30 items" 형태에서 숫자 추출. 못 찾으면 "불명"으로 취급(위험군).
_BATCH_SIZE_RE = re.compile(r"(\d+)\s*(건|개|case|items?)", re.IGNORECASE)
BATCH_SMALL_THRESHOLD = 20  # CLAUDE.md 사다리 규칙의 N<20 기준과 동일 값 재사용
```

판정 로직 (Agent PreToolUse, consulted 이후에 추가 삽입):
1. `tool_input.prompt`에서 위 3개 카테고리 중 몇 개가 매치되는지 센다. 2개 이상이면
   "다단계 신호".
2. `_BATCH_SIZE_RE`로 숫자를 찾는다. 못 찾거나 찾은 값이 `BATCH_SMALL_THRESHOLD` 미만이면
   "소배치 신호"(찾지 못한 경우도 소배치로 간주 — 근거: 브레인스토밍에서 합의, "배치
   불명시는 위험군 취급"이 실험17 반례를 놓치지 않는 쪽).
3. 둘 다 참이고, 이번 세션에서 아직 `pipeline_batch_acknowledged`가 안 됐으면 **1회
   deny**(기존 티어 불일치 확인과 동일 패턴 — `mismatch_acknowledged`를 본떠
   `pipeline_batch_acknowledged` 상태 키 추가) 하고 상태를 true로 갱신. 같은 턴에 재시도하면
   통과(같은 프롬프트로 재시도해도 통과 — 강제 변경은 못 시키지만 "의식적 재확인"은
   강제한다, 기존 게이트들과 동일한 설계 철학).
4. 티어 불일치 확인과 마찬가지로 `ladder_gate_events`에 실측 로그 남김
   (`event: "pipeline_batch_flagged"`, 다단계신호/소배치신호/acknowledged 여부) —
   `measure.py`가 나중에 "이 게이트가 실제로 몇 번 개입했는지" 집계할 수 있게.

deny 메시지:
```
"다단계 파이프라인(생성→판정→측정 등)을 서브에이전트 하나에 통위임하는 패턴으로
보이고 배치가 작아 보입니다(20건 미만 또는 배치 크기 불명) — 실험10·17 실측상
오버헤드가 절감분을 상쇄하거나 역전(최대 3.495배)합니다. 각 단계를 병렬 Agent
여러 콜로 쪼개거나, 배치가 20건 이상이면 그대로 다시 시도하세요(통과합니다)."
```

## 상태
기존 `ladder_gate.py` 세션 상태파일에 키 추가:
```json
{"consulted": true, "recommended_tier": "sonnet",
 "mismatch_acknowledged": false, "pipeline_batch_acknowledged": false}
```
`--reset`(UserPromptSubmit)이 매 턴 `pipeline_batch_acknowledged: false`로도 리셋 —
`consulted: false`와 함께 같은 딕셔너리에 씀(새 상태파일 종류 추가 아님).

## 에러 처리 (기존 원칙 그대로)
- `session_id` 없음, 상태파일 손상, 정규식 매치 중 예외 → 무조건 allow(fail-open).
- 킬스위치: 기존 `TOKEN_SAVER_DISABLE_LADDER_GATE=1`, `config.json`의
  `ladder_gate.disabled` 그대로 재사용(새 킬스위치 만들지 않음 — 같은 파일의 같은 게이트
  범주이므로 분리할 이유 없음).

## 성능검증 지표 채택 (문서만, 코드 변경 없음)
`measure.py --check`/`--statusline`이 이미 계산하는 **캐시절감 $**·**효율점수**를
"이 세션이 실제로 이득이었는가"의 공식 지표로 `docs/TOKEN-GUIDE.md`에 명문화한다(신규
로직 없음, 기존 계산을 공식 채택 선언만). 주간/5시간 구독 게이지는 작업량과 효율이
섞인 값이라 이 목적에 쓰지 않는다는 점도 함께 명시(이번 대화에서 사용자에게 설명한
내용을 문서화).

## 테스트
`tests/test_ladder_gate.py`(기존 파일 확장):
- 2개 이상 카테고리 매치 + 배치 언급 없음 → 최초 호출 deny, `pipeline_batch_acknowledged`
  기록.
- 2개 이상 카테고리 매치 + 배치 언급 없음 → 재시도(2번째 호출) 허용.
- 2개 이상 카테고리 매치 + "30건" 등 20 이상 배치 명시 → 최초부터 허용.
- 1개 카테고리만 매치(단일 단계) → 허용(다단계 신호 아님).
- "15건"처럼 20 미만 명시 → deny.
- 킬스위치/config disabled → 무조건 허용(기존 테스트 패턴 재사용).
- `--reset` 호출 시 `pipeline_batch_acknowledged`도 false로 초기화되는지 회귀.

## 배포 체크리스트
코드 변경이 기존 `hooks.json` 배선(`ladder_gate.py`, matcher: Agent)을 그대로 쓰므로
`hooks.json` 수정 불필요. `plugin.json` 버전 범프 → `git push` →
`claude plugin marketplace update token-saver-tools` →
`claude plugin update token-saver@token-saver-tools` → 재시작 안내(기존 배포 체인,
13차·26차에서 확립된 절차 그대로).

## 향후 과제 (범위 밖, feasibility 확인되면 후속 spec)
- 오탐률 실측 후 `BATCH_SMALL_THRESHOLD`·카테고리 매치 개수 기준 조정(지금은 근거:
  CLAUDE.md 기존 N<20 기준 재사용, 이 게이트 전용 실측치는 아직 없음).
- 서브에이전트가 실제로 내부에서 Bash를 몇 번 호출했는지 사후 대조해 이 게이트의
  정밀도(오탐/누락률)를 실측 — `ladder_gate_events` 로그가 쌓인 뒤 가능.

## Amendment (2026-08-13, 최종검토 반영)
최종 브랜치 코드리뷰에서 "다단계 신호"(`_has_pipeline_signal`, 2개 이상 카테고리
매치) 규칙이 CLAUDE.md 자신이 권장하는 "독립 검증 서브에이전트" 위임 패턴과
오탐 충돌함을 발견했다 — 예: `"이 PR diff를 리뷰하고 문제를 판정해서 보고서를
작성해줘"`는 생성/만들/작성 + 판정/판단/평가/채점/검증 두 카테고리에 매치되지만,
실제로는 단일 단계 작업이지 다단계 파이프라인이 아니다.

사용자 승인 하에 규칙을 강화: 카테고리 2개 이상 매치에 더해 **명시적 순서 마커**가
프롬프트에 있어야만 다단계 신호로 판정한다.

```python
_SEQUENCE_RE = re.compile(r"(뒤|다음|이후|그리고\s?나서|→)")
```

`_has_pipeline_signal`은 이제 `(카테고리 2개 이상 매치) AND _SEQUENCE_RE.search(prompt)`
둘 다 참일 때만 True. 회귀 테스트: `tests/test_ladder_gate.py`의
`test_verification_delegation_pattern_allows`,
`test_multi_category_without_sequence_marker_allows`.
