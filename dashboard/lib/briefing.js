// 브리핑 HTML을 절(h2) 단위로 나눠 탭으로 보여 주기 위한 순수 함수 (시험: tests/briefing.test.mjs)

const TAB_IDS = [
  ["주요 사건", "main"], ["핵심 사건", "main"], ["기타 사", "other"], ["AI 보안", "ai"],
  ["국방", "defense"], ["정책", "policy"], ["업계", "industry"], ["보안 행사", "events"], ["다음 주", "next"], ["수집 상태", "status"],
];

// 절 안 항목 수: 사건 제목(h3)이 있으면 h3 수(그 아래 설명 목록은 세지 않음), 없으면 맨 바깥 목록의 li (중첩 목록 제외)
export function countItems(html) {
  const h3 = (html.match(/<h3[\s>]/g) || []).length;
  if (h3) return h3;
  let n = 0, depth = 0;
  for (const m of html.matchAll(/<(\/?)(ul|ol|li)[\s>]/g)) {
    if (m[2] !== "li") depth += m[1] ? -1 : 1;
    else if (!m[1] && depth === 1) n += 1;
  }
  return n;
}

// { head: 첫 h2 앞 HTML(제목·대상 줄), tabs: [{ id, title, html, count }] }
export function splitSections(html) {
  const parts = html.split(/(?=<h2[\s>])/);
  const head = parts[0].startsWith("<h2") ? "" : parts.shift();
  const used = new Set();
  const tabs = parts.map((p, i) => {
    const m = p.match(/^<h2[^>]*>([\s\S]*?)<\/h2>/);
    const title = (m ? m[1] : "").replace(/<[^>]+>/g, "").trim() || `절 ${i + 1}`;
    let id = TAB_IDS.find(([k]) => title.includes(k))?.[1] || `s${i + 1}`;
    if (used.has(id)) id = `${id}${i + 1}`;
    used.add(id);
    const body = m ? p.slice(m[0].length) : p;
    return { id, title, html: body, count: countItems(body) };
  });
  return { head, tabs };
}

// HTML 문자 참조를 글자로 되돌린다. 뽑은 제목·주소는 React가 다시 이스케이프하므로, 되돌리지 않으면
// 'LIG D&A'가 'LIG D&amp;A'로 보이고 '&'가 든 주소가 깨진다 (2026-10-27 수정).
export function decodeEntities(s) {
  return s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (m, e) => {
    const k = e.toLowerCase();
    if (k[0] === "#") {
      const n = k[1] === "x" ? parseInt(k.slice(2), 16) : parseInt(k.slice(1), 10);
      return Number.isFinite(n) && n > 0 && n <= 0x10ffff ? String.fromCodePoint(n) : m;
    }
    return { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" }[k];
  });
}

// 오른쪽 보조 칸 '이번 판 주요 사건': 주요 사건 절의 사건 제목(h3 안 대표 기사 링크)만 뽑는다 (2026-10-27)
// renderMarkdown을 거친 HTML만 받으므로 주소는 이미 허용 목록 검사를 통과한 것.
export function mainIncidents(tabs) {
  const main = tabs.find((t) => t.id === "main");
  if (!main) return [];
  const out = [];
  for (const m of main.html.matchAll(/<h3[^>]*>([\s\S]*?)<\/h3>/g)) {
    const a = m[1].match(/<a [^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/);
    const text = decodeEntities((a ? a[2] : m[1]).replace(/<[^>]+>/g, "")).trim();
    if (text) out.push({ href: a && a[1] !== "#" ? decodeEntities(a[1]) : "", text, follow: /\[후속\]/.test(m[1]) });
  }
  return out;
}
