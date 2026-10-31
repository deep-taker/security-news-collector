"""수집 대상 정의 (1단계: 국내 언론사).

kind:
  rss          - RSS/Atom 피드
  html_etnews  - 전자신문 섹션 목록 페이지
  html_ddaily  - 디지털데일리 전체기사 목록 페이지
  html_itdonga - IT동아 뉴스 목록 페이지 (robots.txt가 RSS 경로를 막음)

security_source: 보안 전문 매체·보안 섹션이라 모든 기사를 후보로 올림
security_categories: RSS 분류값이 이 중 하나면 후보로 올림
ai_source: AI 전문 매체 (AI 보안 키워드를 함께 적용)

IT조선·IT동아는 2026-10-31 추가(사용자 결정 — IT조선: 공개 RSS·robots.txt 허용·약관에 자동 수집 금지 조항 없음, IT동아: 목록 페이지는 robots.txt 허용, RSS 경로는 금지라 쓰지 않음).
"""

SOURCES = [
    {
        "id": "boannews",
        "name": "보안뉴스",
        "group": "국내언론사",
        "kind": "rss",
        "url": "https://www.boannews.com/rss/allArticle.xml",
        "security_source": True,
    },
    {
        "id": "dailysecu",
        "name": "데일리시큐",
        "group": "국내언론사",
        "kind": "rss",
        "url": "https://www.dailysecu.com/rss/allArticle.xml",
        "security_source": True,
    },
    {
        "id": "etnews_sec",
        "name": "전자신문",
        "group": "국내언론사",
        "kind": "html_etnews",
        "url": "https://www.etnews.com/news/section.html?id1=04&id2=045",
        "security_source": True,
    },
    {
        "id": "dt_ict",
        "name": "디지털타임스",
        "group": "국내언론사",
        "kind": "rss",
        "url": "https://www.dt.co.kr/rss/google/ict",
        "security_categories": ["보안/해킹", "보안·해킹", "보안"],
    },
    {
        "id": "digitaltoday",
        "name": "디지털투데이",
        "group": "국내언론사",
        "kind": "rss",
        "url": "https://www.digitaltoday.co.kr/rss/allArticle.xml",
    },
    {
        "id": "aitimes",
        "name": "AI타임스",
        "group": "국내언론사",
        "kind": "rss",
        "url": "https://www.aitimes.com/rss/allArticle.xml",
        "ai_source": True,
    },
    {
        "id": "bloter",
        "name": "블로터",
        "group": "국내언론사",
        "kind": "rss",
        "url": "https://www.bloter.net/rss/allArticle.xml",
    },
    {
        "id": "zdnet",
        "name": "지디넷코리아",
        "group": "국내언론사",
        "kind": "rss",
        "url": "https://feeds.feedburner.com/zdkorea",
    },
    {
        "id": "ddaily",
        "name": "디지털데일리",
        "group": "국내언론사",
        "kind": "html_ddaily",
        "url": "https://www.ddaily.co.kr/news",
        "pages": 2,   # 목록 1쪽은 약 15~20건(낮 시간 3~4시간 분량)이라 2쪽까지 읽음
    },
    {
        "id": "itchosun",
        "name": "IT조선",
        "group": "국내언론사",
        "kind": "rss",
        "url": "https://it.chosun.com/rss/allArticle.xml",   # 최근 50건(약 하루 분량)
    },
    {
        "id": "itdonga",
        "name": "IT동아",
        "group": "국내언론사",
        "kind": "html_itdonga",
        "url": "https://it.donga.com/news/",   # 목록 1쪽 10건 — 하루 약 7건이라 1쪽으로 충분
    },
]

SOURCE_BY_ID = {s["id"]: s for s in SOURCES}
