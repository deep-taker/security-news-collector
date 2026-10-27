// 기사 검색·RSS·새 기사 확인 로직 시험: node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { groupByEvent, validSince, searchFilter, buildRss } from "../lib/articles.js";
import { fmtShort } from "../lib/db.js";
import { renderMarkdown } from "../lib/md.js";

test("시각: 한국 시간 24시간제 'MM/DD HH:mm', 값 없으면 빈 문자열", () => {
  assert.equal(fmtShort("2026-10-26T08:11:00Z"), "10/26 17:11");
  assert.equal(fmtShort("2026-10-26T15:05:00Z"), "10/27 00:05");   // 자정 넘김
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
  assert.ok(xml.includes("<link>https://briefing-security.vercel.app/b/2026-10-26-pm</link>"));
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
