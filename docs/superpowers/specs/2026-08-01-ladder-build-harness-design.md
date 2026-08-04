# ladder-build 하네스 — 설계 스펙 (2026-08-01)

## 목적
실험 2~5에서 검증한 **"싸게 걸고 → 결정론 오라클로 채점 → 실패시 상향"** 사다리를
프론트엔드 빌드 오케스트레이션으로 구현. 결과물 = 재사용 하네스(Workflow 스크립트) +
단일-Opus 대비 토큰/비용 절감 + 품질 유지 실측 증거. (사이트는 테스트 시나리오일 뿐.)

## 왜 Workflow 위에 (AI-YAGNI)
Claude Code Workflow가 이미 모델 티어 fan-out·검증·상향을 결정론적으로 제공 →
밑바닥 오케스트레이터 재발명 금지. 하네스 = Workflow 스크립트 한 개로 상각.

## 모델 배치 (검증된 사다리)
| 역할 | 모델 | 일 |
|---|---|---|
| 아키텍트 | Opus | 디자인토큰 + 페이지 스펙 + 초기 티어 배정 |
| UX 카피 | Fable | 히어로·CTA·상품문구 (코드 사다리 밖, Fable 강점만) |
| 워커 | Haiku(기본)→Opus(상향) | 페이지 HTML/CSS 구현 |
| 통합 | Opus | 최종 일관성 점검 |

## 흐름
brief → [Opus 아키텍트] 토큰+3스펙 + [Fable] 카피 → 각 페이지 pipeline:
build@startTier → audit.mjs 채점 → P1==0? 통과 : rebuild@Opus(위반 피드백) → audit
→ 결과 집계 → 베이스라인(Opus 단독 3페이지) 빌드+audit → measure 비교.

## 검증 게이트 (결정론)
`node <스킬>/references/audit.mjs <file> --json` → violations[].severity 집계.
게이트 = **P1(치명) 위반 0**. LLM 판정 아님. 채점은 값싼 Haiku 에이전트가 실행·파싱.
(오라클 실측 확인됨: headless 렌더, viewport-missing 등 P1 검출, --json 구조화 출력.)

## 측정 (존재 이유)
베이스라인 = Opus 단독 3페이지. 비교축: 총비용 · audit P1/P2/P3 · 티어 구성.
성공 = 하네스가 더 싸면서 품질(P1) ≥ 베이스라인. 실패해도 정직 기록(실험 6).

## 산출물
- `harness/ladder_build.wf.js` — Workflow 스크립트(하네스 본체)
- `harness/brief.md` — 3페이지 쇼핑몰 brief
- `harness/out/*.html`(하네스) · `harness/out/baseline/*.html`(베이스라인)
- `experiments/PROTOCOL.md` 실험 6 — 실측

## 경계·주의 (정직)
- 사다리 상향은 2단계 상한(start→Opus)으로 에이전트 수 bound(~11 typical, ≤16 worst). medium 가이드 내.
- Fable 코드 제외 = 능력 한계 반영. 3페이지 = 메커니즘 입증용(완성 쇼핑몰 아님).
- 오라클은 P1~P3 시각/접근성 규칙 한정 — 기능(가입 로직) 정확성은 범위 밖(정적 프론트).
