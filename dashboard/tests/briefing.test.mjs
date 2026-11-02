// 브리핑 절 → 탭 나누기 시험
import { test } from "node:test";
import assert from "node:assert/strict";
import { splitSections, countItems, mainIncidents } from "../lib/briefing.js";
import { renderMarkdown } from "../lib/md.js";

test("절을 탭으로: 제목·대상 줄은 머리말, 절 이름으로 탭 id, 항목 수", () => {
  const md = `# 정보보안 브리핑 2026-10-27 (화) 12시판
대상: … · 후보 10건

## 🔴 주요 사건·사고
### [A](https://www.boannews.com/a "보도: 보안뉴스")
줄1
줄2
### [B](https://www.boannews.com/b "보도: 보안뉴스")
줄1
줄2

## 📌 기타 사건·사고
- **[C](https://zdnet.co.kr/c "보도: 지디넷코리아")**
  줄1
  줄2

## 🤖 AI 보안
- **[D](https://www.aitimes.com/d "보도: AI타임스")**
  줄1
  줄2

## 🪖 국방·방산보안
- **[G](https://www.boannews.com/g "보도: 보안뉴스")**
  줄1
  줄2

## 🏢 업계 동향
- 보도자료성 기사 — 주요 항목:
  - [E](https://www.etnews.com/e)
  - [F](https://www.etnews.com/f)
`;
  const { head, tabs } = splitSections(renderMarkdown(md));
  assert.match(head, /<h1>정보보안 브리핑/);
  assert.ok(!head.includes("<h2"));
  assert.deepEqual(tabs.map((t) => t.id), ["main", "other", "ai", "defense", "industry"]);
  assert.deepEqual(tabs.map((t) => t.count), [2, 1, 1, 1, 1]);          // 업계 동향 중첩 목록은 1건으로
  assert.equal(tabs[0].title, "🔴 주요 사건·사고");
  assert.ok(!tabs[0].html.includes("<h2"));
});

test("옛 형식·주간 요약 절 이름도 탭으로, 같은 이름은 겹치지 않게", () => {
  const html = renderMarkdown("# t\n\n## 🔴 이번 주 핵심 사건·사고\n### x\n\n## 👀 다음 주 지켜볼 것\n- y\n\n## ⚠️ 수집 상태\n- z\n\n## 기타\n- a\n\n## 기타\n- b\n");
  const { tabs } = splitSections(html);
  assert.deepEqual(tabs.map((t) => t.id), ["main", "next", "status", "s4", "s5"]);
});

test("항목 수: 사건 제목(h3)이 있으면 h3 수, 없으면 바깥 목록 li", () => {
  assert.equal(countItems("<h3>a</h3><ul><li>설명</li><li>보도</li></ul><h3>b</h3><ul><li>c</li></ul>"), 2);   // 옛 형식 주요 사건
  assert.equal(countItems("<ul><li>x<ul><li>y</li></ul></li><li>z</li></ul>"), 2);
});

test("mainIncidents: 주요 사건 절의 사건 제목과 대표 기사 링크만", () => {
  const html = renderMarkdown(`# 제목\n## 🔴 주요 사건·사고\n### [가 사건](https://www.boannews.com/a "보도: 보안뉴스") [후속]\n1줄\n2줄\n\n### 링크 없는 사건\n설명\n## 📌 기타 사건·사고\n- **[다 사건](https://www.boannews.com/c "보도: 보안뉴스")**\n`);
  const r = mainIncidents(splitSections(html).tabs);
  assert.equal(r.length, 2);
  assert.equal(r[0].text, "가 사건"); assert.equal(r[0].href, "https://www.boannews.com/a"); assert.equal(r[0].follow, true);
  assert.equal(r[1].text, "링크 없는 사건"); assert.equal(r[1].href, "");
  assert.deepEqual(mainIncidents([]), []);
});

test("mainIncidents: 제목·주소의 & 같은 문자가 한 번만 이스케이프되도록 되돌림", () => {
  const html = renderMarkdown(`# 제목\n## 🔴 주요 사건·사고\n### [LIG D&A 제재 \"집행정지\" 불발](https://www.boannews.com/media/view.asp?idx=1&kind=1 "보도: 보안뉴스")\n1줄\n`);
  const [r] = mainIncidents(splitSections(html).tabs);
  assert.equal(r.text, 'LIG D&A 제재 "집행정지" 불발');
  assert.equal(r.href, "https://www.boannews.com/media/view.asp?idx=1&kind=1");
});

test("decodeEntities: 한 번만 되돌린다 (이중 참조는 글자 그대로)", async () => {
  const { decodeEntities } = await import("../lib/briefing.js");
  assert.equal(decodeEntities("a &amp;lt; b &#39;c&#x27; &bogus;"), "a &lt; b 'c' &bogus;");
});

test("칼럼 필자: 제목 링크 뒤에 '[소속, 직책, 성명]'을 링크 없이", async () => {
  const { authorLabel, addColumnAuthors, linkUrls } = await import("../lib/briefing.js");
  const { renderMarkdown } = await import("../lib/md.js");
  assert.equal(authorLabel({ org: "나루시큐리티", position: "대표", name: "김혁준" }), "[나루시큐리티, 대표, 김혁준]");
  assert.equal(authorLabel({ org: "", position: "CISO", name: "이혁중" }), "[CISO, 이혁중]");
  assert.equal(authorLabel({}), "");
  assert.equal(authorLabel(null), "");
  const md = '## ✍️ 칼럼·기고\n- **[(보안칼럼) 인간중심 사이버보안의 몰락](https://zdnet.co.kr/view/?no=1&a=2 "보도: 지디넷코리아")**\n  1줄\n  2줄\n\n- **[(이슈칼럼) 다른 글](https://www.boannews.com/x "보도: 보안뉴스")**\n  1줄\n  2줄\n';
  const html = renderMarkdown(md);
  assert.deepEqual(linkUrls(html), ["https://zdnet.co.kr/view/?no=1&a=2", "https://www.boannews.com/x"]);
  const out = addColumnAuthors(html, { "https://zdnet.co.kr/view/?no=1&a=2": { org: "나루<b>", position: "대표", name: "김혁준" } });
  assert.match(out, /인간중심 사이버보안의 몰락<\/a><span class="author"> \[나루&lt;b&gt;, 대표, 김혁준\]<\/span><span class="src-m">/);
  assert.ok(!/<span class="author">[^<]*<a/.test(out));                 // 필자 부분은 링크 아님
  assert.equal((out.match(/class="author"/g) || []).length, 1);           // 필자 정보 없는 글은 그대로
  assert.equal(addColumnAuthors(html, {}), html);
});
