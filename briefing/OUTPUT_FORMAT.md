# data/briefing-output/<날짜>-<판>.json 형식

```json
{
  "date": "2026-10-27",
  "edition": "am",
  "briefing_path": "briefings/2026-10-27-am.md",
  "stats": {"candidates": 120, "security": 64, "pr": 18, "not_security": 38, "events": 21},
  "events": [
    {
      "slug": "php-cve-2026-115560",
      "title": "PHP 신규 원격코드 실행 취약점",
      "category": "취약점",
      "summary": "KISA 임시 조치 권고, 8.2~8.5 버전 업데이트 필요",
      "cves": ["CVE-2026-115560"]
    }
  ],
  "labels": [
    {"id": 1234, "label": "security", "event_slug": "php-cve-2026-115560", "line": "KISA, PHP 원격코드 실행 취약점 임시 조치 권고…8.2~8.5 버전 대상"},
    {"id": 1235, "label": "pr", "event_slug": null, "line": "안랩, 일본 보안 행사서 IT·OT 통합 보안 제시"},
    {"id": 1236, "label": "not_security", "event_slug": null}
  ]
}
```

- `slug`: 영문 소문자·숫자·하이픈. 후속 보도는 `recent_events`의 기존 slug 재사용
- `title`·`summary`: **반드시 한글**로 쓴다(대시보드에 그대로 보임). slug를 그대로 넣거나 비우지 않는다. 후속 보도로 기존 사건을 다시 쓸 때도 `recent_events`의 한글 제목을 그대로 쓴다 — 검증기가 오류로 처리한다
- `category`: 침해사고 / 취약점 / 악성코드·랜섬웨어 / 개인정보 / 정책·제도 / 방산보안 / AI 보안 / 기타
- `labels`: 입력의 모든 후보 기사 id에 대해 하나씩
- `line`: 입력에서 `needs_line: true`인 **보안(security)·업계 동향(pr) 기사만** 한 줄 핵심 요약 (40~60자, 최대 80자). 첫 문장 옮기기 금지, 헤드라인식 간결체. 일반 글자만 — 링크·마크다운 기호·줄바꿈 금지. 입력에 없는 사실 금지. 그 밖의 기사는 생략(이미 AI 요약이 있음). 대시보드 '기사 검색'에 제목 아래 표시된다
- `edition`: 입력 파일의 edition 값 그대로 (am·noon·pm)

## 주간 요약 (월요일)
- 파일: `briefings/<날짜>-week.md`, `data/briefing-output/<날짜>-week.json`
- JSON: `{"date": "<날짜>", "edition": "week", "events": [], "labels": [], "stats": {"events": N}}` — 본문 형식은 INSTRUCTIONS.md '주간 요약' 절

## 보안 행사 (`security_events`, 선택)
이번 판 기사에서 확인한 **국내** 보안 행사. 기사에 날짜가 분명한 것만. 같은 행사가 여러 판에 나와도 그대로 다시 쓰면 DB가 행사명+시작일로 합친다.
```json
"security_events": [
  {"name": "2026 AI 기반 방산기술보호 컨퍼런스", "start_date": "2026-10-28", "end_date": null,
   "place": "서울 코엑스", "organizer": "방위사업청", "url": "<입력 기사 주소>", "major": true,
   "note": "방산기술 보호와 AI 보안 대응 논의", "article_ids": [1234]}
]
```
- `start_date`·`end_date`: YYYY-MM-DD (종료일 없으면 null). 장소·주최를 모르면 null
- `url`: 입력 기사 주소만(수집 매체 도메인 외 링크는 저장되지 않음)
- `note`: 200자 이내, 일반 글자만
