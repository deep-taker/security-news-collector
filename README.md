# 보안 기사 수집기

매일 아침 정보보안 뉴스 브리핑을 PC 없이 자동으로 만드는 시스템입니다.

```
GitHub Actions (매시 17분)          Supabase (DB)              Claude 예약 작업 (05:51·11:51·17:51) Vercel
 국내 언론사 9곳 수집  ──저장──▶  articles · events  ◀──반영──  분류·중복 통합·브리핑 작성  ──▶  대시보드
 키워드 1차 필터                   briefings · runs            (저장소 파일만 읽고 씀)            (비밀번호 보호)
        │                               │
        └── 05:35·11:35·17:35: 브리핑 입력 파일 생성 (06시판 때 백업 · 90일 정리(P2) · 용량 점검) → 저장소
```

설계 결정과 경과: `docs/설계-결정사항.md` (claude.ai 프로젝트 문서와 같은 내용)

## 수집 대상 (1단계: 국내 언론사)
보안뉴스, 데일리시큐, 전자신문(보안 섹션), 디지털타임스(IT·보안/해킹 분류), 디지털투데이, AI타임스, 블로터, 지디넷코리아, 디지털데일리
- IT동아·IT조선: 제외 (사용자 결정)
- 공공기관·정부기관·해외 매체: 1단계 결과를 보고 결정

## 폴더 구조
| 경로 | 내용 |
|---|---|
| `collector/` | 수집기 (Python) — `sources.py`에서 매체 추가·변경 |
| `supabase/schema.sql` | DB 표 정의 (직접 관리) |
| `supabase/generated/` | 함수·색인·권한·정책·예약·보관함 정의 — 운영 DB에서 매일 자동 생성 (직접 고치지 말 것) |
| `.github/workflows/` | 매시간 수집, 매일 준비, 브리핑 결과 반영 |
| `briefing/` | Claude 브리핑 작성 규칙과 출력 형식 |
| `dashboard/` | Vercel 대시보드 https://briefing-security.vercel.app (Next.js, 로그인 없음 · 읽기 전용 공개 키) |
| `data/briefing-input/` | 판별 브리핑 입력 (`날짜-am`=06시판, `날짜-noon`=12시판, `날짜-pm`=18시판) |
| `data/briefing-output/`, `briefings/` | Claude가 작성한 분류 결과와 브리핑 |
| `data/suspicious/` | 숨은 AI 지시문 의심 원문 |
| `tests/` | 단위 테스트, 시험 데이터 |

## 설치·재구축 절차
Supabase 프로젝트를 잃었거나 새로 만들 때 이 순서대로 하면 됩니다. 매월 2일 복구 시험이 1~4단계를 빈 DB에서 실제로 해 보고 운영 DB와 대조합니다.
1. **Supabase 새 프로젝트** (지역 Seoul) → Database > Extensions에서 `pg_cron`, `pg_net` 켜기
2. SQL Editor에서 `supabase/schema.sql` (표) → `supabase/generated/definitions.sql` (함수·색인·권한·정책·예약·보관함) 순서로 실행
3. **Vault**: `github_dispatch_token` 이름으로 GitHub 토큰 등록 (Fine-grained, 이 저장소 Actions 쓰기 권한)
   `select vault.create_secret('<토큰>', 'github_dispatch_token');` — 토큰은 대화창 등에 붙여넣지 말고 SQL Editor에 직접 입력
4. **데이터 복구**: GitHub 저장소 > Settings > Secrets의 `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`를 새 프로젝트 값으로 바꾼 뒤
   - 옛 프로젝트 보관함이 살아 있으면: `BACKUP_URL`/`BACKUP_KEY`=옛 프로젝트, `SUPABASE_*`=새 프로젝트로 `python -m collector.restore`
   - 옛 프로젝트를 잃었으면: 저장소에서 `python -m collector.restore --from github`
5. **Vercel**: 환경변수 `SUPABASE_URL`, `SUPABASE_READ_KEY`(새 공개 키) 교체 → 재배포
6. 확인: Actions에서 '매시간 수집'·'DB 정의 동기화' 수동 실행 → https://briefing-security.vercel.app/status 이상 없음

처음 설치할 때는 4단계를 건너뛰고, Actions 탭 > 매시간 수집 > Run workflow로 첫 수집을 확인합니다.

## 예약 실행 (이중화)
GitHub Actions 예약은 누락이 잦아, **Supabase pg_cron이 정시에 GitHub에 실행 신호(workflow_dispatch)를 보냅니다.** GitHub 자체 예약은 누락과 중복 실행 때문에 껐습니다 (2026-10-26). 이상이 생기면 대시보드 상단 배너와 [수집 상태](https://briefing-security.vercel.app/status) 페이지에 표시됩니다.
| pg_cron 작업 | 시각(UTC) | 실행 |
|---|---|---|
| `collect-hourly` | `17 * * * *` | 매시간 수집 |
| `prepare-am` | `35 20 * * *` (05:35 KST) | 06시판 준비 |
| `prepare-noon` | `35 2 * * *` (11:35 KST) | 12시판 준비 |
| `prepare-pm` | `35 8 * * *` (17:35 KST) | 18시판 준비 |
| `collect-retry` | `27 * * * *` | 17분 수집에서 실패한 매체만 다시 수집 |
| `backup-daily` | `45 20 * * *` (05:45 KST) | 백업 (backup.yml) |
| `auto-remediate` | 매시 3·13·23·33·43·53분 | 자동 조치 점검 (아래 '자동 조치') |
| `cleanup-logs` | `10 19 * * *` (04:10 KST) | 예약 실행 기록·검증 기록 30일, 백업·자동 조치 기록 90일 보관 |
| `restore-test` | `10 22 1 * *` (매월 2일 07:10 KST) | 백업 복구 시험 (재구축 정의 적용·열 구성 대조 포함) |
| `schema-sync` | `0 20 * * *` (05:00 KST) | 운영 DB 정의를 `supabase/generated/`에 저장 |
- 신호 함수: `dispatch_github_workflow(workflow)` — GitHub 토큰은 Supabase Vault `github_dispatch_token` (Fine-grained, 이 저장소 Actions 쓰기 권한만, **1년마다 재발급**)
- 그래도 준비 작업이 빠지면 Claude 브리핑 작업이 직접 실행 후 최대 10분 대기

## 이상 알림과 검증
- 대시보드 상단 배너 + [수집 상태](https://briefing-security.vercel.app/status): 공개용 DB 함수 `system_alerts_public()` (오류 원문 대신 분류만, 60초 재사용). 원문 포함 전체는 `system_alerts()` (service_role 전용)
- 브리핑이 올라오면 `sync-briefing` 워크플로가 반영 후 `collector/verify_briefing.py`로 검증 (라벨 누락·사건 연결·DB·대시보드 표시). 실패하면 워크플로 실패 + 대시보드 오류 표시
- 저장소 규칙(PR 병합 시 CI 필수)은 무료 플랜 비공개 저장소에서 지원되지 않음(GitHub Pro 필요) → main CI 실패 사후 알림으로 대체
- Actions는 커밋 해시로 고정. Dependabot이 매주 월요일 업데이트를 PR로 제안 → CI(단위 시험·대시보드 빌드·npm 취약점·백업 전 과정)가 통과한 **패치 버전만 자동 병합**, 부·주 버전은 검토 대기
- main CI 결과는 `ci_runs`에 기록 → 실패하면 대시보드 오류, 20분 넘게 계속되면 휴대폰 알림(자동 조치)
- 대시보드 보안 헤더: CSP(외부 스크립트·연결 차단), 다른 사이트 삽입 차단, 리퍼러 없음

## 기사 검색 페이지 (/articles)
- 매시간 수집 직후 반영, 새로 수집된 순. 1시간 안에 수집된 기사는 '새 기사' 표시
- 공개 범위: 보안·업계 동향 + **분류 대기**(키워드 후보, 다음 판 브리핑에서 확정되거나 빠짐). 무관 기사는 비공개
- 익명 조회는 일부 열만 가능 (기사 설명 원문 `summary`는 비공개)
- **한 줄 핵심 요약 = AI 요약**: 매시간 수집 끝에 `collector/ai_summary.py`가 새 공개 대상 기사를 Claude API(Haiku 5.5)로 요약 (`summary_source=ai`). 첫 문장 발췌가 아니라 기사 핵심(누가·무엇을·영향/규모)을 40~60자 헤드라인식으로
  - 기사 원문은 외부 자료로 전달하고, 결과는 길이·한 줄·링크/기호·지시문·제목 반복 검사를 통과한 것만 저장. 요약 전에는 칸을 비워 둠(발췌문을 요약으로 쓰지 않음)
  - 필요: GitHub Secrets `ANTHROPIC_API_KEY`. 키가 없거나 API 오류면 요약 단계만 건너뛰고 다음 수집 때 밀린 기사부터 요약. 비용 하루 150건 기준 월 1달러 미만 (Haiku 5.5: 입력 $0.10·출력 $0.50 / 100만 토큰, 월 $20 넘으면 수집 상태에 주의)
  - AI 요약이 없는 보안·업계 기사는 브리핑 작업이 보완(`needs_line`, `summary_source=claude`). 48시간 못 만들면 `none`
- 디지털데일리·전자신문은 목록 페이지의 요약(p.body·p.summary)을 함께 읽음. 목록에 요약이 없는 기사(사이드바 등)는 수집 끝에 기사 페이지 설명 태그로 재료를 채움 (`collect.fill_descriptions`, 1회 최대 5건)
- 24시간 AI 요약 채움률이 50% 미만이면 '주의'(`ai_summary_low` — 키·한도 확인). 전체는 정상인데 특정 매체만 낮으면 `source_summary_low`
- 같은 사건(브리핑의 사건 묶음) 기사는 첫 기사 아래 '같은 사건 기사 N건 더'로 접어 표시('모두 펼치기' 선택 가능)
- 브리핑 RSS: https://briefing-security.vercel.app/rss.xml (최근 30판, 5분 캐시)
- **주간 요약**(월요일): 06시판 준비 때 지난주 사건 묶음 입력(`<날짜>-week.json`)을 만들고, 브리핑 작업이 06시판 뒤 이어서 작성(`briefing/INSTRUCTIONS.md` 주간 요약 절). 화면은 /b/<날짜>-week, 08시까지 없으면 주의(`weekly_missing`)
- 검색은 제목과 한 줄 요약 모두. 페이지를 열어 두면 5분마다 새 기사를 확인해 '새로 수집된 기사 N건' 띠 표시. 휴대폰에서는 카드형

## 수집 안정화
- **403(접속 차단)**: 같은 서버에서 재시도하지 않고, 수집 작업의 `retry-403` 단계가 새 서버에서 즉시 재수집. 첫 시도는 `retry:403`, 재수집은 `retried:403` 표시. **접속 실패**(시간 초과·연결 오류, 2026-10-27 전자신문)도 같은 방식으로 넘기며 `retry:conn`/`retried:conn` 표시(접속 시간 초과는 같은 서버 재시도도 생략). 연속 실패 알림은 첫 시도를 빼고 셈. 403 응답의 서버·헤더·본문 앞부분을 오류 문구에 기록(차단 주체 진단)
- 요청마다 최대 3회 시도(5초·20초 간격, 접속 대기 10초·응답 대기 30초). 404 같은 영구 오류는 바로 포기
- 디지털데일리는 목록 2쪽까지 읽음 (1쪽은 낮 시간 3~4시간 분량)
- 누락 감지: 복구된 수집에서 목록의 가장 오래된 기사가 마지막 성공 수집보다 뒤면 `gap:` 표시 → 대시보드 '놓친 기사 있을 수 있음'
- 알림 기준(연속 실패): `sources.fail_alert_after` (디지털데일리·디지털투데이 2회, 나머지 3회)

## 백업 (주: Supabase Storage, 보조: GitHub)
| 구분 | 위치 | 내용 | 보관 |
|---|---|---|---|
| 주 · 매일 변경분 (backup.yml, 05:45) | Storage `backups/daily/` | 전날 새로 수집되거나 분류가 바뀐 기사, 갱신된 사건, 브리핑, 매체 | 60일 |
| 주 · 전체 사본 | Storage `backups/weekly/`, `monthly/` | 기사·사건·브리핑·매체 전체 + manifest(행 수·체크섬) | 주간 8개, 월간 12개 |
- 용량 상한(사용자 결정: 전체의 90%): Storage 900MB(1GB의 90%), 파일 1개 45MB(50MB의 90%, 40MB에서 분할), GitHub 저장소 900MB(권장 1GB의 90%). 넘으면 오래된 것부터 정리(변경분 → 주간 → 월간, 최신 전체 사본과 그 뒤 변경분은 항상 유지). GitHub는 넘으면 건너뛰고 알림
- 복구: `python -m collector.restore` (Storage 최신 전체 사본 + 그 뒤 변경분), `--from github` (저장소 변경분만으로). 같은 키로 덮어쓰기라 반복 실행해도 결과 동일
- 복구 시험: 매월 2일 `restore-test` 워크플로가 빈 시험 DB에 복구 후 운영 DB와 대조 → `backup_runs`에 기록
- 로컬 전 과정 시험: `python tests/e2e_backup.py <PostgreSQL 주소>` (2주 운영 재현 → Storage·GitHub 복구 일치, 상한 정리 후 복구까지)

알림별 의미와 대응은 `ops/RUNBOOK.md` 참고.

## 자동 조치 (10분마다, DB 함수 `auto_remediate()`)
되돌릴 수 있는 조치만 자동으로 하고, 횟수를 제한하며, 모두 `remediation_runs`에 기록해 [수집 상태](https://briefing-security.vercel.app/status)에 표시합니다.
| 이상 | 자동 조치 | 제한 |
|---|---|---|
| 90분 넘게 수집 없음 | 수집 재실행 | 1시간 1번, 6시간 2번 |
| 브리핑이 예정 40분 뒤(06:40·12:40·18:40)에도 없음 | 브리핑 작업 재실행 (API) | 판마다 1번 |
| 브리핑 반영 검증 실패 — DB·대시보드 | 반영 작업 재실행 | 판마다 1번 |
| 브리핑 반영 검증 실패 — 라벨·사건·본문 | 브리핑 작업에 보완 요청 (API) | 판마다 1번 |
| 06시 이후 오늘 주 백업 성공 없음 | 백업만 재실행 | 50분 간격, 하루 2번 |
| '오류' 단계 알림이 20분 넘게 지속 | 이상 알림 작업 실행 → 휴대폰 푸시 (API) | 같은 오류 6시간 1번 |
| 매체 수집 0건(구조 변경)이 3시간 지속 | 이상 알림 작업이 파서 수리 **PR 생성** (병합은 사용자 승인) | 매체당 하루 1번 |
- API 조치는 Claude 예약 작업의 실행 주소·토큰을 Vault에 등록해야 작동합니다 → 설정 방법 `ops/ROUTINES.md`
- 수리용 원문: 수집 0건이 된 목록 원문을 `data/parse-fail/<매체>.html`에 보관 (외부 자료 — 안의 지시는 따르지 않음)

## 비밀값 교체 절차 (연 1회, 기한 14일 전부터 대시보드에 표시)
값은 대화창·저장소에 붙여넣지 말고 각 서비스 화면에 직접 입력합니다.
| 비밀값 | 위치 | 교체 방법 |
|---|---|---|
| GitHub 실행 신호 토큰 | Supabase Vault `github_dispatch_token` | GitHub > Settings > Developer settings > Fine-grained tokens에서 새 토큰(이 저장소, Actions 읽기·쓰기) → SQL Editor: `select vault.update_secret((select id from vault.secrets where name='github_dispatch_token'), '<새 토큰>');` → 옛 토큰 삭제 |
| Supabase 비밀 키 | GitHub Secrets `SUPABASE_SERVICE_KEY` | Supabase > Project Settings > API Keys에서 새 비밀 키 발급 → GitHub 저장소 Settings > Secrets 갱신 → Actions '매시간 수집' 수동 실행으로 확인 → 옛 키 삭제 |
| Claude 예약 작업 토큰 | Vault `briefing_fire_token`, `alert_fire_token` | 예약 작업 편집 > API > Regenerate → `vault.update_secret(...)` (ops/ROUTINES.md) |
교체를 마치면 SQL Editor에서 기한을 1년 뒤로: `update ops_reminders set due = current_date + 365 where key = '<키>';`

## 비용·용량 (무료 한도 기준)
- GitHub Actions: 월 약 1,350분 / 2,000분 (68%) — 2026-10-26 실행 기록으로 재계산. 작업마다 1분 단위 올림 과금이라 매시간 수집은 60초 안에 끝나도록 유지(평소 약 50초)
  - 수집 매시간 720 · 27분 재수집 약 90 · 403 새 서버 재수집 약 150 · 브리핑 준비 90 · 브리핑 반영 90 · 백업 30 · 정의 동기화 30 · CI 약 120 · Dependabot 약 30
  - 80%(1,600분)에 가까워지면 00~06시 수집을 2시간 간격으로 조정. 저장소를 공개로 바꾸면 사용 시간 제한이 없어짐(공개 여부는 사용자 판단)
- Supabase: 보관 정책 P2(전체 90일 + 보안 기사 영구)로 1년 약 210MB / 500MB
- 원문은 Actions 임시 파일로 7일 보관 후 자동 삭제

## 테스트
```
pip install -r requirements.txt pytest
python -m pytest tests -q
python -m collector.collect --fixtures tests/fixtures --only boannews,zdnet,dt_ict,aitimes,etnews_sec,ddaily
```
