// 기사 검색 페이지·RSS·새 기사 확인에서 쓰는 순수 함수 (단위 시험 대상: tests/articles.test.mjs)

// 제목 유사도: 글자·숫자만 남긴 제목의 두 글자 묶음 일치율(다이스 계수, 0~1)
const normTitle = (s) => String(s || "").toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
function bigrams(s) {
  const m = new Map();
  for (let i = 0; i < s.length - 1; i++) { const k = s.slice(i, i + 2); m.set(k, (m.get(k) || 0) + 1); }
  return m;
}
export function titleSimilarity(a, b) {
  const A = bigrams(normTitle(a)), B = bigrams(normTitle(b));
  let hit = 0, total = 0;
  for (const [k, v] of A) { hit += Math.min(v, B.get(k) || 0); total += v; }
  for (const v of B.values()) total += v;
  return total ? (2 * hit) / total : 0;
}
// 제목 속 숫자가 서로 어긋나는지 (한쪽이 다른 쪽을 포함하면 어긋나지 않음) — 연재 회차·다른 회사 공시 구분용
function numbersConflict(a, b) {
  const na = new Set(String(a || "").match(/\d+/g) || []), nb = new Set(String(b || "").match(/\d+/g) || []);
  const sub = (x, y) => [...x].every((n) => y.has(n));
  return !(sub(na, nb) || sub(nb, na));
}
const when = (a) => Date.parse(a.published_at || a.collected_at || "") || 0;
export const DUP_SIM = 0.72;          // 2주치 실제 기사로 맞춘 기준 (이 이상은 거의 모두 같은 기사, 그 아래엔 다른 피해 기관 등 섞임)
export const DUP_HOURS = 36;
// 같은 기사(다른 주소): 제목이 매우 비슷하고 36시간 안 + 제목 숫자가 어긋나지 않음.
// 같은 매체가 10분 안에 다시 올린 기사는 숫자가 달라도 같은 기사로 본다(정정·중복 송고).
export function isDuplicate(a, b) {
  const gap = Math.abs(when(a) - when(b));
  if (!when(a) || !when(b) || gap > DUP_HOURS * 3600e3) return false;
  if (titleSimilarity(a.title, b.title) < DUP_SIM) return false;
  if (a.source_id && a.source_id === b.source_id && gap <= 10 * 60e3) return true;
  return !numbersConflict(a.title, b.title);
}

// 같은 사건 묶기: 이 쪽의 기사 중 같은 사건은 첫 기사만 남기고, 나머지는 첫 기사 아래 묶음으로 보여 준다.
// byEvent: { 사건번호: [그 사건의 기사들(최신순)] } — 묶음 정보가 없는 사건의 기사는 그대로 둔다.
// 브리핑 전(분류 대기)이라 사건 번호가 없는 기사도 제목이 거의 같으면(isDuplicate) 먼저 나온 기사 아래로 묶는다.
export function groupByEvent(rows, byEvent, { similar = true } = {}) {
  const shown = new Set();
  const byEv = rows.filter((a) => {
    if (!a.event_id || !byEvent[a.event_id]) return true;
    if (shown.has(a.event_id)) return false;
    shown.add(a.event_id);
    return true;
  });
  const evSib = (a) => (a.event_id && byEvent[a.event_id] ? byEvent[a.event_id].filter((b) => b.id !== a.id) : []);
  const extra = new Map();   // 대표 기사 id → 제목이 거의 같은 기사들
  const visible = [];
  for (const a of byEv) {
    const head = similar && visible.find((r) => [r, ...(extra.get(r.id) || [])].some((m) => isDuplicate(m, a)));
    if (head) extra.set(head.id, [...(extra.get(head.id) || []), a]);
    else visible.push(a);
  }
  const siblings = (a) => {
    const seen = new Set([a.id]), out = [];
    for (const b of [...evSib(a), ...(extra.get(a.id) || []).flatMap((m) => [m, ...evSib(m)])])
      if (!seen.has(b.id)) { seen.add(b.id); out.push(b); }
    return out;
  };
  return { visible, shown, siblings, merged: byEv.length - visible.length };
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
