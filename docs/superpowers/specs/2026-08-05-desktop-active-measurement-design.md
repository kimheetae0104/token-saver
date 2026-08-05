# Desktop Code 탭 능동 계측 복원 — 설계 스펙 (2026-08-05)

## 목적
Claude Desktop 앱의 **Code 탭**(실제 Claude Code 엔진, stream-json server/API 모드)은
hooks가 원천 발화하지 않는다([desktop/desktop#22138](https://github.com/desktop/desktop/issues/22138),
closed as not planned — Anthropic 의도적 미지원). 이 때문에 `measure.py --check`(매 턴 효율 줄),
`session_autopsy.sh`(세션 종료 부검), `capture_failures`(실패 사례 수집)가 전부 침묵한다.
목표: **hooks 없이도** 이 세 기능을 Desktop Code 탭에서 best-effort로 복원하고, "모든 프로젝트에서"
동작하도록 **플러그인 설치로 전역 적용**되게 한다(현재 CLAUDE.md 서술 규칙은 이 repo 전용).

## 사전 검증 (실측, 2026-08-05)
- Desktop Code 탭이 project-scoped `.mcp.json` stdio 서버를 실제로 spawn·호출하는지 확인
  필요 → 무의존성 손수 구현 프로브(`experiments/desktop_mcp_probe/probe_server.py`)로
  실측. 사용자가 Desktop Code 탭에서 직접 연결·호출 확인(**연결됨** — 사용자 1차 관찰,
  raw JSON 페이로드는 미채집. 구현 단계에서 재확인해 기록으로 남길 것).
- hooks·커스텀 stdio MCP 둘 다 Cowork(다른 제품, 착각 방지)에서는 closed-as-duplicate로
  막혀 있음([#63360](https://github.com/anthropics/claude-code/issues/63360),
  [#48909](https://github.com/anthropics/claude-code/issues/48909)) — 이 스펙은 Cowork가 아니라
  **Desktop Code 탭**(=Claude Code 엔진, MCP는 살아있고 hooks만 막힘) 대상임을 명확히 함.

## 왜 Skill+MCP 분리 (AI-YAGNI)
- `intent_gate.py`/`habit_coaching.py`(연결어 과다·4슬롯·방향전환 등)는 **텍스트 패턴 규칙**이라
  이미 이 repo CLAUDE.md에 "Hook 미지원 환경 자가 점검"으로 이식되어 있음 — MCP 불필요,
  **전역 Skill로 일반화만 하면 끝**(추가 비용 0, 모델이 컨텍스트에서 직접 자가적용).
- `measure.py --check`/`--autopsy`/`--capture-failures`는 **실제 트랜스크립트 파싱·숫자 계산**이
  필요해 텍스트 규칙으로 흉내 불가 → 이 셋만 MCP 서버 툴로 노출.

## 컴포넌트
```
skills/token-saver/SKILL.md   ← 전역 Skill (신규)
.mcp.json                     ← 플러그인 루트, mcpServers 등록 (신규, 공식 지원 확인:
                                 code.claude.com/docs/en/plugins-reference "MCP servers")
mcp/server.py                 ← MCP 서버 본체 (신규)
measure.py                    ← latest_session() 일반화 (기존 파일 수정)
```

### 1. `skills/token-saver/SKILL.md`
- CLAUDE.md "Hook 미지원 환경 자가 점검" 5규칙을 프로젝트 무관하게 일반화해 이식.
- 매 턴 지시(자기감지형, CLI 중복 호출 방지):
  - 시스템 컨텍스트에 이미 `⟢ 턴...` 형식 줄이 보이면(hook 정상 발화 중 = CLI/IDE) 아무것도
    안 함.
  - 안 보이면(Desktop Code 탭) `token_saver_check` MCP 툴을 호출해 같은 정보를 얻어 한 줄로
    노출.
  - 대화가 마무리되는 신호(사용자의 마무리 인사·"여기까지"·"수고했어" 류)를 감지하면
    `token_saver_autopsy` 호출, 요약 한 줄만 보여주고 그 외 언급 안 함(session_autopsy.sh와
    동일하게 조용한 백그라운드 계측 철학 유지).

### 2. `mcp/server.py` — 무의존성 손수 구현(stdio, JSON-RPC), 프로브와 같은 패턴
툴 3개, 전부 `measure.py`의 기존 함수를 **import해 재사용**(로직 재구현 금지):

| 툴 | 대응 hook | 로직 |
|---|---|---|
| `token_saver_check` | UserPromptSubmit | `aggregate`+`proxies`+`efficiency_score` → `do_check()`와 동일 포맷 문자열 |
| `token_saver_autopsy` | Stop (부검부) | `autopsy(tot, px, per_turn)` → 낭비 신호 요약 |
| `token_saver_autopsy` (같은 호출 내 side effect) | Stop (수집부) | `capture_failures()` → `production_failures.jsonl` append |

트랜스크립트 경로: hook처럼 stdin으로 안 넘어오므로 자체 탐색.
`project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()` →
`~/.claude/projects/<sanitize(project_dir)>/*.jsonl` 중 최신.

`CLAUDE_PLUGIN_DATA`(capture_failures 영속 디렉터리)도 env로 전달될 것으로 가정하되
**미검증** — 구현 단계에서 프로브로 먼저 확인(측정 없이 가정 금지 원칙).

### 3. `measure.py` 수정
- `TRANSCRIPT_DIR`(현재 `__file__` 위치 기준 — 이 repo 단독 실행 전제라 플러그인으로
  다른 프로젝트에 설치되면 틀린 경로를 가리킴)를 함수화:
  `def transcript_dir(project_dir=None)`, 기본값 `os.getcwd()`. `latest_session()`이 이걸 사용.
  기존 hook 경로(항상 stdin에 transcript_path 옴)는 영향 없음 — fallback 경로만 고쳐짐.
- 이 리팩터는 MCP 유무와 무관하게 이미 존재하던 일반화 버그 수정이라 별도 가치 있음.

## 에러 처리
트랜스크립트 없음/파싱 실패 → 빈 결과 조용히 반환(기존 `do_check()`/`do_capture_failures()`와
동일 철학 — 침묵, 예외로 세션 안 끊음).

## 검증
1. 로컬 스모크: probe와 같은 방식으로 stdin에 initialize/tools-list/tools-call 파이프.
2. `claude plugin validate` 통과.
3. **실사용 실측(핵심 오라클)**: Desktop Code 탭에서 실제 세션 진행 → 세션 후 그 트랜스크립트를
   CLI `measure.py`로 재분석 → (a) 세 툴이 실제 호출됐는지, (b) MCP 호출 자체의 토큰 오버헤드가
   얼마인지(사용자 가설 "매 턴 호출이 절감에도 도움" 자체를 여기서 실측 검증) →
   `experiments/PROTOCOL.md`에 실험으로 기록. 가정이 아니라 결과로 결론.

## 경계·주의 (정직)
- MCP 호출은 hook과 달리 실제 모델 행동(tool_use 왕복)이 들어가는 비용 — hook의 "공짜에 가까운
  주입"과 동급 비용이 아님. 3번 검증에서 실측 전까지는 "복원됐다"고만 하고 "공짜로 복원됐다"고는
  말하지 않는다.
- `probe_server.py`는 스파이크 산출물 — 이 스펙 구현 후 정리 대상(코드는 폐기, 검증 결과만
  `experiments/PROTOCOL.md`에 남김).
- 이 repo 자체에서 개발 중엔 로컬 CLAUDE.md 규칙 + 신규 전역 Skill이 동시에 로드돼 텍스트 규칙이
  중복될 수 있음(해롭진 않지만 낭비) — CLAUDE.md의 해당 섹션을 신규 Skill 참조로 축약하는 정리는
  구현 단계 후속 작업.
