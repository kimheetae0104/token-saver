export const meta = {
  name: 'ladder-build',
  description: '검증된 싸게-걸고-오라클채점-실패시상향 사다리를 프론트엔드 빌드에 적용. 하네스 vs 단일-Opus 비용/품질 비교.',
  phases: [
    { title: 'Architect', detail: 'Opus: 디자인토큰 + 페이지 스펙 + 초기 티어' },
    { title: 'Copy', detail: 'Fable: UX 마이크로카피' },
    { title: 'Build', detail: 'Haiku 시작, audit P1 실패시 Opus 상향' },
    { title: 'Audit', detail: 'audit.mjs 결정론 채점(P1 게이트)' },
    { title: 'Baseline', detail: 'Opus 단독 3페이지 (비교군)' },
  ],
}

// 실험6(2026-08-04)을 실제로 돌렸을 때의 로컬 경로 그대로 — 실행 기록 보존용으로만
// 남겨둔다(Workflow 스크립트 샌드박스엔 fs/env 접근이 없어 경로를 동적으로 못 구함).
// 이 저장소는 그 이후 canonical root로 이전됐고, AUDIT도 이 repo 밖의 로컬 skill
// 파일을 참조해 다른 환경에서 애초에 그대로 재실행 불가 — 재현하려면 REPO/AUDIT를
// 실행 환경에 맞게 직접 바꿀 것.
const REPO = '<local-only: path this repo lived at during experiment 6>'
const AUDIT = '<local-only: path to the frontend-design-review skill audit.mjs>'
const TIERS = ['haiku', 'sonnet', 'opus']

const ARCH_SCHEMA = {
  type: 'object',
  properties: {
    designTokensCss: { type: 'string', description: '자기완결 CSS :root{} 토큰 블록 + 폰트/간격/라운드 규칙' },
    pages: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          filename: { type: 'string' },
          spec: { type: 'string', description: '이 페이지에 필요한 섹션·컴포넌트 구체 지시' },
          startTier: { type: 'string', enum: ['haiku', 'sonnet', 'opus'] },
        },
        required: ['name', 'filename', 'spec', 'startTier'],
      },
    },
  },
  required: ['designTokensCss', 'pages'],
}

const COPY_SCHEMA = {
  type: 'object',
  properties: { copy: { type: 'string', description: '페이지별 라벨링된 마이크로카피(헤드라인·CTA·상품명·폼 라벨 등)' } },
  required: ['copy'],
}

const AUDIT_SCHEMA = {
  type: 'object',
  properties: {
    p1: { type: 'integer' }, p2: { type: 'integer' }, p3: { type: 'integer' },
    pass: { type: 'boolean' },
    topViolations: { type: 'array', items: { type: 'string' } },
  },
  required: ['p1', 'p2', 'p3', 'pass', 'topViolations'],
}

const BRIEF = `브랜드 "무명(MUMYUNG)" 미니멀 라이프스타일 편집샵. 톤: 차분·절제·따뜻한 뉴트럴.
페이지 3개: (1) landing.html 히어로+특징3블록+상품그리드4+푸터, (2) products.html 필터칩바+상품카드8+페이지네이션, (3) signup.html 가입폼(이메일·비번·비번확인·약관체크·가입버튼)+로그인링크.`

const RULES = `필수(audit 게이트 직결): <meta name=viewport content="width=device-width,initial-scale=1">, <html lang="ko">, 대비 WCAG AA 본문4.5:1, 터치타깃 ≥24x24px, 인터랙티브 요소 cursor:pointer, 반응형(폭390 안깨짐). 순수 정적 HTML+inline CSS, 외부의존0.`

function auditPrompt(absFile) {
  return `다음 명령을 정확히 실행하라(경로 공백 주의, 작은따옴표 유지):
\`node '${AUDIT}' '${absFile}' --json --w 390\`
출력 JSON의 violations 배열을 severity 필드로 집계: P1/P2/P3 개수. topViolations=위반 rule 이름 상위 5개. pass = (P1==0). 숫자와 목록만 반환.`
}

function buildPrompt(page, tokensCss, copy, tier, feedback) {
  return `너는 프론트엔드 구현 워커(${tier})다. 아래 페이지의 완성된 정적 HTML 파일을 만들어 정확히 이 경로에 Write 해라:
${REPO}/harness/out/${page.filename}
브랜드/맥락: ${BRIEF}
이 페이지 스펙: ${page.spec}
디자인토큰(그대로 사용, 3페이지 일관성): ${tokensCss}
UX 카피(해당 페이지 것 사용): ${copy}
품질 규칙: ${RULES}
${feedback || ''}
자기완결 HTML 하나만. 완료하면 'done'만 반환.`
}

phase('Architect')
const arch = await agent(
  `너는 시니어 프론트엔드 아키텍트다. 아래 미니 쇼핑몰의 디자인시스템과 페이지별 구현 스펙을 설계하라.
${BRIEF}
품질 규칙: ${RULES}
요구: (1) designTokensCss = 자기완결 CSS :root{} 토큰(팔레트·타입스케일·간격·라운드) + 사용 규칙. 대비/터치타깃 규칙을 토큰 단계에서 만족시켜라.
(2) pages = 3개 각각 {name, filename(landing.html/products.html/signup.html), spec(섹션·컴포넌트 구체 지시), startTier}.
startTier 배정 규칙: 단순 페이지=haiku, 폼/상태 많은 복잡 페이지=sonnet. Opus는 상향 예비.`,
  { model: 'opus', phase: 'Architect', label: 'architect', schema: ARCH_SCHEMA }
)

phase('Copy')
const copyRes = await agent(
  `너는 브랜드 카피라이터다. 아래 쇼핑몰의 UX 마이크로카피를 써라(한국어, 절제된 미니멀 톤).
${BRIEF}
페이지별로 라벨을 붙여: landing(히어로 헤드라인+서브+CTA, 특징3 제목/설명, 상품4 이름/가격), products(필터칩 라벨, 상품8 이름/가격), signup(폼 라벨들, 가입버튼 문구, 안내문). 간결하게.`,
  { model: 'fable', phase: 'Copy', label: 'copy', schema: COPY_SCHEMA }
)

// 페이지별 사다리: startTier 빌드 → audit → P1>0면 Opus 상향(2단계 상한)
async function ladder(page) {
  const startIdx = TIERS.indexOf(page.startTier)
  const attempts = []
  let lastAudit = null
  const tierSeq = [page.startTier]
  if (page.startTier !== 'opus') tierSeq.push('opus') // 실패시 최상위로 직행(상한2)
  for (const tier of tierSeq) {
    const fb = lastAudit
      ? `이전 시도가 audit P1 위반 ${lastAudit.p1}개(${lastAudit.topViolations.join(', ')}). 반드시 P1을 0으로 고쳐라.`
      : ''
    const absFile = `${REPO}/harness/out/${page.filename}`
    await agent(buildPrompt(page, arch.designTokensCss, copyRes.copy, tier, fb),
      { model: tier, phase: 'Build', label: `build:${page.name}@${tier}` })
    lastAudit = await agent(auditPrompt(absFile),
      { model: 'haiku', phase: 'Audit', label: `audit:${page.name}@${tier}`, schema: AUDIT_SCHEMA })
    attempts.push({ tier, p1: lastAudit.p1, p2: lastAudit.p2, p3: lastAudit.p3 })
    if (lastAudit.pass) break
  }
  return { page: page.name, filename: page.filename, startTier: page.startTier,
    finalTier: attempts[attempts.length - 1].tier, attempts,
    p1: lastAudit.p1, p2: lastAudit.p2, p3: lastAudit.p3, pass: lastAudit.pass }
}

phase('Build')
const harnessResults = await parallel(arch.pages.map(p => () => ladder(p)))

// 베이스라인: Opus 단독으로 3페이지 전부 (동일 스펙), out/baseline/ 에
phase('Baseline')
await agent(
  `너는 Opus 단독 빌더다(비교 베이스라인). 아래 3페이지를 전부 직접 구현해 각각 정확히 이 경로들에 Write 하라:
${arch.pages.map(p => `${REPO}/harness/out/baseline/${p.filename}`).join('\n')}
${BRIEF}
페이지 스펙:\n${arch.pages.map(p => `- ${p.filename}: ${p.spec}`).join('\n')}
디자인토큰: ${arch.designTokensCss}
카피: ${copyRes.copy}
품질 규칙: ${RULES}
완료하면 'done'만 반환.`,
  { model: 'opus', phase: 'Baseline', label: 'baseline-build@opus' }
)
const baselineResults = await parallel(arch.pages.map(p => () =>
  agent(auditPrompt(`${REPO}/harness/out/baseline/${p.filename}`),
    { model: 'haiku', phase: 'Baseline', label: `audit:baseline:${p.name}`, schema: AUDIT_SCHEMA })
    .then(a => ({ page: p.name, p1: a.p1, p2: a.p2, p3: a.p3, pass: a.pass }))
))

return {
  harness: harnessResults.filter(Boolean),
  baseline: baselineResults.filter(Boolean),
  tierComposition: harnessResults.filter(Boolean).map(r => `${r.page}:${r.startTier}→${r.finalTier}(${r.pass ? 'pass' : 'FAIL'})`),
}
