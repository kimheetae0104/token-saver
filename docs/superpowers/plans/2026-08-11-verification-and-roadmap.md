# 검증 → 로드맵 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** token-saver의 테스트·문서·실사용 수치가 지금도 정확한지 검증하고 발견된 불일치를 고친 뒤, 그 결과를 근거로 다음 개발 아이디어를 우선순위와 함께 정리한다.

**Architecture:** 순차 5태스크. Task1(코드 건강성)→Task2(문서-코드 정합성, 서브에이전트 4개 병렬)→Task3(실사용 재측정)→Task4(HANDOFF 19차 기록)→Task5(아이디어 목록+우선순위). 각 태스크는 발견사항을 바로 그 자리에서 고치는 방식(별도 리포트 파일 신설 없음).

**Tech Stack:** Python(pytest), `measure.py`(자체 측정 엔진), `claude` CLI(`plugin validate`), Agent 툴(문서 감사용 서브에이전트 위임).

## Global Constraints
- 실측만 기록한다 — 표본이 부족해 결론이 안 바뀌면 "판단 보류"로 명시하고 억지로 수치를 만들지 않는다(스펙 성공기준).
- 문서와 코드가 불일치할 때 코드를 진실로 삼는다 — 문서는 코드를 서술하는 것이 원칙(스펙 리스크 항목).
- 오라클 없는 소표본은 실측 금지(AI-YAGNI, `CLAUDE.md` 위임 절).
- 서브에이전트 위임은 결론만 회수한다(격리 캐시) — 원문 전체를 부모 컨텍스트로 반입하지 않는다.
- 이번 범위는 `Workflow` 멀티에이전트 오케스트레이션을 쓰지 않는다(사용자가 명시 요청 안 함) — 일반 `Agent` 툴 위임까지만.
- Task5(Phase 2)의 산출물은 아이디어 목록+우선순위까지다. 실제 구현은 이 플랜의 범위 밖(다음 세션).
- 로컬 커밋까지만 한다. `git push`는 하지 않는다(사용자 글로벌 규칙 — push는 매번 별도 확인 필요).

---

### Task 1: 코드 건강성 검증 + 수정

**Files:**
- Modify: `README.md:18`(테스트 배지), `README.en.md:21`(테스트 배지) — 불일치 확인되면
- Test: `pytest` 전체 스위트 자체가 오라클(별도 테스트 파일 신설 없음)

**Interfaces:**
- Consumes: 없음(이 플랜의 첫 태스크)
- Produces: "코드 건강성 결과" 텍스트(통과 수, validate 결과, hooks 배선 상태) — Task 4가 HANDOFF 19차 항목 작성 시 이 결과를 인용

- [ ] **Step 1: 테스트 스위트 실행**

Run: `pytest -q` (저장소 루트에서)
Expected: 전부 PASS. 통과 개수를 기록해둔다(플랜 작성 시점 실측값: **207 passed** — 재실행해서 달라졌는지 확인).

- [ ] **Step 2: plugin manifest 검증**

Run: `claude plugin validate .`
Expected: `✔ Validation passed`

- [ ] **Step 3: hooks.json 배선 대조**

Run: `hooks/hooks.json`에 나열된 모든 `command` 안의 `${CLAUDE_PLUGIN_ROOT}/hooks/*.py`·`*.sh` 경로가 `hooks/` 디렉토리에 실제로 존재하는지 파일 하나씩 대조(`ls hooks/`와 비교). 참고로 `hooks/hooks.json` 안에는 `measure.py`도 1곳(UserPromptSubmit) 참조돼 있으니 그것도 저장소 루트에 존재하는지 같이 확인.
Expected: 전부 존재(플랜 작성 시점에 이미 1회 확인함 — 회귀 없는지만 재확인).

- [ ] **Step 4: 배지 수치 불일치 수정**

Step 1의 실제 통과 개수가 README 배지(`215%2F215`)와 다르면, `README.md:18`과 `README.en.md:21`의 `tests-215%2F215_passing`을 `tests-<실제개수>%2F<실제개수>_passing` 형식으로 정확히 맞춰 고친다. (Step1이 215로 나오면 이 스텝은 스킵.)

- [ ] **Step 5: 커밋**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver"
git add README.md README.en.md
git commit -m "fix(docs): 테스트 배지 수치를 실측(pytest) 결과에 맞춰 정정

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(Step1~3에서 배지 외 다른 회귀가 발견되면, 그 발견을 고치는 별도 커밋을 이 스텝 전에 추가하고 커밋 메시지에 원인을 명시한다.)

---

### Task 2: 문서-코드 정합성 감사 (서브에이전트 4개 병렬 위임)

**Files:**
- Read: `README.md`, `README.en.md`, `HANDOFF.md`, `docs/TOKEN-GUIDE.md`, `experiments/PROTOCOL.md`
- Modify: 위 문서들 중 불일치 확인된 파일(위임 결과에 따라 결정)

**Interfaces:**
- Consumes: 없음(Task1과 독립)
- Produces: "문서-코드 불일치 목록"(파일:줄 + 무엇이 다른지) — Task4가 인용

- [ ] **Step 1: 4개 서브에이전트를 한 메시지에 병렬로 위임**

Agent 1(README 묶음) 프롬프트:
```
저장소 루트: /Volumes/Extreme SSD/worktree/token-saver
README.md와 README.en.md를 읽고, 그 안의 구체적 수치·상태 주장(버전 배지, 테스트
배지, "N/N 통과", "현재 적용됨" 같은 상태 서술, many_agents=12 같은 임계값 언급,
"실험21/N=20" 같은 실험 인용)을 전부 뽑아라. 각 주장을 현재 코드로 직접 대조하라:
- 버전: .claude-plugin/plugin.json과 .claude-plugin/marketplace.json의 version 필드
- 테스트 배지: pytest -q 실행 결과의 통과 개수
- 임계값(many_agents 등): hooks/habit_coaching.py 또는 config_store.py DEFAULTS의
  실제 상수값
- "현재 적용됨"/"~에 반영됨" 서술: 언급된 파일(hooks/prompt_gate.py 등)을 열어 실제
  동작(메시지 포맷 등)이 서술과 일치하는지
불일치만 "파일:줄 — 문서 주장 vs 실제 코드값" 형식으로 반환하라. 일치하는 항목은
보고하지 마라. 불일치가 하나도 없으면 "불일치 없음"이라고만 답하라.
```

Agent 2(HANDOFF.md) 프롬프트:
```
저장소 루트: /Volumes/Extreme SSD/worktree/token-saver
HANDOFF.md를 읽어라. 각 "N차" 절 본문은 그 시점의 세션 기록(역사적 서술)이므로 절대
고치라고 제안하지 마라 — 오직 다음 두 가지만 검증하라:
1. 파일 경로·함수명·훅 이름 등 "지금도 존재해야 한다"고 암시하는 참조(예: 특정 hooks
   파일, tests 파일, config 키)가 실제로 지금도 존재하는가.
2. "열린 스레드"·"블록됨"이라고 표시된 항목들의 현재 상태 서술(예: many_agents 재보정
   대기, verify_fails 재검증 불가)이 지금 코드/데이터 상태와 여전히 맞는가 — 이미
   해소됐는데 블록됨으로 남아있는 게 있으면 지적하라.
불일치만 "줄 번호 — 무엇이 문제인지" 형식으로 반환하라. 없으면 "불일치 없음".
```

Agent 3(TOKEN-GUIDE.md) 프롬프트:
```
저장소 루트: /Volumes/Extreme SSD/worktree/token-saver
docs/TOKEN-GUIDE.md를 읽어라. 특히 §1(비용 구조 5분면 공식)과 §4(상황별 규칙)를
현재 코드와 대조하라:
- §1의 비용 공식(input×b + cc5m×1.25 + cc1h×2 + read×0.1 + out×5)이 measure.py의
  실제 가격 계산 함수와 일치하는지
- §4의 포맷 규칙(4슬롯류=Markdown, 대규모=HTML회피, 자유텍스트=JSON비권장)이
  hooks/prompt_gate.py의 실제 deny 메시지 포맷과 일치하는지
불일치만 "줄 번호 — 문서 서술 vs 코드 실제" 형식으로 반환하라. 없으면 "불일치 없음".
```

Agent 4(PROTOCOL.md) 프롬프트:
```
저장소 루트: /Volumes/Extreme SSD/worktree/token-saver
experiments/PROTOCOL.md를 읽어라. 실험 결과 중 다른 문서(README.md, README.en.md,
docs/TOKEN-GUIDE.md)가 "실험N" 형식으로 인용하는 항목들을 찾아, 인용하는 쪽의
숫자·결론이 PROTOCOL.md 원본 서술과 정확히 일치하는지 대조하라. 또한 PROTOCOL.md가
언급하는 파일 경로(예: experiments/ladder_real/attempts_n10, experiments/label_failures.py)가
실제로 저장소에 존재하는지도 확인하라.
불일치만 "무엇이 다른지" 형식으로 반환하라. 없으면 "불일치 없음".
```

- [ ] **Step 2: 결과 수합 및 판정**

4개 에이전트 결과를 모아, 각 불일치 항목에 대해 Global Constraints의 "코드가 진실"
원칙에 따라 문서를 코드에 맞춰 고칠지, 혹은 (드물게) 코드 쪽이 실수라 코드를 고칠지
판정한다.

- [ ] **Step 3: 발견된 불일치 수정**

Step 2 판정에 따라 해당 문서(또는 코드) 파일을 직접 Edit로 고친다. HANDOFF.md는
Step1의 Agent 2 프롬프트가 명시한 대로 역사적 본문은 건드리지 않고, "열린 스레드"
상태 표기만 갱신 대상이 될 수 있다.

- [ ] **Step 4: 커밋**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver"
git add -A
git commit -m "fix(docs): 문서-코드 정합성 감사에서 발견된 불일치 정정

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(불일치가 하나도 없었다면 이 태스크는 커밋 없이 "불일치 없음" 결과만 Task4로 넘긴다.)

---

### Task 3: 실사용 효과 재측정

**Files:**
- Read: `measure.py` 출력, `experiments/production_failures.jsonl`
- Modify: 수치 갱신이 필요하면 `README.md`, `HANDOFF.md`의 해당 부분

**Interfaces:**
- Consumes: 없음(Task1·2와 독립적으로 실행 가능하나 순서상 뒤에 옴)
- Produces: "실사용 재측정 결과" 텍스트(변경 없음 포함) — Task4·5가 인용

- [ ] **Step 1: 세션 간 추세 재실행**

Run: `python3 measure.py --all` (저장소 루트에서)
결과를 살펴 최근(18차 이후) 세션들의 효율·에스컬레이션 패턴이 README가 인용하는
결론과 계속 부합하는지 확인.

- [ ] **Step 2: production_failures.jsonl 성장 확인**

Run: `wc -l experiments/production_failures.jsonl`
README.md:81은 "141건"을 인용한다. 플랜 작성 시점 실측값은 **142줄**이었다 — 재실행
시점 값과 비교해 얼마나 늘었는지 확인하고, 새로 추가된 줄들이 실험13에서 이미 수정된
근본원인 2건과 같은 패턴인지, 아니면 새 유형의 위양성/위음성인지 마지막 몇 줄을
`tail -5 experiments/production_failures.jsonl`로 열어 직접 확인한다.

- [ ] **Step 3: ladder_gate 실사용 로그 확인**

Run: `python3 measure.py --autopsy`
`ladder_gate_summary_for_session` 계열 함수가 리포트에 추천/실제 티어 일치 데이터를
포함하면, README §"측정과 검증"이 인용하는 일치율 수치와 대조한다. 로그가 없거나
표본이 여전히 한 자릿수면 "표본 부족, 판단 보류 유지"로 결론짓고 수치를 바꾸지 않는다.

- [ ] **Step 4: 변경 필요 시 수치 갱신**

Step1~3에서 실제로 결론이 바뀌는 수치가 발견되면(예: production_failures 건수, 위양성
비율) `README.md`의 해당 줄을 Edit로 고친다. 바뀐 게 없으면 이 스텝은 스킵하고 Task4에
"판단 보류/변경 없음"으로만 기록한다.

- [ ] **Step 5: 커밋 (변경이 있을 때만)**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver"
git add README.md
git commit -m "docs(readme): 실사용 재측정 결과로 수치 갱신

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: HANDOFF.md 19차 세션 항목 작성

**Files:**
- Modify: `HANDOFF.md` (기존 "## 재개 방법" 절 바로 앞에 새 절 삽입 — 18차 절과 동일한
  삽입 위치 패턴)

**Interfaces:**
- Consumes: Task1의 "코드 건강성 결과", Task2의 "불일치 목록", Task3의 "재측정 결과"
- Produces: HANDOFF.md에 반영된 19차 세션 기록 — Task5가 "열린 스레드" 갱신 시 이 절을
  참조

- [ ] **Step 1: 19차 절 작성**

`## 재개 방법` 직전에 아래 형식으로 새 절을 추가한다(18차 절의 문체·밀도를 따름 —
사실만, 근거 수치 포함, 과장 없이). 세 문단 각각 Task1/2/3의 **실제 실행 결과를 그대로**
채운다 — 아래는 Task1 문단의 실제 작성 예시(플랜 작성 시점에 이미 확인된 실측값을
그대로 사용한 것)이니 이 밀도·형식을 Task2·Task3 문단에도 그대로 적용한다:

```markdown
## 검증 스레드 — 코드건강성·문서정합성·실사용재측정 (2026-08-11, 19차)
`pytest -q` 재실행 결과 <N>개 전부 PASS(README/README.en 배지 215/215는 실제론
<N>이었음 — 정정), `claude plugin validate .` 통과, hooks.json 9개 배선 전부 실제
파일 존재 확인.

서브에이전트 4개(README 묶음/HANDOFF/TOKEN-GUIDE/PROTOCOL) 병렬 감사 결과 <발견
개수>건 불일치 — <파일:줄 — 무엇이 다른지, 어떻게 고쳤는지를 항목별로>. (0건이면
"불일치 없음, 4개 문서 전부 코드와 합치"라고 명시)

production_failures.jsonl <N>줄(README 인용치 141에서 <증감>), 새로 추가된 줄은
<기존 근본원인 2건과 동일 패턴 / 새 유형 — 어느 쪽인지>. ladder_gate 실사용
추천/실제 티어 일치율은 <계산 가능했으면 수치, 아니면 "표본 <N>건으로 여전히 판단
보류">.
```

`<...>` 안은 반드시 실제 실행 결과 값으로 치환한다 — 빈 채로 두거나 "추후 확인" 같은
말로 남기면 이 스텝은 완료된 것이 아니다.

- [ ] **Step 2: 커밋**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver"
git add HANDOFF.md
git commit -m "docs(handoff): 19차 세션 기록 — 코드건강성·문서정합성·실사용재측정 결과

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: 아이디어 목록 + 우선순위 (Phase 2 산출물)

**Files:**
- Modify: `docs/superpowers/specs/2026-08-11-verification-and-roadmap-design.md`(하단에
  "## Phase 2 결과 — 아이디어 우선순위" 절 추가)
- Modify: `HANDOFF.md`("## 열린 스레드" 절을 이 표 기준으로 갱신)

**Interfaces:**
- Consumes: Task1~4의 모든 산출물(특히 Task2의 불일치 목록, Task3의 판단보류 항목)
- Produces: 우선순위 표 — 다음 세션이 그대로 착수 지점으로 사용

- [ ] **Step 1: 소싱 3갈래에서 후보 수집**

1) Task1~3 실행 중 실제로 드러난 갭(회귀, 불일치, 판단보류 항목)을 나열.
2) `HANDOFF.md`의 기존 "열린 스레드"/블록 항목(verify_fails 재검증, many_agents 재보정,
   병렬 haiku 겹침)을 다시 훑어 Task3 재측정으로 상태가 바뀌었는지 확인.
3) 코드에 아직 없는 신규 아이디어를 최소 3개 이상 브레인스토밍(예: Desktop/Windows
   hooks 격차 완화, MCP 툴 확장, 라우팅 신호 추가) — 전부 "가설" 딱지를 붙인다.

- [ ] **Step 2: 우선순위 표 작성**

각 후보를 아래 표 형식으로 정리하고, 가치/비용 비율 기준으로 정렬한다. AI-YAGNI 또는
"오라클 없는 소표본 실측 금지" 원칙에 위배되는 항목은 표 하단 "제외" 섹션으로 옮기고
제외 사유를 1줄로 남긴다.

```markdown
## Phase 2 결과 — 아이디어 우선순위 (2026-08-11)

| 순위 | 항목 | 설명 | 가치 | 비용 | 블로커 | 소스 |
|---|---|---|---|---|---|---|
| 1 | ... | ... | ... | ... | ... | 1/2/3 |

### 제외
- 항목명 — 제외 사유
```

- [ ] **Step 3: 문서 반영**

Step2의 표를
`docs/superpowers/specs/2026-08-11-verification-and-roadmap-design.md` 맨 아래에
추가하고, `HANDOFF.md`의 "## 열린 스레드" 절 내용을 이 표를 기준으로 다시 쓴다(순위
1~2위 정도를 "다음에 고를 것"으로 남기고, 해소된 기존 항목은 취소선 처리하는 기존
HANDOFF 관행을 따른다).

- [ ] **Step 4: 커밋**

```bash
cd "/Volumes/Extreme SSD/worktree/token-saver"
git add docs/superpowers/specs/2026-08-11-verification-and-roadmap-design.md HANDOFF.md
git commit -m "docs(roadmap): Phase 2 — 개발 아이디어 우선순위 목록 작성

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
