# 세션 핸드오프 — 새 세션 시작용 (증류본)

> 이 파일은 긴 이전 세션(~300k 토큰)을 한 장으로 **증류**한 것이다. 전체 대화를 복사하지 말 것 —
> 그러면 sunk-cost 컨텍스트가 그대로 재생돼 무거워진다. 새 세션은 이 폴더의 `CLAUDE.md`를 자동 로드하므로,
> 여기엔 파일에 없는 것(맥락·결정·열린 스레드)만 담았다.

## 이 프로젝트
Claude Code **토큰 세이버 툴킷**. 북극성: 토큰 최소화가 아니라 **토큰당 아웃풋 극대화**
("절약 vs 품질"은 가짜 트레이드오프 — 노이즈만 깎으면 싸지고 동시에 좋아짐). 계정=구독(Max).

## 이미 완성·검증된 것 (읽으면 컨텍스트 복원)
- `CLAUDE.md` — 작업 강제 규칙(자동 로드, 42줄)
- `docs/TOKEN-GUIDE.md` — 상세 근거·수치·"줄여도 되는 것 vs 안 되는 것" 경계표
- `measure.py` — 측정·부검 엔진(8개 모드, 검증됨). main + task 트랜스크립트 파싱, 모델별 단가 자동
- `statusline.sh`, `hooks/`, `.claude/settings.json` — 실시간 표시 + 능동 자동화(경고·부검)
- `experiments/PROTOCOL.md` — 3개 A/B 실험 **실측 결과**
- `experiments/ROUTING-OUTPUT.md` — 라우팅·출력통제 설계
- 원 계획서: `~/.claude/plans/effervescent-enchanting-quokka.md`(전체 설계·리서치 근거)

## 실증 결과 (전부 실측, 지어낸 값 0)
1. grep+간결 vs 통독+장황: **토큰 −29%, 3.2× 빠름**, 정답 동일
2. Haiku vs Opus 기계적 과제: **비용 7.2× 저렴**, 25/25 동일
3. Haiku vs Opus 미묘한 버그: **비용 7.6× 저렴**, 둘 다 정확 → Haiku 실패 경계는 예상보다 높음(가설 반증)
4. (실험4) Haiku vs Opus 생성형 계산기 구현+복합함정: 둘 다 25/25, Haiku ~6.8× 저렴 → 경계 또 미검출
5. **(실험5) 외적 타당성 — 프로젝트 유형 일반화**: TS·Go·대형Python 3종 A/B(grep vs 통독), 모델고정.
   전 유형 **품질 무손실**(정답 100%), 절감은 **파일 크기 비례**(대형 −24.6%↔소형 −3.5%, optimized는 ~48k
   고정오버헤드 바닥으로 수렴). 장황 baseline은 답 세다 자가정정하는 흔들림 → 여분토큰이 품질 안 삼.
   → "어떤 프로젝트든 grep-first+간결은 손해 없고, 클수록 이득" 실증. 원 −29%가 우연 아님(대형서 재현).
6. **(실험6) 계층형 하네스**(`harness/ladder_build.wf.js`, Workflow): Opus설계→Fable카피→[싸게빌드→
   audit.mjs P1게이트→실패시상향]→Opus베이스라인. 미니쇼핑몰 3페이지. 12에이전트 실측.
   **가설 반증**: 하네스 $2.60 vs 베이스라인 $1.60 (**1.6× 더 비쌈**). 단 분해하면: 빌드 라우팅은 −40%
   성공($0.84 vs $1.40)+품질 우세(P2 랜딩2<6). **오케스트레이션 고정비**(architect$0.63+**fable카피$0.99**
   +audit$0.14)가 절감을 삼킴. 3페이지론 상각 안 됨 → 실험5 스케일교훈 재확인. 손익분기 ≈8~10페이지 추정.
   교정안: 카피 인라인化·아키텍트 조건부·audit배치·사다리는 대규모 반복에만. 사이트는 `harness/out/`.

## 핵심 확정 사실 (코드에 이미 반영)
- 비용 5분면: `input×b + cc5m×1.25 + cc1h×2 + read×0.1 + out×5`(모델당 base 단가 하나면 됨)
- 캐시 무효화 트리거: `/model`·`/effort`·`/fast`·MCP 연결/해제·`/compact`·도구정의 변경·버전업 첫턴
- 구독=자동 1h TTL → 긴 세션 유지 유리, 새 세션 남발은 cold write 손해
- 측정 2층: 라이브 프록시(정답 불필요) vs 실험 OckScore(태스크당 토큰!)

## 🔧 갭 감사 (2026-08-03) — 검증됐으나 운영규칙 미이식. **다음 세션 최우선 편집.**
> 실험 1~6 결과가 experiments/에만 있고 CLAUDE.md엔 절반만 이식됨. grep으로 확인한 진짜 갭 4개 + 편집 스펙:
>
> **갭1 — 4슬롯 intent: 구현 0%.** hooks/엔 없음(context_warn·session_autopsy뿐). 규칙에도 없음.
>   → 편집: CLAUDE.md에 규칙 추가 "요청 착수 전 4슬롯 확보(의도·제약·성공기준·위임경계), 애매하면 파싱본 echo 후 확인."
>   선택: `hooks/intent_gate.sh`(결정론 휴리스틱: 만들/구현/리팩터+짧음+성공기준 단어 없음 → 리마인더 주입, 사소하면 침묵).
> **갭2 — effort/thinking 예산: 가장 저평가된 레버.** TOKEN-GUIDE:63에 반 줄뿐, CLAUDE.md엔 없음.
>   핵심 미기재: **thinking 토큰=output 단가(5×)** → 기계적 작업에 effort high면 5× 낭비(실험2 관측).
>   → 편집: CLAUDE.md 위임/라우팅에 "effort도 라우팅: 기계적=low, 어려운 추론만 high. thinking=output가격이라 절감 큼." TOKEN-GUIDE에 근거 확장.
> **갭3 — 구조화 출력(schema) 강제: 미문서화.** 실험 전부 schema 사용했으나 규칙 0건.
>   → 편집: CLAUDE.md 출력통제에 "구조적 답이 필요하면 schema/형식 강제 → 산문 파싱·재시도 왕복 제거."
> **갭4 — CLAUDE.md:15 반증된 정적티어 잔존.** `기계적=Haiku…어려운=Opus`를 사다리로 교체:
>   "라우팅=사다리: 값싼 오라클 있는 일은 Haiku로 걸고→검증→실패시 상향. 오라클 없고 애매·고위험이면 처음부터 상위."
> 소소: 방금 편집한 파일 재읽기 금지 명문화 / 초대형 repo 인덱싱 패턴(grep 한계).

## 열린 스레드 (다음 할 것 — 우선순위 순)
1. ~~Haiku 진짜 실패 경계 찾기~~ **해결(실험7, 2026-08-04)**: 경계=직관≠실제 평가순서 의미론
   (튜플언패킹 LHS 등). Haiku 0%↔Sonnet 100% 구배 확인. 프롬프트 강화로 100% 복원 가능.
   추가로 **실험8**: 검증기구(테스트·lint·schema) 있는 실무 과제 3종은 Haiku 1차 3/3 통과,
   Sonnet 대비 3.09배 저렴 — 사다리 실전 검증 완료. hook 3종(`intent_gate.py`·`habit_coaching.py`·
   `measure.py --check`) `.claude/settings.json`에 배선 완료·작동 확인.
2. ~~THRESH·BASE_IN 튜닝~~ **완료(2026-08-04)**: BASE_IN은 claude-api 스킬로 공식가 재확인 — 이미 정확
   (변경 없음). THRESH는 실사용 세션 5개(turns 15~231) 실측 기반 재보정: `ctx_growth` 1.50→2.00,
   `verbosity` 4000→3000, `cache_hit_low` 0.50→0.85, `many_agents` 5→7(상시발화 신호 제거).
   `read_thrash`·`correction`·`sunk_input`은 실측이 기존값을 이미 뒷받침해 유지. N=5로 작음 — 세션
   누적되면 재검토(`measure.py`의 THRESH 주석에 근거 명시).
3. ~~habit_coaching.py 정확도 개선~~ **완료(2026-08-04)**: 방향전환("대신에·차라리·처음부터 다시" 등)
   패턴 추가. 겸사겸사 기존 패턴6의 `str.split(regex)` 버그(정규식이 리터럴로 취급돼 무의미했음)도 수정.
4. ~~measure.py 확장~~ **완료(2026-08-04)**: `discover_task_files()`로 `<uuid>/subagents/**/agent-*.jsonl`
   자동 discovery(중첩 workflows 포함), `actor_breakdown()`으로 행위자(agentType)별 토큰·비용 집계.
   경로 수동 지정 불필요 — `print_report`에 자동 통합. 실측 검증: 서브에이전트 70개 세션에서
   메인 $18.23 vs 전체(메인+서브) $31.61 — 이전엔 안 보이던 진짜 총비용 노출.
5. ~~실험8 표본 확대~~ **완료(2026-08-04)**: N=3(과제당 1회)→30(과제당 10회, 독립 콜드스타트 Haiku).
   **30/30 PASS, 실패 0건.** rule-of-three로 진짜 실패율 상한 재추정: N=3의 사실상 무의미한 상한(~100%)이
   N=30에서 **~10%**로 좁혀짐. 실측 비용 $0.5788(30회, 전부 Haiku, `measure.py` 자동discovery로 확인) —
   시도당 ~$0.019. 에스컬레이션 비용은 여전히 미관측(실패 0건이라 발생 자체가 없음) — 이는 결함이 아니라
   결과이며, 다음 단계는 합성 표본 추가 확대보다 **프로덕션 실사용 실패 사례 수집**이 낫다는 결론.
   상세: `experiments/PROTOCOL.md` 실험8 addendum, 코드: `experiments/ladder_real/{attempts_n10,grade_n10.py}`.

## 열린 스레드 — 다음 세션 후보 (2026-08-04 갱신, 2건 모두 완료)
1. ~~프로덕션 실패 사례 수집~~ **완료(2026-08-04)**: `measure.py`에 `capture_failures()` 추가,
   `--capture-failures` CLI로 노출, `hooks/session_autopsy.sh`(Stop hook)에 배선 완료.
   감지 신호 2종(둘 다 결정론, LLM 미사용): (a) **escalation_pair** — Haiku 서브에이전트 뒤에
   설명이 유사한(Jaccard≥0.5, 모델명 등 불용어 제거) 상위모델 서브에이전트가 시간상 뒤따름,
   (b) **user_correction_follow** — Haiku 서브에이전트 직후 사용자 메시지에 기존 `CORRECTION_MARKERS`
   또는 신규 `PIVOT_MARKERS`(방향전환) 매치. 후보는 `experiments/production_failures.jsonl`에
   append-only 누적, `dedup_key`(toolUseId 기반)로 Stop 훅 재발화에도 중복 없음(idempotent 확인됨).
   **실전 검증 중 발견한 함정**: 실험8 세션(167e7f96)에 재실행했더니 A/B 비교용 "Baseline: Sonnet …"
   서브에이전트 3건을 오탐(설명 유사 + 시간상 후행 — 구조적으로 진짜 에스컬레이션과 구분 불가,
   meta.json엔 워크플로우 여부를 나타내는 필드가 없음 확인). `description`에 "baseline" 포함 시
   양쪽 다 제외하는 필터 추가로 해결, 재실행 시 0건(정상) 확인 — 합성/실험 세션이 오염원이 될 수
   있다는 걸 실측으로 확인했으므로, 이 로그를 검토할 때 "baseline" 라벨 없는 다른 실험 산출물이
   섞여 있을 가능성은 열어둘 것.
   현재 로그는 비어있음(실사용 실패 사례가 아직 0건 — 정상, 앞으로 쌓일 것).
2. ~~THRESH 재검토~~ **완료(2026-08-04, 2차)**: N=5→6(세션 1개 추가, turns 84~231)으로 재보정.
   `read_thrash`·`correction`·`verbosity`·`cache_hit_low`·`sunk_input`은 실측이 기존값을 여전히
   뒷받침해 유지. 2개 변경:
   - `ctx_growth` 2.00→**3.00**: 1차 재보정 때 이미 설계 오류였음을 이번에 발견 — 당시 관측
     중앙값(2.17)이 임계값(2.00)보다 높았다(임계값<중앙값이면 정의상 세션 과반 상시발화).
     N=6 관측 최대(2.67) 바로 위로 재설정, 실측상 0/6 발화(상시발화 제거 확인).
   - `many_agents` 7→**12**: 신규 세션(`d3b71176`, n_agents=30)은 실험8 표본확대 세션 —
     PROTOCOL.md에 "배치 위임 금지 원칙 예외"로 명시된 의도적 벤치마크라 정상 위임 분포를
     대표하지 않음(`production_failures.jsonl`의 "baseline" 필터와 같은 종류의 오염원 판단).
     이 outlier를 제외한 건강 상한(10) 바로 위로 설정 — 재조정 전 7은 이미 8/8/10에
     상시발화 중이었음(1차 재보정으로도 안 고쳐졌던 문제, 이번에 처음 확인). 재보정 후
     outlier 1건만 정확히 발화(4/6→1/6).
   검증: 전 세션(`TRANSCRIPT_DIR` glob) 순회하며 `measure.autopsy(tot, px, per_turn)` 직접 호출 →
   재보정 후 발화 빈도 `ctx_growth` 4/6→0/6, `many_agents` 4/6→1/6(outlier만), 나머지 항목 불변 확인.
   N=6 여전히 작음 — 특히 `many_agents`는 outlier 1건에 의존하는 재조정이라 세션 누적 시 재검토.

## 열린 스레드 — 다음 세션 후보 (2026-08-04 3차 갱신)
위 2개 전부 완료. 새로 발견된 후속 스레드:
1. **many_agents 재검토**: 이번 값(12)은 outlier 1건(30-spawn) 제외 후 건강 상한(10)만으로 정한 것 —
   건강한 위임이 실제로 8~10 근처에서 더 자주 나올지, 아니면 12 근처의 새 정상 사례가 나올지는
   세션이 몇 개 더 쌓여야 판단 가능.

## 시장 비교 + 플러그인 배포 (2026-08-04 4차, 완료)
- **경쟁 도구 실측 비교**: Ponytail·RTK·Caveman·Headroom·CBM·context-mode 조사(WebSearch).
  핵심 발견 — JetBrains(Denis Shiryaev)가 독립 재측정한 3개 중 벤더 주장 생존은 **Ponytail 하나뿐**
  (주장 47~77% vs 실측 −10.3%, p=0.004). **RTK는 오히려 비용 +7.6%**(허수 counterfactual로 절감
  카운터 조작 확인), Caveman은 주장 65% vs 실측 −8.5~9%. Headroom·CBM·context-mode는 독립 재현
  자체가 없음(벤더 수치만). "코드버닝"은 검색해도 실체 없음(사용자가 지칭한 이름 확인 안 됨).
  → 이 프로젝트가 RTK가 실패한 바로 그 함정(캐시 재읽기를 원가로 셈, 존재 안 하는 원본과 비교)을
  애초에 `measure.py`의 5-facet 실제과금 단가 설계로 피해감을 재확인. 상세는 세션 대화 로그 참고
  (별도 문서화 안 함 — 일회성 조사).
- **플러그인 패키징 + GitHub 배포**: `git init`(main 브랜치) → `.claude-plugin/plugin.json` +
  `marketplace.json`(source `"./"`, 자기 자신을 마켓플레이스로 등록) → `hooks/hooks.json`
  (`.claude/settings.json`의 훅을 `${CLAUDE_PLUGIN_ROOT}` 경로로 이전, 원본은 로컬 개발용으로 유지) →
  `README.md`(N=6·v0.x·production_failures 0건 명시, 벤더주장 안 함 원칙 명시) → `LICENSE`(MIT).
  `claude plugin validate` 통과. `gh repo create kimheetae0104/token-saver --public --push`로 배포 완료:
  https://github.com/kimheetae0104/token-saver
- **실치 설치 검증**: `claude plugin marketplace add` → `install` → `list`/`details` 실사이클 확인
  (훅 2개 인식, 상시토큰비용 0). 이 프로젝트 자체가 로컬 `.claude/settings.json`으로 같은 훅을 이미
  쓰고 있어 user-scope 설치 시 중복 실행되므로, 검증 후 uninstall + marketplace remove로 원복함
  (전역으로 계속 설치해둘지는 사용자 선택 사항으로 남김).
- **커뮤니티 마켓플레이스 정식 제출은 보류** — 사용자 결정: N=6 상태로 정식 제출하면 방금 비교에서
  지적한 "미성숙한 주장을 자신있게 내놓는" 함정에 스스로 빠지는 것과 같다는 판단.

## 열린 스레드 — 다음 세션 후보 (2026-08-04 4차 갱신)
1. ~~`production_failures.jsonl` 영속성 버그~~ **완료(2026-08-04)**: `measure.py`에 `--data-dir` 인자
   추가(`do_capture_failures`가 우선 사용, 없으면 기존 `PRODUCTION_LOG` 상대경로로 폴백). 배선:
   `hooks/hooks.json`의 Stop 훅이 `CLAUDE_PLUGIN_DATA` 환경변수를 명시적으로 export하며
   `session_autopsy.sh` 호출 → 스크립트가 그 값이 있으면 `--data-dir "$CLAUDE_PLUGIN_DATA"`를 붙여
   `measure.py`에 전달, 없으면(로컬 프로젝트 사용) 기존 그대로. 4가지 경로(CLI --data-dir 있음/없음,
   훅 스크립트 env 있음/없음) 합성 픽스처로 전부 검증 — 로컬 동작 불변, 플러그인 경로는 영속
   디렉터리에 씀. 테스트 중 실수로 실제 `experiments/production_failures.jsonl`에 합성 항목이
   1건 써졌던 것 발견해 즉시 삭제(실측 로그 오염 방지). README "알려진 제한사항"에서 이 항목 제거.
2. ~~many_agents 재검토~~ **재검토 완료, 값 유지(2026-08-04)**: N=6→7(세션 1개 추가:
   `2fd3cd7f`, 이번 대화 세션 자체, n_agents=0). 분포 0/0/6/8/8/10/30 — 새 값이 0이라 건강
   상한(10)·outlier(30) 둘 다 안 바뀜, 발화 여전히 1/7(outlier만). **결론: 변경 근거 없음,
   12 유지.** 단 이번 추가분은 8~12 경계 근처 값이 아니라서 원래 열린 질문(8~10 클러스터링이
   유지될지, 12 근처 새 정상 사례가 나올지)은 여전히 미해결 — 다음에도 근처 값(11~15)이
   나와야 실제로 판단 가능. 검증: `measure.autopsy()` 직접 호출로 7개 세션 전부 재확인
   (스크립트에서 `proxies(sess, per_turn)` 인자 순서 실수 한 번 했다가 바로잡음).

## 성능/신뢰도 테스트 로드맵 (2026-08-04 5차, 진행 중)
사용자 요청: "성능이랑 신뢰도 테스트" — 4갈래로 분해.
1. ~~플러그인 자체 안정성(훅 엣지케이스)~~ **완료(2026-08-04)**: `intent_gate.py`·`habit_coaching.py`
   ·`measure.py --check/--statusline/--capture-failures`를 빈 stdin·손상 JSON·비문자열 prompt·
   디렉터리 경로 등 26케이스로 방어적 테스트(무료, API 호출 없음). **실버그 3종 발견·수정**:
   (a) `intent_gate.py`/`habit_coaching.py` — `prompt`가 문자열이 아니면(int·array) `.strip()`에서
   미처리 예외로 훅이 죽음 → `isinstance(prompt, str)` 가드 추가. (b) `measure.py`의 `do_check`
   `do_statusline`·`do_capture_failures` 3곳 — `transcript_path`가 디렉터리면 `os.path.exists()`가
   True를 반환해 통과한 뒤 `open()`에서 `IsADirectoryError`로 죽음 → `os.path.isfile()`로 교체.
   `session_autopsy.sh`는 bash `[ -f "$path" ]` 가드가 이미 있어 해당 안 됨(정상 확인).
   CLI 전용 경로(`--autopsy` 포지셔널 인자)는 사람이 직접 넣는 값이라 훅 안전성과 무관, 손 안 댐.
   테스트 하네스는 일회성(스크래치패드, 삭제됨) — 재현 필요시 이 항목 설명대로 재작성.
2. **과제 다양성 확대(대기)**: 실험8/8확대는 "직관대로 풀리는" 기계적 과제(코드+테스트, 버그+lint,
   변환+schema) 3종만 검증(N=30 포함). 리팩터·설정편집·멀티파일 컨텍스트 등 다른 유형은 미검증.
   다음 세션에서 과제셋 설계 + 예상 비용 산정 → 사용자 승인 후 실행 예정(실비용 발생, 이전
   실험8확대 기준 30콜=$0.58 정도가 참고 스케일).
3. **many_agents 데이터 축적**: 액션 불가(실측만 기록 원칙) — 세션 자연 누적 대기.
4. **경쟁 도구 head-to-head(대기)**: Ponytail 등 실제 설치 가능 여부부터 확인 필요 — 설치는
   외부 플러그인이라 명시적 승인 필요. 다음 세션에서 실현가능성 조사부터.

## 재개 방법
1. 이 폴더에서 새 세션 시작(→ `CLAUDE.md` 자동 로드로 규칙 복원).
2. 이 `HANDOFF.md` + 필요 시 `experiments/PROTOCOL.md`만 읽으면 상태 복원(전체 대화 불필요).
3. `python3 measure.py --all` 로 이전 세션 대비 효율 비교하며 시작.
4. "열린 스레드" 중 하나 골라 진행.
