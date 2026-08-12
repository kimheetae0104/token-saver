# 로드맵 5위 — `many_agents` 판정에 근접중복 신호 추가 설계 (2026-08-12)

## 배경
HANDOFF.md 25차 세션이 `~/.claude/projects/.../*.jsonl` 90개 세션을 전수 스캔해
`many_agents`(현재 `THRESH["many_agents"]=12`, measure.py:80) 임계값을 넘는 신규 outlier
5건을 발견했다: `n_agent_spawns` 기준 19/19/41/24/22. 2026-08-04 3차 재보정 시점엔
outlier가 1건(30, 실험8 의도적 벤치마크로 제외)뿐이라 "outlier 1건에 의존" 문제로 재보정을
보류했는데, 이번엔 5건으로 늘어 그 문제는 해소됐다. 그러나 25차는 "이 5건이 정상적인
배치 위임 패턴(SDD 워크플로우 등)인지 진짜 과다 위임(낭비)인지 구분이 먼저"라고 판단을
보류했다 — 신호(숫자) 자체보다 이 구분 기준을 세우는 게 핵심 설계 작업이라는 것.

## 목적
`n_agent_spawns >= 12`라는 단일 카운트만으로 "과분해 가능"을 일괄 코칭하는 대신, 스폰된
각 서브에이전트의 `description`끼리 근접중복이 있는지를 함께 봐서 "정상적인 다중 독립
작업"과 "item당 1개씩 위임한 배치 위임 후보(CLAUDE.md가 이미 금지하는 패턴)"를 구분한다.

## 범위
- **포함**: `measure.py`의 `parse_session()`/`proxies()`/`autopsy()` 3개 함수 수정. 근접중복
  판정은 기존 `_similar_desc()`(2026-08-12 22~23차에 적대적 재검증까지 거친 함수) 재사용 —
  새 유사도 로직 없음.
- **제외**: `THRESH["many_agents"]=12` 자체의 재조정(이번 설계로 다루지 않음 — 아래 "왜
  임계값 자체는 안 건드리나" 참고), `_similar_desc()`의 0.7 자카드 컷 조정, 서브에이전트
  파일(`subagents/**/agent-*.jsonl`)이나 메타(`spawnDepth` 등) 읽기 — 실측으로 신뢰 불가
  확인됨(아래 "기각한 대안" 참고).

## 실측 근거
25차가 찾은 outlier 5개 세션 + 이번 세션 전신(694f2287)에서, 메인 트랜스크립트의 최상위
`Agent` tool_use `input.description`끼리 `_similar_desc()` 페어 비교:

| 세션 | spawns | 근접중복 있는 spawn 수 | 비율 | 실제 내용 |
|---|---|---|---|---|
| e796ed47 | 19 | 0 | 0% | 전부 서로 다른 설명 |
| d70ea518 | 19 | 0 | 0% | SDD Task1/2/3 implementer+reviewer(Task 번호로 구분됨) |
| c8016fa5 | 41 | 30 | 73% | "G1 without-reminder pilot" 등 문구가 그대로 반복 |
| df5c36a0 | 24 | 6 | 17% | "token-saver 프로젝트 기능/성능 조사" 동일 문구 7회 |
| 694f2287 | 22 | 6 | 50% | "Adversarial review of X" — 독립검증이라 병합 불가할 수 있는 패턴 |

근접중복 유무가 뚜렷한 낭비 사례(c8016fa5)와 정상 사례(e796ed47, d70ea518)를 갈랐다.
df5c36a0·694f2287은 애매하지만, 이 finding은 hard gate가 아니라 low/med severity
코칭이므로 일부 모호성은 감내 가능(아래 "리스크" 참고).

## 기각한 대안
- **Workflow 툴 사용 여부로 구분**: d70ea518은 `Workflow` 툴 없이(순수 재귀 `Agent` 체인)도
  근접중복 0%로 정상 패턴이고, e796ed47은 `Workflow`를 쓰고도 정상 패턴이라 상관관계 없음.
- **서브에이전트 메타 `spawnDepth`로 "메인 직접 위임 vs Workflow 내부 팬아웃" 구분**: 실측
  결과 `Workflow` 내부에서 스폰된 e796ed47의 156개 중첩 에이전트도 전부 `spawnDepth=1`로
  기록돼 "메인 세션 루트로부터의 거리"를 신뢰성 있게 나타내지 않았다(하네스 내부 동작 불명).
  디렉터리 중첩 구조도 세션마다 flat/nested가 달라 일관되지 않았다. 문서화되지 않은
  하네스 내부 신호에 의존하는 리스크가 커서 기각 — AI-YAGNI/오라클 없는 소표본 실측 금지
  원칙에 해당.

## 설계

### 1. `parse_session()` (measure.py:229)
`Agent` tool_use를 셀 때(`n_agent_spawns += tools.count("Agent")` 근처) 각 블록의
`input.get("description")`도 함께 수집한다.

```python
agent_descs = []
...
if name == "Agent":
    agent_descs.append(inp.get("description") or "")
...
n_agent_spawns += tools.count("Agent")
```

반환 dict에 `"agent_descs": agent_descs` 추가.

### 2. `proxies()` (measure.py:487)
`sess["agent_descs"]`에 대해 `_similar_desc()` O(n²) 페어 비교(실측 최대 41건 — 무시할
비용)로 다음을 계산해 px에 추가:
- `agent_dup_count`: 근접중복 상대가 하나 이상 있는 spawn 개수
- `agent_dup_examples`: 예시 중복 쌍 문구(최대 1~2개, 메시지용)

### 3. `autopsy()` (measure.py:587-590)
`many_agents` 분기를 둘로 나눈다:
- `agent_dup_count == 0`: **현재 문구 그대로**(변경 없음, severity `low`).
- `agent_dup_count >= 1`: 새 finding "과분해 의심(배치 위임 후보)", severity `med`,
  detail에 몇 건이 겹쳤는지 + 예시 문구 1개, tip "동일/유사 항목은 하나로 배치 위임
  (item당 1개 금지)".

### 왜 임계값 자체는 안 건드리나
`THRESH["many_agents"]=12`(트립 조건)와 `_similar_desc()`의 0.7 자카드 컷(중복 판정
기준) 둘 다 이미 실측으로 검증된 상수다. 이번 설계의 목적은 "트립된 이후 무엇을
보여줄지"를 구분 신호로 정교화하는 것이지, 트립 자체의 민감도를 바꾸는 게 아니다. 새
매직넘버를 추가하지 않는다.

## 리스크
- 694f2287류(정당한 독립 재검증을 반복 spawn하는 패턴)에서 `med`로 과대평가될 수 있음.
  hard gate가 아니라 low→med 코칭 조정이라 실사용 영향은 "리뷰 권장 문구 하나 더 뜨는"
  수준 — 감내 가능한 리스크로 판단.
- N=5(+1) 소표본 검증이라 일반화엔 한계 있음. 다만 이번 설계가 바꾸는 건 "숫자 임계값"이
  아니라 "이미 검증된 유사도 함수를 재사용해 메시지를 분기하는 로직"이라 소표본이어도
  안전하게 반영 가능(로직 자체는 결정론적이고, 22~23차에 이미 하드닝된 `_similar_desc`
  재사용).

## 테스트 계획 (구현 단계에서 TDD로 진행)
- `parse_session()`: `Agent` tool_use 여러 개(중복 description 포함) 있는 합성 세션 →
  `agent_descs` 정확히 수집되는지.
- `proxies()`: 중복 있는/없는 `agent_descs` 입력 → `agent_dup_count`/`agent_dup_examples`
  정확한지 (Task 번호로 구분되는 경우는 중복 아님 처리 포함 — 기존 `_similar_desc` 동작
  재확인 수준).
- `autopsy()`: `n_agent_spawns >= 12` + dup 있음/없음 두 케이스 각각 severity·메시지
  분기 확인.
