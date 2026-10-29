import { q } from "../../lib/db";
import { allowed } from "../../lib/md";
import { eventDate } from "../../lib/articles";
import { parseMonth, shiftMonth, monthRange, buildMonth, monthEvents } from "../../lib/calendar";

export const dynamic = "force-dynamic";
export const metadata = { title: "행사 일정 · 정보보안 브리핑" };

const DOW = ["일", "월", "화", "수", "목", "금", "토"];
const Name = ({ e }) => (allowed(e.url || "")
  ? <a href={e.url} target="_blank" rel="noopener noreferrer" title={e.name}>{e.name}</a>
  : <span title={e.name}>{e.name}</span>);

// 한 달 달력
function Month({ m, rows, today }) {
  const [y, mo] = m.split("-");
  return (
    <section className="cal-month">
      <h2 className="cal-title">{y}년 {Number(mo)}월</h2>
      <table className="cal">
        <thead><tr>{DOW.map((d, i) => <th key={d} className={i === 0 ? "sun" : i === 6 ? "sat" : ""}>{d}</th>)}</tr></thead>
        <tbody>
          {buildMonth(m, rows, today).map((w) => (
            <tr key={w[0].date}>
              {w.map((c, i) => (
                <td key={c.date} className={[c.inMonth ? "" : "out", c.today ? "today" : "", i === 0 ? "sun" : i === 6 ? "sat" : ""].join(" ").trim()}>
                  <div className="d">{c.day}</div>
                  {c.events.map((e) => (
                    <div key={e.id} className={`ev${e.major ? " major" : ""}`}><Name e={e} /></div>
                  ))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

// 국내 보안 행사 일정 — 브리핑 작업이 기사에서 뽑아 쌓은 것.
// 월별 달력 (2026-10-29 사용자 요청), 이번 달과 다음 달을 한꺼번에 (2026-10-30 사용자 요청). 주소 ?m=YYYY-MM은 첫 달
export default async function Events({ searchParams }) {
  const sp = (await searchParams) || {};
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);   // 한국 날짜
  const m = parseMonth(Array.isArray(sp.m) ? sp.m[0] : sp.m, today);
  const m2 = shiftMonth(m, 1);
  const { first } = monthRange(m);
  const { last } = monthRange(m2);
  // 달력 앞뒤 주(지난달 말·다다음 달 초)와 앞달에 시작한 여러 날 행사까지 포함하도록 넉넉히
  const from = new Date(Date.parse(first) - 45 * 86400e3).toISOString().slice(0, 10);
  const to = new Date(Date.parse(last) + 7 * 86400e3).toISOString().slice(0, 10);
  let rows = [];
  try {
    ({ rows } = await q("security_events", {
      select: "id,name,start_date,end_date,place,organizer,url,major,note",
      and: `(start_date.gte.${from},start_date.lte.${to})`, order: "start_date.asc,name.asc", limit: "500",
    }, { revalidate: 300 }));
  } catch { rows = []; }
  const list = monthEvents(m, rows, 2);
  const label = (x) => `${Number(x.slice(5))}월`;
  return (
    <>
      <h1 style={{ fontSize: "1.3rem", marginTop: 0 }}>보안 행사 일정 (국내)</h1>
      <p className="muted">수집한 기사에서 브리핑 작업이 뽑은 행사입니다(하루 3회 갱신). 기사에 날짜가 나온 행사만 싣고, 링크는 행사를 다룬 기사입니다. 참가 전 주최 측 공지를 확인하세요.</p>
      <div className="cal-nav">
        <a href={`/events?m=${shiftMonth(m, -1)}`} aria-label="이전 달">‹ 이전 달</a>
        <strong>{m.slice(0, 4)}년 {label(m)} · {m2.slice(0, 4) !== m.slice(0, 4) ? `${m2.slice(0, 4)}년 ` : ""}{label(m2)}</strong>
        <a href={`/events?m=${m2}`} aria-label="다음 달">다음 달 ›</a>
        {m !== today.slice(0, 7) && <a className="cal-today" href="/events">이번 달</a>}
      </div>
      <Month m={m} rows={rows} today={today} />
      <Month m={m2} rows={rows} today={today} />
      <h2 className="sec">{label(m)}·{label(m2)} 행사 {list.length}건</h2>
      {list.length ? (
        <table className="articles">
          <thead><tr><th style={{ width: 130 }}>일정</th><th>행사</th><th style={{ width: 220 }}>장소 · 주최</th></tr></thead>
          <tbody>{list.map((e) => (
            <tr key={e.id}>
              <td className="muted meta when" style={{ whiteSpace: "nowrap" }}>{eventDate(e)}</td>
              <td><Name e={e} />{e.major && <> <span className="tag new">주요</span></>}{e.note && <div className="line">{e.note}</div>}</td>
              <td className="muted meta">{[e.place, e.organizer].filter(Boolean).join(" · ")}</td>
            </tr>))}
          </tbody>
        </table>
      ) : <p className="empty">두 달 안에 확인된 행사가 없습니다.</p>}
    </>
  );
}
