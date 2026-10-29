// 행사 일정 달력 시험: node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseMonth, shiftMonth, monthRange, buildMonth, monthEvents } from "../lib/calendar.js";

test("달 주소 해석·이동·범위", () => {
  assert.equal(parseMonth("2026-11", "2026-10-29"), "2026-11");
  for (const bad of [undefined, "", "2026-13", "2026-1", "../x", "2026-10-01"]) assert.equal(parseMonth(bad, "2026-10-29"), "2026-10");
  assert.equal(shiftMonth("2026-12", 1), "2027-01");
  assert.equal(shiftMonth("2026-01", -1), "2025-12");
  assert.deepEqual(monthRange("2026-02"), { first: "2026-02-01", last: "2026-02-28" });
  assert.deepEqual(monthRange("2028-02"), { first: "2028-02-01", last: "2028-02-29" });
});

test("달력 칸: 일요일 시작, 앞뒤 주 포함, 여러 날 행사는 걸친 날마다", () => {
  const evs = [
    { id: 1, name: "나 포럼", start_date: "2026-10-28" },
    { id: 2, name: "가 컨퍼런스", start_date: "2026-10-30", end_date: "2026-11-02", major: true },
    { id: 3, name: "다 세미나", start_date: "2026-10-30" },
  ];
  const weeks = buildMonth("2026-10", evs, "2026-10-29");
  assert.equal(weeks.length, 5);                                  // 9/27(일) ~ 10/31(토)
  assert.ok(weeks.every((w) => w.length === 7));
  assert.equal(weeks[0][0].date, "2026-09-27");
  assert.equal(weeks[0][0].inMonth, false);
  const cell = (d) => weeks.flat().find((c) => c.date === d);
  assert.equal(cell("2026-10-29").today, true);
  assert.deepEqual(cell("2026-10-28").events.map((e) => e.id), [1]);
  assert.deepEqual(cell("2026-10-30").events.map((e) => e.id), [2, 3]);   // 주요 먼저
  assert.deepEqual(cell("2026-10-31").events.map((e) => e.id), [2]);
  const nov = buildMonth("2026-11", evs, "2026-10-29").flat();
  assert.deepEqual(nov.find((c) => c.date === "2026-11-02").events.map((e) => e.id), [2]);   // 앞달에 시작한 행사
});

test("그달 행사 목록: 그달에 걸친 행사만, 시작일순", () => {
  const evs = [
    { id: 1, name: "a", start_date: "2026-11-05" },
    { id: 2, name: "b", start_date: "2026-10-30", end_date: "2026-11-02" },
    { id: 3, name: "c", start_date: "2026-10-01" },
  ];
  assert.deepEqual(monthEvents("2026-11", evs).map((e) => e.id), [2, 1]);
  assert.deepEqual(monthEvents("2026-10", evs, 2).map((e) => e.id), [3, 2, 1]);   // 이번 달 + 다음 달
  assert.deepEqual(monthEvents("2026-09", evs, 2).map((e) => e.id), [3, 2]);
});
