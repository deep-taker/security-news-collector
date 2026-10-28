// 브리핑 변환 시험: node --test tests/  (라이브러리 업데이트 때 결과가 바뀌면 실패)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { renderMarkdown } from "../lib/md.js";

const ATTACKS = [
  "[x](javascript:alert(1))", "[x](JaVaScRiPt:alert(1))", "[x]( javascript:alert(1))", "[x](data:text/html,<script>)",
  "[x](vbscript:msgbox(1))", "![i](javascript:alert(1))", "![i](https://evil.example/t.png)", "<script>alert(1)</script>",
  "<img src=x onerror=alert(1)>", "<a href=javascript:alert(1)>x</a>", "[x](https://a.kr/\"onmouseover=alert(1))",
  "<iframe src=//evil></iframe>", "<svg onload=alert(1)>", "[x](//evil.example)", "<style>body{}</style>",
  "**굵게** [정상](https://www.boannews.com/media/view.asp?idx=1&kind=1)",
];

// 태그 안의 속성만 검사 (본문 글자로 보이는 &lt;...&gt;는 안전)
const tags = (html) => html.match(/<[a-z][^>]*>/gi) || [];

test("공격 문자열: 실행 가능한 태그·속성·주소가 나오지 않음", () => {
  for (const a of ATTACKS) {
    const html = renderMarkdown(a);
    for (const t of tags(html)) {
      assert.match(t, /^<(p|a|strong|em|code|ul|ol|li|h[1-6]|blockquote|br|hr|pre|del|table|thead|tbody|tr|th|td)\b/i, `${a} → 허용 안 된 태그 ${t}`);
      assert.doesNotMatch(t, /\son[a-z]+=/i, `${a} → 이벤트 속성 ${t}`);
      const href = t.match(/href="([^"]*)"/i);
      if (href) assert.match(href[1], /^(https?:\/\/[^"\s]+|#)$/i, `${a} → 위험한 주소 ${href[1]}`);
    }
    assert.doesNotMatch(html, /<img|<script|<iframe|<svg|<style/i, a);
  }
});

test("수집 매체가 아닌 도메인 링크는 막힘", () => {
  for (const u of ["https://evil.example/a", "https://boannews.com.evil.io/", "https://user@www.boannews.com/a", "https://www.boannews.com:8443/a"]) {
    assert.match(renderMarkdown(`[x](${u})`), /href="#"/, u);
  }
  assert.match(renderMarkdown("[x](https://zdnet.co.kr/view/?no=1)"), /href="https:\/\/zdnet\.co\.kr\/view\/\?no=1"/);
});

test("정상 링크는 새 창·리퍼러 없이 열림", () => {
  const html = renderMarkdown("[보안뉴스](https://www.boannews.com/media/view.asp?idx=1&kind=1)");
  assert.match(html, /<a target="_blank" rel="noopener noreferrer" href="https:\/\/www\.boannews\.com\/media\/view\.asp\?idx=1&amp;kind=1">보안뉴스<\/a>/);
});

test("실제 브리핑 변환 결과가 저장된 기준과 같음", () => {
  const md = readFileSync(new URL("./fixtures/briefing.md", import.meta.url), "utf8");
  const out = new URL("./fixtures/briefing.expected.html", import.meta.url);
  const html = renderMarkdown(md);
  if (!existsSync(out) || process.env.UPDATE_SNAPSHOT) writeFileSync(out, html);
  assert.equal(html, readFileSync(out, "utf8"), "변환 결과가 바뀜 — 의도한 변경이면 UPDATE_SNAPSHOT=1 로 기준 갱신");
});

test("대표 기사 제목 링크: 보도 매체 말풍선·휴대폰 표시, 설명 문구 속 태그는 글자로", () => {
  const html = renderMarkdown('### [더존비즈온 침해](https://www.boannews.com/a "보도: 보안뉴스, 데일리시큐 외 4곳") [후속]\n\n- **[악성](https://evil.example/x "보도: <img src=x onerror=alert(1)>")**');
  assert.match(html, /<a target="_blank" rel="noopener noreferrer" href="https:\/\/www\.boannews\.com\/a" class="has-src" data-src="보도: 보안뉴스, 데일리시큐 외 4곳">더존비즈온 침해<\/a><span class="src-m"> · 보안뉴스, 데일리시큐 외 4곳<\/span>/);
  assert.ok(!/<img/i.test(html));              // 설명 문구의 태그는 실행되지 않음
  assert.ok(html.includes('href="#"'));         // 허용되지 않은 주소는 막힘
});
