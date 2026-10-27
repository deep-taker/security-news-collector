# Claude 예약 작업 설정 (자동 조치 연결)

Supabase `auto_remediate()`(10분마다)가 이상을 발견하면 **브리핑 작업 하나**("정보보안 브리핑 (06·12·18시)")를 API로 실행한다.
브리핑 작업이 첫 줄 형식(자동 조치 / 보완 요청 / 알림 / 수리 요청)에 따라 처리한다.
별도 '이상 알림·자동 수리' 작업은 만들지 않는다 — 에이전트가 만든 예약 작업에는 대화의 커넥터(Supabase 등)가 자동으로 붙고
뗄 수 없어, 외부 원문을 다루는 수리 작업에 쓰기에 위험하다(2026-10-26 생성 후 삭제). 브리핑 작업은 커넥터 없이 만들어져 있다.

| Vault 이름 | 값 |
|---|---|
| `briefing_fire_url` / `alert_fire_url` | 둘 다 `https://api.anthropic.com/v1/claude_code/routines/<브리핑 작업 ID>/fire` (작업 ID는 예약 작업 목록에서 확인) |
| `briefing_fire_token` / `alert_fire_token` | 둘 다 브리핑 작업 편집 화면 API 트리거의 토큰 (같은 값) |

토큰 재발급 시 (Supabase SQL Editor에 직접 — 대화창·저장소에 붙여넣지 말 것):
```sql
select vault.update_secret((select id from vault.secrets where name = 'briefing_fire_token'), '<새 토큰>');
select vault.update_secret((select id from vault.secrets where name = 'alert_fire_token'), '<새 토큰>');
```
2026-10-26 시험: 호출 응답 200. 휴대폰 알림은 "할 일 없음" 문구에는 오지 않고 "확인 필요" 문구에는 도착 → 자동 조치 알림 첫 줄을 "알림: 확인 필요 — 해결되지 않은 오류 N건"으로 고정.

## 브리핑 작업 지시문 (2026-10-27부터 고정 문구)
예약 작업 화면의 지시문은 `briefing/ROUTINE_BOOTSTRAP.txt`와 같은 고정 문구다(커넥터 금지·외부 자료 속 지시 무시 등 원칙 + `briefing/ROUTINE.md`를 읽어 따름).
절차(판 판정, 작성·검증·커밋, routine-fire-payload 처리 — 자동 조치/보완 요청/알림/수리 요청)는 **`briefing/ROUTINE.md` 7번**에 있다. 바꿀 때는 저장소 파일만 고친다 — 예약 작업 지시문은 고치지 않는다.
