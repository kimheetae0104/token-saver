# token-saver

Claude Code용 토큰 효율화 플러그인. 목표는 토큰 최소화가 아니라 **토큰당 아웃풋 극대화** — 자세한 철학은 [CLAUDE.md](CLAUDE.md), 수치 근거는 [experiments/PROTOCOL.md](experiments/PROTOCOL.md) 참고.

## 상태: v0.1.0, 초기 단계

- **N=6 세션**으로 보정한 값입니다. 제3자 검증 없음(자체 측정만).
- `many_agents` 임계값은 outlier 세션 1건을 제외하고 정한 값이라 특히 불안정합니다.
- 실사용 실패 사례 수집 파이프라인(`production_failures.jsonl`)은 이제 막 설치되어 **N=0**입니다.
- 벤더 주장 없이 실측만 기록합니다 — 근거 없는 절감률(예: "60~95% 절감")을 내세우지 않습니다. 이유는 [PROTOCOL.md](experiments/PROTOCOL.md)의 시장 비교 섹션 참고(Ponytail·RTK·Caveman 등 외부 도구의 벤더 주장 대비 JetBrains 독립 재측정 결과 요약 포함).

## 무엇을 하는가

- **모델 티어 라우팅 사다리**: 기계적 작업은 Haiku 1차 시도 → 오라클(compile/test) 검증 → 실패 시만 상향. 실측: 오라클 있는 과제에서 Sonnet 직행 대비 3.09배 저렴, 사다리의 "실패 시 상향" 비용은 0(N=30 벤치마크에서 실패 0건, 실패율 상한 95% CI ~10%).
- **낭비 탐지 코칭 훅**: read 스래싱, 컨텍스트 성장, 장황함, 캐시 적중률, 서브에이전트 과다호출을 세션 종료 시 자동 부검(`--autopsy`).
- **실사용 실패 수집**: Haiku 1차 실패(에스컬레이션·사용자 교정) 후보를 결정론적으로(LLM 미사용) 감지해 로그에 누적, 향후 재보정 근거로 사용.

## 설치

```
/plugin marketplace add kimheetae0104/token-saver
/plugin install token-saver@token-saver-tools
```

## 알려진 제한사항

- 플러그인으로 설치 시 `${CLAUDE_PLUGIN_ROOT}`는 업데이트마다 바뀌는 임시 경로입니다. 현재 `production_failures.jsonl`은 이 경로 기준(스크립트 자기 위치)에 씁니다 — 즉 **플러그인 업데이트 시 실패 로그가 유실될 수 있습니다.** 이 프로젝트 자체(로컬 개발용 `.claude/settings.json` 경유)는 프로젝트 디렉터리가 고정이라 영향 없지만, 마켓플레이스로 설치한 사용자는 영향받습니다. 다음 버전에서 `${CLAUDE_PLUGIN_DATA}`(업데이트 간 유지되는 경로)로 이전 예정.
- `statusLine`(measure.py 기반 토큰/비용 표시줄)은 플러그인 `settings.json`이 지원하는 필드가 아니라서 자동 적용되지 않습니다. 쓰려면 설치 후 직접 프로젝트 `.claude/settings.json`에 추가하세요(`hooks/hooks.json` 옆의 예시 구조 참고, `.claude/settings.json`이 원본).

## 라이선스

[MIT](LICENSE)
