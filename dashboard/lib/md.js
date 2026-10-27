import { marked } from "marked";

// 링크 허용 도메인: 수집 매체 9곳 (collector/verify_briefing.py ARTICLE_DOMAINS와 같게 유지)
const ARTICLE_DOMAINS = ["boannews.com", "dailysecu.com", "etnews.com", "dt.co.kr", "digitaltoday.co.kr",
  "aitimes.com", "bloter.net", "zdnet.co.kr", "ddaily.co.kr"];

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
  html = html.replace(/href="([^"]*)"/gi, (m, href) => (allowed(href) ? m : 'href="#"'));
  // 이미지는 쓰지 않음: 외부 주소·javascript: 등을 막기 위해 대체 문자열만 남긴다
  html = html.replace(/<img\b[^>]*?\balt="([^"]*)"[^>]*>/gi, "$1").replace(/<img\b[^>]*>/gi, "");
  // 대표 기사 제목 링크의 '보도: …' 설명 → PC는 마우스를 올리면 바로 뜨는 말풍선, 휴대폰(마우스 없음)은 제목 옆 작은 글씨
  html = html.replace(/<a href="([^"]*)" title="(보도:[^"]*)">([\s\S]*?)<\/a>/g, (m, href, t, text) =>
    `<a href="${href}" class="has-src" data-src="${t}">${text}</a><span class="src-m"> · ${t.replace(/^보도:\s*/, "")}</span>`);
  return html.replace(/<a href=/g, '<a target="_blank" rel="noopener noreferrer" href=');
}
