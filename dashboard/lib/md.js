import { Marked } from "marked";

// 취소선 문법 끔: GFM은 '~…~'·'~~…~~'를 취소선으로 바꿔 "3~4일 … 9~10월"이 "34일 … 910월" + 취소선으로 보였다
// (2026-11-03, 사용자 결정: 모든 화면에 취소선 글자 없음). 물결표는 글자 그대로 둔다.
const marked = new Marked({ tokenizer: { del() { return undefined; } } });

// 링크 허용 도메인: 수집 매체 11곳 (IT조선·IT동아는 it. 하위 주소만 — 본지 주소는 허용하지 않음) (collector/verify_briefing.py ARTICLE_DOMAINS와 같게 유지)
const ARTICLE_DOMAINS = ["boannews.com", "dailysecu.com", "etnews.com", "dt.co.kr", "digitaltoday.co.kr",
  "aitimes.com", "bloter.net", "zdnet.co.kr", "ddaily.co.kr", "it.chosun.com", "it.donga.com"];

export function allowed(href) {
  try {
    const u = new URL(href.replace(/&amp;/g, "&"));
    if (!["http:", "https:"].includes(u.protocol) || u.username || u.password || (u.port && !["80", "443"].includes(u.port))) return false;
    const h = u.hostname.toLowerCase();
    return ARTICLE_DOMAINS.some((d) => h === d || h.endsWith("." + d));
  } catch {
    return false;
  }
}

// 브리핑 마크다운 → HTML. 외부 기사 제목이 섞이므로 HTML 태그와 위험한 링크를 막는다.
export function renderMarkdown(md) {
  const escaped = (md || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  let html = marked.parse(escaped, { gfm: true, breaks: true });   // 2줄 요약: 줄바꿈을 그대로 줄로 (2026-10-27 형식)
  html = html.replace(/<\/?(?:del|s|strike)>/g, "");   // 혹시 남은 취소선 태그도 제거 (글자는 그대로 둠)
  html = html.replace(/href="([^"]*)"/gi, (m, href) => (allowed(href) ? m : 'href="#"'));
  // 이미지는 쓰지 않음: 외부 주소·javascript: 등을 막기 위해 대체 문자열만 남긴다
  html = html.replace(/<img\b[^>]*?\balt="([^"]*)"[^>]*>/gi, "$1").replace(/<img\b[^>]*>/gi, "");
  // 대표 기사 제목 링크의 '보도: …' 설명 → PC는 마우스를 올리면 바로 뜨는 말풍선, 휴대폰(마우스 없음)은 제목 옆 작은 글씨
  html = html.replace(/<a href="([^"]*)" title="(보도:[^"]*)">([\s\S]*?)<\/a>/g, (m, href, t, text) =>
    `<a href="${href}" class="has-src" data-src="${t}">${text}</a><span class="src-m"> · ${t.replace(/^보도:\s*/, "")}</span>`);
  // 항목 사이에 빈 줄이 있으면(느슨한 목록) 항목마다 <p>가 한 겹 더 씌워져, 제목 크기·간격 규칙(li > strong)이 안 먹고
  // 절마다 글자 크기·줄 모양이 달라졌다(2026-11-03 재발). 문단이 하나뿐인 항목은 <p>를 벗겨 빈 줄 유무와 관계없이 같은 구조로 만든다.
  html = html.replace(/<li>\s*<p>((?:(?!<\/?p>|<\/?li>)[\s\S])*)<\/p>\s*<\/li>/g, "<li>$1</li>");
  // 목록 항목 제목 뒤의 꼬리표(예: " [후속]")를 제목(굵은 글씨) 안으로 — 주요 사건(h3)처럼 제목 줄에 붙어 보이게.
  // 제목을 한 줄(블록)로 보이게 한 뒤 꼬리표가 본문 첫 줄 앞으로 내려가던 문제 (2026-10-28)
  html = html.replace(/<li><strong>([\s\S]*?)<\/strong>([^<\n]+?)<br>/g, (m, title, tail) => `<li><strong>${title}${tail}</strong><br>`);
  return html.replace(/<a href=/g, '<a target="_blank" rel="noopener noreferrer" href=');
}
