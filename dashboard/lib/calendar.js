// 행사 일정 달력 (2026-10-29 사용자 요청: 상단 '행사 일정'을 달력 형태로). 순수 함수 — 시험: tests/calendar.test.mjs
// 날짜는 모두 'YYYY-MM-DD' 한국 날짜 문자열. 주는 일요일부터 시작.

const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;

// '2026-10' 형식만 받고, 아니면 기본 달(오늘이 든 달)
export function parseMonth(m, today) {
  return /^\d{4}-(0[1-9]|1[0-2])$/.test(m || "") ? m : today.slice(0, 7);
}

export function shiftMonth(m, delta) {
  const d = new Date(`${m}-01T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() + delta);
  return iso(d).slice(0, 7);
}

// 그달 1일·말일
export function monthRange(m) {
  const first = `${m}-01`;
  const last = new Date(`${shiftMonth(m, 1)}-01T00:00:00Z`);
  last.setUTCDate(0);
  return { first, last: iso(last) };
}

// 달력 칸: [{ weeks: [[{ date, day, inMonth, today, events: [...] } x7] ...] }]
// 여러 날 행사는 걸친 날마다 넣는다 (start ≤ 날짜 ≤ end). 같은 날 안에서는 주요 행사 먼저 → 이름순.
export function buildMonth(m, events, today) {
  const { first, last } = monthRange(m);
  const start = new Date(`${first}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - start.getUTCDay());   // 그 주 일요일
  const end = new Date(`${last}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() + (6 - end.getUTCDay()));   // 그 주 토요일
  const weeks = [];
  for (const d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    const date = iso(d);
    if (d.getUTCDay() === 0) weeks.push([]);
    const evs = events.filter((e) => e.start_date <= date && date <= (e.end_date || e.start_date))
      .sort((a, b) => (b.major === true) - (a.major === true) || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    weeks.at(-1).push({ date, day: d.getUTCDate(), inMonth: date.slice(0, 7) === m, today: date === today, events: evs });
  }
  return weeks;
}

// 그달에 걸친 행사 목록 (달력 아래 목록·휴대폰용), 시작일순
export function monthEvents(m, events) {
  const { first, last } = monthRange(m);
  return events.filter((e) => e.start_date <= last && (e.end_date || e.start_date) >= first)
    .sort((a, b) => (a.start_date < b.start_date ? -1 : a.start_date > b.start_date ? 1 : a.name < b.name ? -1 : 1));
}
