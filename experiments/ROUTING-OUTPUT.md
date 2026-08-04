# Phase 5 (실험) — 난이도 기반 모델 라우팅 + 출력 통제

> 실험/설계 단계. 핵심 함정과 현실적 구현형을 정리한다. 검증은 PROTOCOL.md의 A/B로.

## 모델 라우팅

**함정**: 세션 중 `/model`·`/effort` 전환 = 캐시 무효화 → 매 턴 메인 전환은 역효과.
→ **위임 라우팅**: 메인 모델은 세션당 1회 고정, 작업별 티어는 **서브에이전트 위임**(격리 캐시, 자기 모델 지정).

**라우터**
- ① 휴리스틱(공짜): 패턴 신호로 trivial/medium/hard.
  - trivial: rename·format·boilerplate·대량 편집 / medium: 표준 코딩·단일 파일 / hard: 아키텍처·교차파일·난해 디버깅.
- ② 애매하면 Haiku 분류기: `{tier, needs_reasoning, scope, confidence}`.
- 정확한 토큰량 예측(불신) 대신 coarse 티어.

**라우팅 테이블**: trivial→Haiku(thinking off) / medium→Sonnet(medium) / hard→Opus(high).

**오분류 방어(비대칭 오류)**: under-route가 더 위험(나쁜 결과→rework) → 불확실하면 상향 +
**실패시 상향 사다리**(값싼 티어 → 검증 오라클 → 실패 시 상위 티어). 검증 루프와 결합.

**granularity**: 서브에이전트 cold 캐시 → trivial은 하나로 배치(item당 1개 금지).

**불확실**: 메인 루프 모델의 네이티브 턴별 자동 전환 지원 여부 → 구현 전 검증(hook은 "권장"까지).
오늘 구현형 = 서브에이전트 티어 위임 + 오케스트레이터 결정.

**측정**: `measure.py` 행위자별 분해 → 라우팅 ROI = (전부-Opus 추정 − 실제 혼합). 품질은 오라클로 고정.

## 출력 통제 (라우팅=추론예산, 출력통제=답변예산 — 같은 다이얼)

- 간결 강제(서론·맺음말·preamble/postamble 제거), 구조/포맷(JSON·불릿·**diff-only**),
  정지 조건("끝나면 멈춤, 다음단계·한일요약 금지"), thinking/effort 예산(`MAX_THINKING_TOKENS`), 티어별 max_tokens 캡.
- **경계**: 태스크 난이도별 하한 추론 budget 유지(과삭제 시 정확도 최대 ~28%↓). 최종 답 짧게, 필요 추론 확보.

## 실증 근거 (PROTOCOL 실험 1)
같은 정답에서 통독+장황(baseline) 47,972 tok vs grep+간결(optimized) 33,930 tok = **−29.3%, 3.2× 빠름**.
출력 통제(간결)와 탐색 통제(grep-first)가 실제로 토큰을 줄이면서 품질을 유지함을 보임.
