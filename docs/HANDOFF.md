# 세션 인수인계 (2026-10-27 기준)

이전 Claude 세션에서 하던 작업을 새 세션이 이어받기 위한 문서다.
작업 원칙은 `CLAUDE.md`, 결정 경과는 `docs/설계-결정사항.md`. 이 문서는 **지금 상태와 남은 일**만 다룬다.

## 1. 새 세션이 처음 할 일
1. `CLAUDE.md` → 이 문서 → `docs/설계-결정사항.md` 순서로 읽는다.
2. 쓸 수 있는 도구를 확인해 사용자에게 한 줄씩 보고한다: Supabase 커넥터(프로젝트 `security-news-collector` 조회 가능 여부), Vercel 커넥터, 사용자 브라우저 연결, `gh` 인증, 예약 작업 도구.
3. 현황을 5줄 이내로 요약해 사용자 확인을 받는다.
4. 옛 점검 예약은 그대로 두고 **10/29 09:30 점검 예약을 새로 만든다**(아래 3절 지시문). 만든 직후 `mcp_connections`가 비어 있는지 확인하고, 커넥터가 붙었으면 사용자에게 알린다(예약 작업에 커넥터가 붙는 것은 위험 — `CLAUDE.md` 원칙 5).

## 2. 현재 상태 (10/27 오전 점검 결과)
- **브리핑**: 10/27 06시판이 새 고정 지시문(→ `briefing/ROUTINE.md`)으로 정상 작성됨. 검증 오류·경고 0건. 새 형식(절 순서·제목 링크·"보도:" 말풍선·2줄 요약·가운데 점 없음·상한 없음) 준수.
- **AI 한 줄 요약**: Haiku 5.5로 매시간 실행, 밤사이 탈락·잘림 0건. 이번 달 비용 약 0.07달러. 요약이 빈 기사는 모두 `not_security`(의도대로 요약 안 함).
- **DB 정의 점검**(매일 05:00): 통과.
- **디지털데일리**: 첫 시도 403이 자주 나지만 새 서버 재수집(`retry-403`)으로 1~2분 안에 회복.
- **대시보드**: C안 적용(커밋 8556080·68f8077) — 본문 1200px(1440px 이상 화면 1480px), 글자 16px, 1440px 이상에서 오른쪽 보조 칸(이번 판 주요 사건 → 최근 진행 중 사건 → 다가오는 보안 행사, 모든 제목은 대표 기사 링크). 1680px 화면에서 확인 완료.
- **예약 작업**:
  - 정보보안 브리핑 — 사용자가 만듦, 커넥터 0개, 지시문은 고정 문구(`briefing/ROUTINE_BOOTSTRAP.txt`). **수정·삭제하지 않는다.**
  - 이전 세션에 묶인 10/29 점검 예약 `3일 운영 결과 점검·품질 개선`은 **사용자가 일시중지함(10/27 확인, enabled=false)** → 새 세션이 아래 3-1 지시문으로 다시 만든다. 옛 작업은 다시 켜지 않는다.
  - **10/29 점검 예약 `3일 운영 결과 점검·품질 개선 (10/29)` 생성(10/27 09:18)** — 10/29 09:30 1회, 이전 세션에 묶임, 지시문은 3-1 그대로. 생성 직후 `mcp_connections`·`mcp_servers` 모두 비어 있음(커넥터 0개) 확인. 이 조직에서는 예약 작업 도구의 커넥터 지정 설정이 막혀 있어, 사용자 승인 뒤 기본값으로 만듦.
  - 참고: 이전 기록의 (예약 작업)은 10/27 09:16 조회 시 **존재하지 않았음**(목록·개별 조회 모두 없음) → 위 예약으로 대체.

## 3. 남은 일
### 3-0. 새 공개 저장소 전환 (10/27 사용자 결정 — 진행 중)
- 결정: 기존 저장소 이름 변경(비공개 보관) → 같은 이름 `deep-taker/security-news-collector`로 새 공개 저장소, 이력 없이 코드만. GitHub 보조 백업 중단, 수집 기록에 원문 HTML 업로드 안 함, 브리핑 입력 요약은 공개, parse-fail·suspicious는 저장소에 두고 공개 감수, **기존 DB 기록 모두 삭제(전환 때, 직전 백업 뒤)**.
- 1단계(준비 PR): 위 코드 변경 + Dependabot 자동 병합에 '같은 저장소 브랜치만' 조건.
- 2단계(사용자): 기존 저장소 이름 변경 → 같은 이름 공개 저장소 빈 상태로 생성. 3단계(Claude): 첫 커밋 하나로 코드 올림(data·briefings 기록 제외, noreply 작성자).
- 4단계(사용자): GitHub Secrets 3개(SUPABASE_URL·SUPABASE_SERVICE_KEY·ANTHROPIC_API_KEY), Vault의 GitHub 실행 토큰(새 저장소 권한), Vercel Git 연결, 저장소 보안 설정(외부 PR 승인 후 실행·토큰 읽기 기본·비밀값 검사·이슈 끄기·이메일 비공개). 브리핑 예약 작업이 새 저장소에서 안 돌면 사용자가 같은 고정 문구로 다시 만들고 Vault fire URL·토큰 4개 교체.
- 저장소가 10/28 새벽 사용자에 의해 `deep-taker/security-news-collector`(비공개)로 옮겨짐. 새 공개 저장소도 deep-taker 아래 같은 이름으로 만든다(사용자 결정). 옛 저장소는 `security-news-collector-archive` 등으로 이름 변경. 저장소 주소를 쓰는 곳(ROUTINE.md·ROUTINE_BOOTSTRAP.txt·대시보드 링크·문서)은 deep-taker로 바꿈. DB 실행 주소는 마이그레이션 `20261028_dispatch_repo_deep_taker.sql`을 4단계 직후 적용. **같은 이름 저장소는 한 세션에 둘 수 없어, 3단계부터는 deep-taker/security-news-collector를 소스로 한 새 세션에서 진행.**
- 3단계 첫 커밋: 작성자는 noreply 주소, 커밋·PR에 Claude 세션 링크 넣지 않음(CLAUDE.md 원칙 8). 공개 전 `python -m pytest tests -q`의 개인정보 검사(`tests/test_public_repo.py`) 통과 확인. 사용자는 GitHub 설정에서 'Keep my email addresses private'·'Block command line pushes that expose my email'을 켠다. 도메인 등록 정보(WHOIS) 비공개 여부도 사용자가 확인.
- 대시보드 주소는 `briefing-security.vercel.app`(10/28 사용자 결정, 개인 도메인 사용 안 함, Vercel 프로젝트에서 옛 도메인 제거·팀 이름 변경 완료). 4단계에서 Vercel Git 연결을 새 공개 저장소로 바꾼 뒤 운영 배포가 READY인지 확인.
- **새 저장소로 넘기지 않는 파일 (10/28 분석·사용자 결정)** — 3단계 첫 커밋에서 제외:
  | 제외 | 이유 |
  |---|---|
  | `data/` 전체 (backup·briefing-input·briefing-output·samples·db-status.json) | 기존 기록 보관 불필요(DB도 삭제). 필요한 폴더는 작업이 실행될 때 자동 생성 |
  | `briefings/` 전체 | 지난 판 기록 불필요 |
  | `supabase/generated/definitions.sql` | 옛 계정 이름 포함. DB 실행 주소 마이그레이션 적용 뒤 'DB 정의 동기화'로 다시 생성 (`columns.txt`는 넘김) |
  | `supabase/migrations/20261026_*`, `20261027_*` (3개) | 이미 운영 DB에 적용된 기록용(첫 파일은 '적용 금지'). 현재 정의는 schema.sql + generated. `20261028_dispatch_repo_deep_taker.sql`은 미적용이라 넘김 |
  | `.github/workflows/sample-pages.yml` | 기사 원문 HTML을 저장소에 커밋하는 수동 도구 — 공개 저장소에 원문을 올리지 않음(필요하면 보관 저장소에서 실행) |
  | `.github/workflows/probe-sites.yml`, `tests/tools/probe_sites.py` | 수집원 후보 접속 시험(사용자 결정: 제외). 필요하면 보관 저장소에서 실행 |
  | `tests/tools/page_diff.py` | 어디서도 쓰지 않는 개발 도구 |
  - 넘기는 것: 나머지 코드·시험·시험 자료(`tests/fixtures`, `dashboard/tests/fixtures` — 시험에 필요한 기사 발췌), 문서, `briefing/ROUTINE_BOOTSTRAP.txt`(브리핑 예약 작업을 다시 만들 때 필요), `.claude/settings.json`.
  - 첫 커밋 뒤 확인: `python -m pytest tests -q`, `cd dashboard && node --test tests/*.mjs && npm run build`가 제외 파일 없이 통과하는지.
  - 알아 둘 것: DB `system_alerts()`의 `source_summary_low` 안내 문구가 '매체 원문 표본 저장 작업'을 가리킴 → 보관 저장소에서 실행하면 됨(문구 변경은 다음 DB 수정 때 함께).
- **개인정보 최종 처리(10/28)**: `supabase/generated/definitions.sql`에 옛 계정 이름이 든 실행 주소가 남아 있음(DB 실행 주소 마이그레이션 적용 전이라). → 3단계 첫 커밋에서 이 파일은 **빼고**, 5단계에서 마이그레이션 적용 직후 'DB 정의 동기화' 작업을 수동 실행해 새로 만든다. 4단계에서 사용자가 GitHub Secrets `PRIVATE_WORDS`(옛 계정 이름·개인 이메일 아이디·옛 도메인·옛 Supabase 프로젝트 ID·기기 이름 등, 쉼표 구분)를 등록하면 CI가 공개 파일에서 검사한다(`tests/test_public_repo.py`, 단어는 출력하지 않음).
- 5단계(Claude): DB 기록 삭제(승인 범위 확인) → 수집·브리핑 준비·반영·백업 수동 실행 → 대시보드·다음 날 06시판 확인. 10/29 점검 예약 다시 만들기.
### 3-1. 10/29(목) 09:30 3일 운영 점검 — 예약됨
예약 지시문(그대로 사용):
```
10/29 09:30 — 3일 운영 결과 점검·품질 개선 시점이다. 모든 출력은 한국어로만 쓴다. 저장소 deep-taker/security-news-collector 의 CLAUDE.md와 docs/HANDOFF.md를 먼저 읽는다. (10/26에 이미 반영됨 — 디지털데일리·전자신문 목록 요약 추출, 기사 페이지 설명 보완, 한 줄 요약의 AI 전환(collector/ai_summary.py, Claude Haiku 5.5, summary_source=ai), 같은 사건 묶어 보기, 브리핑 RSS, 주간 요약. 다시 구현하지 말 것)
1) 10/26~10/29 운영 점검: Supabase(security-news-collector 프로젝트) collection_runs(flags의 gap:·page2_failed·retry:403·retried:403 포함)·briefings·briefing_checks·backup_runs·remediation_runs·system_alerts(), 매체별 후보 대비 not_security 비율(오탐), 후보에서 빠졌지만 보안 관련으로 보이는 기사 표본(놓침). 국방·방산보안 절과 보안 행사 절이 실제 판에 나왔는지, security_events 누적 건수.
2) 디지털데일리 403: 첫 시도 403 횟수, 새 서버 재수집(retried:403) 성공률, 403 진단 문구로 차단 주체 확인. 재수집도 자주 실패하면 대책(수집 시각 분산·매체 문의)을 제안.
3) AI 한 줄 요약 점검: collection_runs의 source_id가 비고 flags에 ai_summary가 있는 행으로 성공률·탈락 이유·응답 잘림·모델(claude-haiku-5-5) 확인. summary_source별 비율. AI 요약 표본 15건의 품질(제목 반복·과장·입력에 없는 사실·80자 초과). 문제가 있으면 collector/ai_summary.py의 지시문·검증을 보완하고 시험 추가, CI 통과 확인.
4) 키워드 점검 구현: 1)의 오탐·놓침 표본을 근거로 collector/keywords.py 조정(국방·군사보안 용어 포함), 단위 시험 추가.
5) 2단계 매체 판단 자료: 정부·공공기관·해외 매체 후보와 예상 효과. 국방 수집원 접속 시험 결과(방사청·국방일보·국방홍보원·NCSC 허용, 국방부·국정원 robots.txt 거부, 연합뉴스 북한 RSS)를 반영.
6) 분류 대기 기사의 사건 묶기 판단 자료: 매시간 AI 요약 단계에서 '같은 사건 후보'까지 표시하는 방안의 예상 비용(Haiku 토큰), 3일치로 본 정확도 추정(브리핑이 실제로 묶은 결과와 비교), 화면 표시 방법, 도입 권고(구현은 사용자 승인 뒤).
7) 대시보드: 브리핑 화면 절별 배치 순서(INSTRUCTIONS.md '각 절 안의 배치 순서')가 지켜졌는지 10/27~10/29 판에서 확인.
결과를 한국어로 짧게 보고한다(무엇을 바꿨는지, 근거 수치, 남은 판단 사항).
```

### 3-1b. 10/27 점검 개선 (PR #10 병합 완료)
- 반영(저장소): 푸시 재시도 실패를 숨기던 워크플로 6곳 수정, 06시판 정비 실패 시에도 입력 커밋, 브리핑 DB 반영 실패를 실패로 표시(파일별 처리)·동시 실행 제한, 403 재수집 작업에 의심 원문 보관 추가, 마지막 성공 시각 조회 실패에도 수집 계속, RSS 복구 모드 사용 시 `xml_recovered` 표시, 쪽 나눔 정렬 고정, 대시보드 주요 사건 제목의 `&amp;` 깨짐·오류 화면(`app/error.js`)·검색 파라미터 배열 오류, 옛 마이그레이션 '적용 금지' 표시, 재구축 점검에 PUBLIC 권한 검사.
- **DB 적용 완료(10/27 17시, 사용자 승인)**: `supabase/migrations/20261027_export_definitions_public_grants.sql` 적용, 시험용 임시 함수 `_export_definitions_test()` 삭제. 적용 뒤 내보낸 정의에 PUBLIC 권한 0건, export_definitions 실행 권한은 service_role만(변화 없음). PR #10으로 저장소 반영(병합 86dc8f9). 다음 05:00 정의 동기화 때 generated/definitions.sql의 표 revoke 줄이 'from public, anon, authenticated'로 바뀌는 것이 정상.
- 참고: Supabase 커넥터의 DB 변경 명령은 확인 창 응답이 필요하다. 응답이 없으면 시간 초과·'requestState 만료'로 실패하므로, 사용자가 확인할 수 있을 때 실행한다.

### 3-2. 사용자 확인 대기
- **휴대폰 화면**: 보도 매체 작은 글씨(터치 기기에서만 표시)와 C안 휴대폰 배치 — PC 크롬에서 재현 불가, 사용자가 휴대폰으로 확인하기로 함.
- **휴대폰 날짜 목록**: 한 단 배치에서 날짜 목록이 위쪽을 많이 차지 — 접는 메뉴로 바꿀지 사용자 결정 대기(이전 세션에서 제안만 함).

### 3-3. 다음 주 이후
- **11/2(월) 06시판**: 첫 주간 요약(`briefings/2026-11-02-week.md`) 작성 여부 확인. 없으면 `weekly_missing` 알림이 뜬다.
- **11/2 복구 시험**(매월 2일): `security_events` 포함 복구가 되는지 결과 확인.
- 확인 필요(오래된 질문): Supabase 무료 Storage 1GB가 프로젝트별인지 조직 합계인지.

## 4. 최근 결정 (10/26~10/27, 자세한 내용은 설계 결정사항)
- 한 줄 요약은 AI(Haiku 5.5)로 매시간, 요약 전에는 칸을 비워 둠.
- 브리핑 절 순서: 주요 사건·사고 → 기타 사건·사고 → AI 보안 → 정책·제도 → 국방·방산보안 → 업계 동향 → 보안 행사. '수집 상태' 절 없음. 개수 상한 없음, 주요 사건은 5가지 기준.
- 절 안 배치 순서: 절마다 기준이 따로 있음(`briefing/INSTRUCTIONS.md`).
- 보안 행사는 국내만, 탭·보조 칸 모두 맨 끝.
- 예약 작업 지시문은 고정 문구, 절차는 저장소 파일(`briefing/ROUTINE.md`).
- 대시보드 C안(폭 확대 + 오른쪽 보조 칸, 제목 링크).
- 휴대폰(720px 이하)은 브리핑 절 탭 없이 모든 절을 한 페이지에 나열(10/27, PC는 탭 유지). 실제 휴대폰 확인은 사용자.
- 업계 동향도 다른 절처럼 제목 1줄 + 내용 2줄(10/27, `briefing/INSTRUCTIONS.md`·`ROUTINE.md`·검증기 반영). main 병합 뒤 첫 판부터 적용 — 다음 판에서 업계 동향 2줄과 검증 주의 0건 확인.
- 전자신문 접속 시간 초과 대책(10/27): 접속 실패도 새 서버 재수집(`retry:conn`/`retried:conn`). DB 마이그레이션 `supabase/migrations/20261027_alerts_exclude_conn_retry.sql`(연속 실패 계산에서 `retry:conn` 제외)은 **사용자 승인 뒤 적용** — 적용 여부를 확인할 것. 10/29 점검 때 `retried:conn` 성공률도 함께 볼 것.

## 5. 주의 사항
- 예약 작업 지시문에 바뀐 절차를 넣지 말 것 — `briefing/ROUTINE.md`만 고친다.
- `supabase/generated/`는 운영 DB에서 매일 자동 생성 — 직접 고치지 말 것.
- 대시보드 배포는 main 푸시 시 Vercel이 자동으로 한다(1~3분). 클라우드 작업 공간에서는 briefing-security.vercel.app에 직접 접속이 막혀 있을 수 있음 → 사용자 브라우저나 Vercel 커넥터로 확인.
