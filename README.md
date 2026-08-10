# token-saver

Claude Code용 토큰 효율화 플러그인. 목표는 토큰 최소화가 아니라 **토큰당 아웃풋 극대화** — 자세한 철학은 [CLAUDE.md](CLAUDE.md), 수치 근거는 [experiments/PROTOCOL.md](experiments/PROTOCOL.md) 참고.

## 설치 전에 뭐가 달라지는지 보기

이 플러그인의 훅 대부분(재독 차단·트리머)은 무음으로 동작해서 설치해도 눈에 띄는 변화가
딱히 없습니다. 화면에서 직접 보이는 개입은 4슬롯 착수 게이트(아래 예시)와, `systemMessage`
필드로 전환된 낭비 습관 코칭·의도 확인 넛지·효율 경고입니다(2026-08-10, 실사용 검증 전 —
[알려진 제한사항](#알려진-제한사항) 참고). 아래는 4슬롯 게이트의 실제 동작 그대로의 예시입니다.

```
사용자: 더 강화시켜

Claude: (도구를 호출하려 하면 prompt_gate.py가 첫 호출을 막고 이렇게 응답합니다)
  진행하기 전에 확인이 필요해요 — 무엇을 할지, 지켜야 할 제약이 있는지, 뭐가 되면
  끝인지(범위가 넓다면 직접 할지 위임할지도) 먼저 간단히 설명한 다음 다시 시도해주세요.

Claude: 어떤 부분을 더 강화할지 짚어주시겠어요? 방금 다룬 read_guard.py의 임계값을
  말씀하시는 거라면, 어떤 조건을 더 엄격하게/느슨하게 할지 알려주시면 바로 진행하겠습니다.
```

같은 요청도 처음부터 대상·제약·완료 기준이 분명하면(예: "read_guard.py의
LARGE_FILE_LINES를 500에서 300으로 낮춰줘") 전혀 개입하지 않고 그대로 진행됩니다 — 이
훅은 **얼마나 구체적인지**만 보지, 요청의 옳고 그름을 판단하지 않습니다. 트립은 세션당
매 턴 최대 1회(같은 턴에서 도구 호출을 병렬로 여러 개 내도 정확히 1번만 개입 — 동시성
검증 근거는 `tests/test_prompt_gate.py`), 재시도는 즉시 허용됩니다.

## 상태: v0.3.6, 초기 단계

- **N=6~7 세션**으로 보정한 값입니다. 제3자 검증 없음(자체 측정만).
- `many_agents` 임계값은 outlier 세션 1건을 제외하고 정한 값이라 특히 불안정합니다.
- 실사용 실패 수집 파이프라인(`production_failures.jsonl`)이 141건을 축적했던 시점에 표본
  라벨링 결과 18/18(100%)이 위양성으로 확인됐습니다(`experiments/PROTOCOL.md` 실험13). 근본원인
  2건 — `capture_failures()`가 시스템 `<task-notification>` 알림을 사용자 발화로 오인(커밋
  `b3cb163`), `_similar_desc()`가 재검토 정형 문구를 유사도로 오판(커밋 `8ddf98f`) — **둘 다
  수정 완료(2026-08-09), 회귀테스트로 검증**. 단, 수정 전 축적된 기존 141건 로그 자체의
  재라벨링(재검증)은 아직 하지 않았으므로 그 로그를 그대로 재보정에 쓰기 전엔 새로 축적되는
  로그로 신뢰도를 다시 확인할 것.
- 벤더 주장 없이 실측만 기록합니다 — 근거 없는 절감률(예: "60~95% 절감")을 내세우지 않습니다. 이유는 [PROTOCOL.md](experiments/PROTOCOL.md)의 시장 비교 섹션 참고(Ponytail·RTK·Caveman 등 외부 도구의 벤더 주장 대비 JetBrains 독립 재측정 결과 요약 포함).
- 2026-08-09~10 결정론 훅 6개 전부(재독 차단·트리머 2종·설정 저장소·4슬롯 게이트)를 동시성·
  코퍼스 시나리오로 검증해 실버그 6건(원자성 부재로 인한 레이스 3건 — `prompt_gate.py`·
  `read_guard.py`·`config_store.py`, 트림 결과가 원본보다 커지는 역설 1건 — `grep_trim.py`/
  `bash_trim.py`, 초단문 커버리지 갭 1건 — `intent_gate.py`, 매니페스트 버전 드리프트 1건)을
  발견·수정, 회귀 테스트로 고정했습니다. `habit_coaching.py`(유일하게 전용 테스트가 없던 훅)도
  이번에 커버리지 추가. 전체 테스트 스위트 157/157 통과. 상세 시나리오·근거 로그는 커밋
  `b191f98`·`10ade10`·`e435599` 참고.

## 무엇을 하는가

### 항상 켜져 있는 결정론 훅 (LLM 호출 없음)

- **재독 차단**(`read_guard.py`, PreToolUse): 같은 세션에서 정확히 같은 범위를 다시 Read하거나,
  이미 읽은 더 넓은 범위의 부분집합을 재독하거나, 이미 본 대형 파일(기본 500줄↑)을 스코프 없이
  통째로 다시 읽으면 차단. 파일이 그 사이 바뀌었으면(mtime 변경) 항상 허용 — 수정 확인 재독은
  안 막음. 이 repo 최초로 실제 도구 호출을 deny할 수 있는 훅.
- **출력 트리머**(`grep_trim.py`/`bash_trim.py`, PostToolUse): Grep 매치(기본 100줄↑)·Bash 출력
  (기본 200줄↑)이 과도하면 상위+하위만 남기고 중간을 생략 — 전체 건수는 항상 명시해 정보 손실
  신호를 숨기지 않음.
- **4슬롯 착수 게이트**(`intent_gate.py` + `prompt_gate.py`): 모호한 착수형 요청(의도·제약·
  성공기준·위임경계 중 불명확한 게 있으면)에 확인 넛지를 주입하고, 초단문+대상 생략 조합처럼
  특히 애매한 경우엔 그 턴의 첫 도구 호출을 1회만 막아 Claude가 먼저 설명하고 나서 진행하게
  강제(1회성 트립 게이트). 병렬 도구 호출 아래에서도 원자적 클레임으로 정확히 1회만 트립.
- **낭비 습관 코칭**(`habit_coaching.py`, UserPromptSubmit): 연결어 과다·과거 회고+재확인 결합·
  방향전환·긴 배경설명 같은 채팅 습관 패턴을 감지해 한 줄 피드백. `systemMessage`로 사용자
  화면에 직접 표시됩니다(2026-08-10, 아래 "알려진 제한사항" 참고).
- **DIY 설정**(`config_store.py` + MCP `token_saver_config_*`): 위 훅들의 임계값·kill switch를
  훅 재배포 없이 조회·변경. env kill switch(`TOKEN_SAVER_DISABLE_*`)가 항상 최우선.

### 측정 · 라우팅

- **모델 티어 라우팅 사다리**: 기계적 작업은 Haiku 1차 시도 → 오라클(compile/test) 검증 → 실패 시만 상향. 실측: 오라클 있는 과제에서 Sonnet 직행 대비 3.09배 저렴, 사다리의 "실패 시 상향" 비용은 0(N=30 벤치마크에서 실패 0건, 실패율 상한 95% CI ~10%).
- **매 턴 효율 상태 주입**: 프롬프트 제출마다(`--check`) 누적 토큰·캐시 적중률·비용·효율 점수를 한 줄로 계산해 Claude 자신의 컨텍스트에 주입 — 컨텍스트 비대·캐시 적중 저하는 같은 줄에 경고 추가, 재독 차단·트리머의 절감 추정치와 4슬롯 게이트 개입 횟수도 같은 줄/리포트에 합산. 전체 줄은 여전히 Claude 컨텍스트 전용이지만, **경고(컨텍스트 비대·캐시 적중 저하 등)가 있을 때는 `systemMessage`로 사용자 화면에도 직접 표시됩니다**(2026-08-10, 아래 "알려진 제한사항" 참고 — 매 턴 전체 줄을 다 보여주면 스팸이라 경고만 선별). `statusLine` 수동 설정은 여전히 절감 추정치까지 포함한 완전한 한 줄을 상시로 보고 싶을 때 유효합니다.
- **낭비 탐지 부검**: read 스래싱, 컨텍스트 성장, 장황함, 캐시 적중률, 서브에이전트 과다호출, 위임 오버헤드를 세션 종료 시 자동 분석(`--autopsy`).
- **실사용 실패 수집**: Haiku 1차 실패(에스컬레이션·사용자 교정) 후보를 결정론적으로(LLM 미사용) 감지해 로그에 누적, 향후 재보정 근거로 사용. 141건 표본에서 발견된 18/18 위양성의 근본원인 2건은 수정 완료(실험13, 위 "상태" 참고) — 새로 쌓이는 로그로 신뢰도 재확인 예정.

## 설치

```
/plugin marketplace add kimheetae0104/token-saver
/plugin install token-saver@token-saver-tools
```

## 알려진 제한사항

- **(2026-08-10 검증 완료, 음성) `UserPromptSubmit` hook의 plain stdout은 사용자 화면에 뜨지
  않습니다** — 공식 문서(code.claude.com/docs/en/hooks, "Add context for Claude" 섹션)에
  "시스템 리마인더로 감싸져 Claude 컨텍스트에만 들어가고 어떤 인터페이스에서도 채팅
  메시지로 표시되지 않는다"고 명시돼 있고, 실사용 중 사용자가 직접 확인해 재발견했습니다
  (2026-08-08). 같은 공식 문서에 **`systemMessage`라는 별도 top-level 필드가 전체
  hook 이벤트 공통으로 존재하고, 이건 Claude 컨텍스트가 아니라 사용자 화면에 직접
  렌더링된다**고 명시돼 있어 `intent_gate.py`·`habit_coaching.py`·`measure.py --check`
  (경고가 있을 때만) 셋 다 이 필드로 전환했지만(2026-08-10), 실사용 세션에서 재확인한
  결과 **의도대로 렌더링되지 않았습니다** — hooks가 정상 발화한 턴(`UserPromptSubmit hook
  success` 시스템 알림으로 발화 자체를 직접 확인)에서 사용자가 "직후 화면에 코칭/게이트
  메시지가 뜨지 않았다"고 확인해줬습니다(VSCode 확장/Agent SDK 하네스 기준, 같은 날). 아래
  `statusLine`이 유일하게 **확인된** 가시 경로입니다. 다른 하네스(CLI, macOS Desktop Code
  탭)에서는 재확인되지 않았으니 이 결과의 일반화에는 주의하세요. "어시스턴트 자신의 상태
  상기만으로 실제 행동이 달라지는가"도 별개로 아직 실측되지 않은 미검증 가정입니다 — 후속
  과제.
- `statusLine`(measure.py 기반 토큰/비용 표시줄)은 Claude Code가 플러그인에 허용하는 필드가 아니라서(세션당 statusLine은 하나뿐이라 플러그인이 등록할 수 없음) 설치만으로는 뜨지 않습니다. 훅(`UserPromptSubmit`·`Stop`)은 설치 즉시 정상 동작하니 "설치가 안 된다"는 뜻이 아닙니다.
  쓰려면 설치 후 프로젝트(또는 `~/.claude/settings.json`)에 직접 추가하세요:
  ```json
  {
    "statusLine": {
      "type": "command",
      "command": "python3 \"$HOME/.claude/plugins/marketplaces/token-saver-tools/measure.py\" --statusline"
    }
  }
  ```
  (위 명령 그대로 위 `설치` 절 순서로 설치한 경우의 실제 경로입니다 — marketplace add 시 클론되는 위치는 `~/.claude/plugins/marketplaces/<marketplace-name>/`.)
- **Claude Desktop 앱 Code 탭 hooks 미발화는 Windows 한정 버그입니다(macOS는 정상 동작, 2026-08-06
  실측 정정)** — [desktop/desktop#22138](https://github.com/desktop/desktop/issues/22138)이 재현
  환경을 "Windows 11"로 명시했는데, 이 프로젝트가 처음엔 이를 Desktop 전체 문제로 과일반화했습니다.
  실사용 macOS Desktop Code 탭 세션의 실제 트랜스크립트를 열어보니 `UserPromptSubmit` hook이
  정상 발화해 `⟢` 효율 줄이 그대로 출력됐습니다(`experiments/PROTOCOL.md` 실험11). 그래도
  Windows Desktop Code 탭(원 이슈 재현 환경) 등 hooks가 실제로 막힌 환경을 위해 두 갈래
  best-effort 복원을 남겨둡니다: (1) 텍스트 코칭 규칙은 전역 Skill `token-saver:rules`로 이식돼
  MCP 없이도 모든 환경에 적용됩니다. (2) 실제 트랜스크립트 계산이 필요한 매 턴 효율 줄·세션
  부검·실패 사례 수집은 MCP 서버(`mcp/server.py`, `token_saver_check`/`token_saver_autopsy`
  툴)로 노출됩니다. **알려진 결함(완화 시도, 미검증)**: Skill의 "hooks 줄이 이미 보이면 MCP
  호출 생략" 자기감지 지시가 실전에서 안 지켜지는 사례가 실측됨(hooks 정상 발화 중에도 모델이
  MCP를 중복 호출 시도). 2026-08-09 `skills/rules/SKILL.md`에 "이번 턴에 `⟢` 줄이 실제로
  있는지"를 매 턴 명시적으로 자문하게 하는 번호 매긴 게이트로 지시를 강화했으나, 프롬프트
  준수 여부는 실사용 트랜스크립트로 재확인해야 확정 — 아직 안 함. 상세는 실험11 참고. 상세 설계:
  `docs/superpowers/specs/2026-08-05-desktop-active-measurement-design.md`,
  실측 결과: `experiments/PROTOCOL.md` 실험11.

## 라이선스

[MIT](LICENSE)
