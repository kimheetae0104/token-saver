# token-saver

Claude Code용 토큰 효율화 플러그인. 목표는 토큰 최소화가 아니라 **토큰당 아웃풋 극대화** — 자세한 철학은 [CLAUDE.md](CLAUDE.md), 수치 근거는 [experiments/PROTOCOL.md](experiments/PROTOCOL.md) 참고.

## 상태: v0.1.0, 초기 단계

- **N=6 세션**으로 보정한 값입니다. 제3자 검증 없음(자체 측정만).
- `many_agents` 임계값은 outlier 세션 1건을 제외하고 정한 값이라 특히 불안정합니다.
- 실사용 실패 사례 수집 파이프라인(`production_failures.jsonl`)은 이제 막 설치되어 **N=0**입니다.
- 벤더 주장 없이 실측만 기록합니다 — 근거 없는 절감률(예: "60~95% 절감")을 내세우지 않습니다. 이유는 [PROTOCOL.md](experiments/PROTOCOL.md)의 시장 비교 섹션 참고(Ponytail·RTK·Caveman 등 외부 도구의 벤더 주장 대비 JetBrains 독립 재측정 결과 요약 포함).

## 무엇을 하는가

- **모델 티어 라우팅 사다리**: 기계적 작업은 Haiku 1차 시도 → 오라클(compile/test) 검증 → 실패 시만 상향. 실측: 오라클 있는 과제에서 Sonnet 직행 대비 3.09배 저렴, 사다리의 "실패 시 상향" 비용은 0(N=30 벤치마크에서 실패 0건, 실패율 상한 95% CI ~10%).
- **매 턴 실시간 효율 표시줄**: 프롬프트 제출마다(`--check`) 누적 토큰·캐시 적중률·비용·효율 점수를 한 줄로 표시 — statusLine 수동 설정 없이도 무설정으로 매 턴 체감 가능. 컨텍스트 비대·캐시 적중 저하는 같은 줄에 경고 추가.
- **낭비 탐지 코칭 훅**: read 스래싱, 컨텍스트 성장, 장황함, 캐시 적중률, 서브에이전트 과다호출, 위임 오버헤드를 세션 종료 시 자동 부검(`--autopsy`).
- **실사용 실패 수집**: Haiku 1차 실패(에스컬레이션·사용자 교정) 후보를 결정론적으로(LLM 미사용) 감지해 로그에 누적, 향후 재보정 근거로 사용.

## 설치

```
/plugin marketplace add kimheetae0104/token-saver
/plugin install token-saver@token-saver-tools
```

## 알려진 제한사항

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
  툴)로 노출됩니다. **알려진 결함**: Skill의 "hooks 줄이 이미 보이면 MCP 호출 생략" 자기감지
  지시가 실전에서 안 지켜지는 사례가 실측됨(hooks 정상 발화 중에도 모델이 MCP를 중복 호출
  시도) — 후속 개선 필요, 상세는 실험11 참고. 상세 설계:
  `docs/superpowers/specs/2026-08-05-desktop-active-measurement-design.md`,
  실측 결과: `experiments/PROTOCOL.md` 실험11.

## 라이선스

[MIT](LICENSE)
