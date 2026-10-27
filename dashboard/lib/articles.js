// 기사 검색 페이지·RSS·새 기사 확인에서 쓰는 순수 함수 (단위 시험 대상: tests/articles.test.mjs)

// 같은 사건 묶기: 이 쪽의 기사 중 같은 사건은 첫 기사만 남기고, 나머지는 첫 기사 아래 묶음으로 보여 준다.
// byEvent: { 사건번호: [그 사건의 기사들(최신순)] } — 묶음 정보가 없는 사건의 기사는 그대로 둔다.
export function groupByEvent(rows, byEvent) {
  const shown = new Set();
  const visible = rows.filter((a) => {
    if (!a.event_id || !byEvent[a.event_id]) return true;
    if (shown.has(a.event_id)) return false;
    shown.add(a.event_id);
    return true;
  });
  const siblings = (a) => (a.event_id && byEvent[a.event_id] ? byEvent[a.event_id].filter((b) => b.id !== a.id) : []);
  return { visible, shown, siblings };
}

// '새 기사' 확인 주소의 since 검사: ISO 형식(UTC), 미래가 아니고 3일 이내
export function validSince(since, now = Date.now()) {
  if (!/^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/.test(since || "")) return false;
  const t = Date.parse(since);
  return !Number.isNaN(t) && t <= now + 60e3 && now - t <= 3 * 86400e3;
}

// 검색어를 PostgREST or 조건으로 (구문을 깨는 문자는 공백)
export function searchFilter(text) {
  const t = (text || "").replace(/[*,()."'\\:]/g, " ").trim();
  return t ? `(title.ilike.*${t}*,summary_line.ilike.*${t}*)` : null;
}

// 브리핑 RSS
const LABEL = { am: "06시판", noon: "12시판", pm: "18시판", week: "주간 요약" };
const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const cdata = (s) => `<![CDATA[${String(s).replace(/]]>/g, "]]]]><![CDATA[>")}]]>`;

export function buildRss(rows, render, site = "https://briefing-security.vercel.app") {
  const items = rows.map((b) => {
    const id = `${b.date}-${b.edition}`;
    const heading = (b.markdown || "").match(/^#\s+(.+)$/m)?.[1] || `정보보안 브리핑 ${b.date} ${LABEL[b.edition] || ""}`.trim();
    return `<item>
  <title>${esc(heading)}</title>
  <link>${site}/b/${id}</link>
  <guid isPermaLink="true">${site}/b/${id}</guid>
  <pubDate>${new Date(b.created_at).toUTCString()}</pubDate>
  <description>${cdata(render(b.markdown))}</description>
</item>`;
  }).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>정보보안 브리핑</title>
  <link>${site}/</link>
  <atom:link href="${site}/rss.xml" rel="self" type="application/rss+xml"/>
  <description>국내 보안 매체 9곳 기사로 만드는 정보보안 브리핑 (하루 3회: 06·12·18시)</description>
  <language>ko</language>
${items}
</channel>
</rss>`;
}

// 행사 일정: 오늘(한국 날짜) 기준 다가오는(진행 중 포함) / 지난 행사
export function eventGroups(rows, today) {
  const end = (e) => e.end_date || e.start_date;
  return {
    upcoming: rows.filter((e) => end(e) >= today).sort((a, b) => (a.start_date < b.start_date ? -1 : a.start_date > b.start_date ? 1 : 0)),
    past: rows.filter((e) => end(e) < today).sort((a, b) => (a.start_date < b.start_date ? 1 : -1)),
  };
}

const DOW = ["일", "월", "화", "수", "목", "금", "토"];
const md = (d) => { const t = new Date(d + "T00:00:00Z"); return `${d.slice(5, 7)}/${d.slice(8, 10)}(${DOW[t.getUTCDay()]})`; };
export function eventDate(e) {
  return e.end_date && e.end_date !== e.start_date ? `${md(e.start_date)}~${md(e.end_date)}` : md(e.start_date);
}
