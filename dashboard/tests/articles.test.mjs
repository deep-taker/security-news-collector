// 기사 검색·RSS·새 기사 확인 로직 시험: node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { groupByEvent, validSince, searchFilter, buildRss, isDuplicate, titleSimilarity } from "../lib/articles.js";
import { fmtShort, fmt, dateWithDow } from "../lib/db.js";
import { renderMarkdown } from "../lib/md.js";

test("시각: 한국 시간 24시간제 'MM/DD HH:mm', 값 없으면 빈 문자열", () => {
  assert.equal(fmtShort("2026-10-26T08:11:00Z"), "10/26(월) 17:11");
  assert.equal(fmtShort("2026-10-26T15:05:00Z"), "10/27(화) 00:05");   // 자정 넘김 — 요일도 한국 날짜 기준
  assert.equal(fmtShort(null), "");
});

test("같은 사건 묶기: 사건마다 첫 기사만 남기고 나머지는 묶음으로", () => {
  const rows = [{ id: 1, event_id: 7 }, { id: 2 }, { id: 3, event_id: 7 }, { id: 4, event_id: 9 }, { id: 5, event_id: 8 }];
  const byEvent = { 7: [{ id: 1 }, { id: 3 }, { id: 30 }], 9: [{ id: 4 }] };      // 8은 묶음 정보 없음
  const { visible, shown, siblings } = groupByEvent(rows, byEvent);
  assert.deepEqual(visible.map((a) => a.id), [1, 2, 4, 5]);
  assert.deepEqual([...shown], [7, 9]);
  assert.deepEqual(siblings(rows[0]).map((b) => b.id), [3, 30]);
  assert.deepEqual(siblings(rows[3]), []);                                        // 같은 사건 기사 없음
  assert.deepEqual(siblings(rows[1]), []);
});

test("같은 기사(다른 주소) 판별: 제목 유사도·시간·숫자", () => {
  const A = (id, title, source_id, published_at) => ({ id, title, source_id, published_at });
  // 같은 매체가 1초 간격으로 두 번 올린 실적 기사 (숫자가 달라도 10분 안이면 같은 기사)
  const w1 = A(1, "윈스테크넷, 2026년 3분기 영업이익 43억1000만원…전년 동기 대비 25.7% 증가", "digitaltoday", "2026-11-02T08:32:08Z");
  const w2 = A(2, "윈스테크넷, 2026년 3분기 영업이익 43억900만원으로 전년동기 대비 42.8% 증가", "digitaltoday", "2026-11-02T08:32:09Z");
  assert.ok(isDuplicate(w1, w2));
  assert.ok(!isDuplicate(w1, { ...w2, source_id: "zdnet" }));                       // 다른 매체면 숫자가 어긋나 묶지 않음
  // 다른 매체의 같은 기사
  assert.ok(isDuplicate(A(3, "G마켓, e쿠폰 핀번호 무단 사용 정황 확인…KISA 신고", "ddaily", "2026-11-01T01:00:00Z"),
                        A(4, "지마켓, e쿠폰 핀번호 무단 사용 정황 확인…KISA 신고", "zdnet", "2026-11-01T01:08:00Z")));
  assert.ok(isDuplicate(A(5, "센스톤, 중기부 '스케일업 팁스' 선정…OT 보안 허브 고도화", "ddaily", "2026-11-01T01:00:00Z"),
                        A(6, "센스톤, 중기부 ‘2026년 스케일업 팁스’ 선정...OT 보안 허브 고도화 추진", "dailysecu", "2026-11-01T04:00:00Z")));
  // 연재 회차가 다르면 같은 기사가 아님
  assert.ok(!isDuplicate(A(7, "[정보보안 연재소설-로그아웃되지 않는 밤] 제59화 '로그아웃되지 않는 밤'", "dailysecu", "2026-11-01T01:00:00Z"),
                         A(8, "[정보보안 연재소설-로그아웃되지 않는 밤] 제60화 '로그아웃되지 않는 밤'", "dailysecu", "2026-11-02T01:00:00Z")));
  // 비슷한 형식의 다른 피해 기관 기사는 기준 아래
  assert.ok(titleSimilarity("한국재무설계협회도 더존비즈온 해킹 영향…개인정보 유출 가능성 공지", "중부발전서비스도 더존비즈온 해킹 영향…임직원 개인정보 유출 가능성") < 0.72);
  assert.ok(!isDuplicate(A(9, "같은 제목 기사", "a", "2026-11-01T00:00:00Z"), A(10, "같은 제목 기사", "b", "2026-11-03T00:00:00Z")));  // 36시간 넘음
});

test("같은 사건 묶기: 사건 번호가 없어도 제목이 거의 같은 기사는 첫 기사 아래로", () => {
  const rows = [
    { id: 1, title: "윈스테크넷, 2026년 3분기 영업이익 43억1000만원…전년 동기 대비 25.7% 증가", source_id: "digitaltoday", published_at: "2026-11-02T08:32:08Z" },
    { id: 2, title: "윈스테크넷, 2026년 3분기 영업이익 43억900만원으로 전년동기 대비 42.8% 증가", source_id: "digitaltoday", published_at: "2026-11-02T08:32:09Z" },
    { id: 3, title: "하이브, 외부 업체 문서 미리보기 솔루션 통해 전·현직 직원 개인정보 유출", source_id: "zdnet", published_at: "2026-11-02T08:00:00Z" },
  ];
  const g = groupByEvent(rows, {});
  assert.deepEqual(g.visible.map((a) => a.id), [1, 3]);
  assert.deepEqual(g.siblings(rows[0]).map((b) => b.id), [2]);
  assert.equal(g.merged, 1);
  assert.deepEqual(groupByEvent(rows, {}, { similar: false }).visible.map((a) => a.id), [1, 2, 3]);   // '모두 펼치기'
});

test("새 기사 확인: since 형식·범위 검사", () => {
  const now = Date.parse("2026-10-26T12:00:00Z");
  assert.equal(validSince("2026-10-26T11:59:00.000Z", now), true);
  assert.equal(validSince("2026-10-22T11:59:00Z", now), false);                 // 3일 초과
  assert.equal(validSince("2026-10-27T12:00:00Z", now), false);                 // 미래
  for (const bad of ["", "bad", "2026-10-26", "2026-10-26T11:00:00+09:00", "2026-10-26T11:00:00Z&x=1", null])
    assert.equal(validSince(bad, now), false);
});

test("검색 조건: 제목·요약 둘 다, 구문을 깨는 문자는 제거", () => {
  assert.equal(searchFilter("랜섬웨어"), "(title.ilike.*랜섬웨어*,summary_line.ilike.*랜섬웨어*)");
  const f = searchFilter("a,b).or=(x*");
  assert.ok(!/[(),*]/.test(f.slice(1, -1).replace(/title\.ilike\.\*|summary_line\.ilike\.\*|\*,|\*$/g, "")));
  assert.equal(searchFilter("***"), null);
});

test("RSS: 판마다 항목, 제목은 본문 첫 제목, 본문은 정리된 HTML, XML 깨짐 방지", () => {
  const xml = buildRss([
    { date: "2026-10-26", edition: "pm", created_at: "2026-10-26T08:54:00Z",
      markdown: "# 정보보안 브리핑 2026-10-26 (월) 18시판\n\n- [기사](https://www.boannews.com/a) <script>x</script> ]]> 끝" },
    { date: "2026-10-26", edition: "am", created_at: "2026-10-25T20:48:00Z", markdown: "제목 없음 & 기호" },
  ], renderMarkdown);
  assert.equal((xml.match(/<item>/g) || []).length, 2);
  assert.ok(xml.includes("<title>정보보안 브리핑 2026-10-26 (월) 18시판</title>"));
  assert.ok(xml.includes("<title>정보보안 브리핑 2026-10-26 06시판</title>"));
  assert.ok(xml.includes("<link>https://information-security-briefing.vercel.app/b/2026-10-26-pm</link>"));
  assert.ok(!xml.includes("<script>"));
  assert.equal((xml.match(/<!\[CDATA\[/g) || []).length, (xml.match(/]]>/g) || []).length);   // CDATA 균형
});

import { eventGroups, eventDate } from "../lib/articles.js";
test("행사 일정: 진행 중은 다가오는 쪽, 날짜 표시(요일·기간)", () => {
  const rows = [{ id: 1, start_date: "2026-10-26", end_date: "2026-10-28" }, { id: 2, start_date: "2026-10-20" },
                { id: 3, start_date: "2026-11-05" }, { id: 4, start_date: "2026-10-25", end_date: "2026-10-26" }];
  const { upcoming, past } = eventGroups(rows, "2026-10-27");
  assert.deepEqual(upcoming.map((e) => e.id), [1, 3]);
  assert.deepEqual(past.map((e) => e.id), [4, 2]);
  assert.equal(eventDate({ start_date: "2026-10-28" }), "10/28(수)");
  assert.equal(eventDate({ start_date: "2026-10-26", end_date: "2026-10-28" }), "10/26(월)~10/28(수)");
});

test("날짜 뒤 요일 (2026-10-31)", () => {
  assert.equal(dateWithDow("2026-10-31"), "2026-10-31 (토)");
  assert.equal(dateWithDow("2026-11-02"), "2026-11-02 (월)");
  assert.equal(fmt("2026-10-31T15:30:00Z"), "2026-11-01(일) 00:30");
  assert.equal(fmt(null), "");
});
