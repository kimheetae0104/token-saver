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

- `statusLine`(measure.py 기반 토큰/비용 표시줄)은 플러그인 `settings.json`이 지원하는 필드가 아니라서 자동 적용되지 않습니다. 쓰려면 설치 후 직접 프로젝트 `.claude/settings.json`에 추가하세요(`hooks/hooks.json` 옆의 예시 구조 참고, `.claude/settings.json`이 원본).
- **Claude Desktop 앱에서는 hooks가 실행되지 않습니다**(2026-08-05 실사용 확인 — Desktop 앱은 Claude Code를 stream-json server/API 모드로 구동해 interactive CLI 모드 전용인 hooks가 발화하지 않음, [claude-code#63360](https://github.com/anthropics/claude-code/issues/63360) 미해결). 즉 `habit_coaching.py`·`intent_gate.py`·`session_autopsy.sh`·`--statusline`·`--check` 전부 Desktop에서는 침묵합니다. `CLAUDE.md`의 서술형 규칙(라우팅·출력통제 등)은 Claude가 프로젝트 컨텍스트를 읽는 한 여전히 적용되는 것으로 보이나, 능동적 계측·코칭·`production_failures.jsonl` 수집은 CLI/IDE 확장(터미널·VS Code·JetBrains — 전부 동일 엔진 사용, hooks 정상 발화)에서만 동작합니다.

## 라이선스

[MIT](LICENSE)
