# 운영 지침서 — 알림별 대응

대시보드 [수집 상태](https://briefing-security.vercel.app/status)의 알림 종류별로 의미, 자동 조치, 사용자가 할 일을 정리했습니다.
'오류'가 20분 넘게 계속되면 자동 조치가 브리핑 예약 작업을 '알림' 형식으로 실행해 휴대폰으로 알립니다(설정: `ops/ROUTINES.md`).

| 알림 (코드) | 단계 | 뜻 | 자동 조치 | 사용자가 할 일 |
|---|---|---|---|---|
| 수집이 멈췄습니다 (`collect_stalled`) | 오류 | 2시간 15분 넘게 수집 기록 없음 | 90분 시점부터 수집 재실행(1시간 1번, 6시간 2번) | 계속되면 GitHub Actions '매시간 수집' 실행 기록 확인 → 실행 자체가 없으면 아래 '실행 신호 오류' 참고 |
| ○○ 수집 N회 연속 실패 (`source_failing`) | 오류 | 매체 접속·파싱 실패가 기준(디지털데일리·디지털투데이 2회, 나머지 3회) 이상 | 403이면 즉시 새 서버(다른 IP)에서 재수집 — 첫 시도 403은 횟수에 넣지 않고 재수집 결과만 셈. 매시 27분 재수집. '수집 0건'이 3시간 지속되면 수리 PR 요청 | 403: GitHub 실행 서버 IP 단위 차단(일시적). 오류 문구의 `server=…`·`headers=…`로 차단 주체 확인. 새 서버 재시도도 하루 넘게 실패하면 매체에 수집 허용 문의 검토 → 알려 주세요. 시간 초과: 대부분 일시적. 수리 PR이 오면 CI 통과 확인 후 병합 |
| ○○ 최근 수집 실패 (`source_failed`) | 주의 | 기준 미만 실패 | 27분 재수집 | 없음 |
| ○○ 24시간 새 기사 0건 (`source_no_new`) | 주의 | 수집은 되지만 새 기사가 없음 | 없음 | 매체 사이트에 실제 새 기사가 있는지 확인. 있다면 사이트 구조 변경 → 알려 주세요 |
| AI 한 줄 요약 채움률 N% (`ai_summary_low`) | 주의 | 24시간 공개 기사 중 AI 요약이 절반도 안 됨 | 다음 수집 때 밀린 기사부터 다시 요약 | GitHub Secrets `ANTHROPIC_API_KEY` 등록·만료 확인, platform.claude.com 사용 한도·결제 확인, '매시간 수집' 로그의 'AI 한 줄 요약:' 줄 확인 |
| ○○ 한 줄 요약 채움률 N% (`source_summary_low`) | 주의 | 매체 24시간 기사 중 요약이 절반도 안 됨 | 없음 | 비공개 보관 저장소(`security-news-collector-archive`)의 '매체 원문 표본 저장 (수동)' 실행 → 그 저장소 data/samples/ 표본으로 목록 구조 변경 확인 → 공개 저장소에 파서 수정 (공개 저장소에는 원문 표본을 올리지 않음) |
| 수집 원문에서 지시문 의심 문장 (`inject_suspected`) | 주의 | 24시간 안 수집 원문에 AI를 겨냥한 지시문 형태 문장 | 원문 data/suspicious/ 영구 보관, 브리핑·AI 요약은 따르지 않음 | 반복되면 해당 원문 확인 (디지털타임스 사례는 오탐이었음) |
| 놓친 기사가 있을 수 있음 (`source_gap`) | 주의 | 수집이 끊긴 사이 목록에서 밀려난 기사가 있을 수 있음 | 없음 | 표시된 시간대의 해당 매체 보안 기사를 사이트에서 직접 확인 |
| ○판 브리핑 누락 (`briefing_missing`) | 오류 | 예정 1시간 뒤에도 브리핑 없음 | 예정 40분 뒤 브리핑 작업 재실행(판마다 1번) | claude.ai/code/routines의 브리핑 작업 실행 기록 확인(사용량 한도·GitHub 연결 만료 여부) |
| ○판 브리핑 반영 검증 실패 (`briefing_check_failed`) | 오류 | 라벨 누락·없는 사건·허용되지 않은 링크·DB/대시보드 미반영 | DB 문제는 반영 재실행, 내용 문제는 브리핑 작업에 보완 요청(판마다 1번) | 계속되면 GitHub Actions '브리핑 결과 반영' 로그 확인. **허용되지 않은 링크**는 숨은 지시문 영향 가능성 → 해당 판 본문 확인 |
| 예약 신호 실패 (`cron_failed`) / 실행 신호 응답 오류 (`dispatch_failed`) | 주의 | Supabase → GitHub 실행 신호 실패 | 없음 | 응답 401·403이면 GitHub 토큰 만료·권한 확인 → README '비밀값 교체 절차' |
| 주 백업 26시간 이상 없음 (`backup_storage_missing`) | 오류 | 매일 백업 실패 | 06시 이후 백업 재실행(하루 2번) | GitHub Actions '백업 (매일)' 로그 확인 |
| 전체 사본 실패 | 주의 | 보조 백업·주간 전체 사본 실패 | 다음 날 재시도 | 이틀 이상 계속되면 확인 |
| 백업 용량 상한의 90% (`backup_storage_size`) | 주의 | 900MB 상한에 근접 | 오래된 사본 자동 정리 | 보관 개수(`collector/backup.py` KEEP) 조정 검토 |
| 백업 복구 시험 실패 (`restore_test_failed`) | 오류 | 월간 복구 시험 실패 | 없음 | GitHub Actions '백업 복구 시험' 로그 확인 |
| 재구축 정의 점검 실패 (`schema_check_failed`) | 오류 | 매일 05:00 점검에서 저장소 정의로 빈 DB를 만들 수 없거나 열 구성이 운영과 다름 | 없음 | `supabase/schema.sql`을 운영 DB에 맞게 수정 (DB에 표를 추가했으면 schema.sql에도 추가) |
| 이상 점검 함수 오류 / 자동 조치 실행 오류 (`system_alerts_failed`, `remediation_failed`) | 오류 | 점검·자동 조치 함수 자체 실패 | 다른 단계는 계속 실행 | Supabase SQL Editor에서 `select public.auto_remediate();` 실행해 오류 문구 확인 |
| main 코드 자동 시험(CI) 실패 (`ci_failed`) | 오류 | main 코드가 시험을 통과하지 못함 | 없음 | GitHub Actions 'CI' 로그 확인 → 원인 커밋 수정 또는 되돌리기 |
| ○○ 교체 D-N / 기한 지남 (`reminder`) | 주의/오류 | 비밀값 정기 교체 시기 | 없음 | README '비밀값 교체 절차' 후 기한 1년 연장 |
| DB 용량 (`db_size`) | 주의 | DB 400MB 초과 (무료 500MB) | 보관 정책(90일) 매일 적용 | 보관 기간 단축 또는 오래된 보안 기사 이관 검토 |

## 되돌리기
- 대시보드: Vercel > Deployments에서 이전 배포 'Promote to Production'(즉시 롤백) 또는 해당 커밋 되돌리기
- 수집·백업 코드: GitHub에서 원인 커밋 Revert → CI 통과 확인
- DB 함수: `supabase/generated/definitions.sql`(매일 자동 저장)의 이전 버전을 SQL Editor에서 실행
