import { q } from "../../lib/db";
import { allowed } from "../../lib/md";
import { eventGroups, eventDate } from "../../lib/articles";

export const dynamic = "force-dynamic";
export const metadata = { title: "행사 일정 · 정보보안 브리핑" };

// 국내 보안 행사 일정 — 브리핑 작업이 기사에서 뽑아 쌓은 것 (앞으로 60일 + 지난 30일)
export default async function Events() {
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);   // 한국 날짜
  const from = new Date(Date.parse(today) - 30 * 86400e3).toISOString().slice(0, 10);
  const to = new Date(Date.parse(today) + 60 * 86400e3).toISOString().slice(0, 10);
  let rows = [];
  try {
    ({ rows } = await q("security_events", {
      select: "id,name,start_date,end_date,place,organizer,url,major,note",
      and: `(start_date.gte.${from},start_date.lte.${to})`, order: "start_date.asc,name.asc", limit: "300",
    }, { revalidate: 300 }));
  } catch { rows = []; }
  const { upcoming, past } = eventGroups(rows, today);
  const Row = ({ e }) => (
    <tr>
      <td className="muted meta when" style={{ whiteSpace: "nowrap" }}>{eventDate(e)}</td>
      <td>
        {allowed(e.url || "") ? <a href={e.url} target="_blank" rel="noopener noreferrer">{e.name}</a> : <span>{e.name}</span>}
        {e.major && <> <span className="tag new">주요</span></>}
        {e.note && <div className="line">{e.note}</div>}
      </td>
      <td className="muted meta">{[e.place, e.organizer].filter(Boolean).join(" · ")}</td>
    </tr>
  );
  const Table = ({ list }) => (
    <table className="articles">
      <thead><tr><th style={{ width: 130 }}>일정</th><th>행사</th><th style={{ width: 220 }}>장소 · 주최</th></tr></thead>
      <tbody>{list.map((e) => <Row key={e.id} e={e} />)}</tbody>
    </table>
  );
  return (
    <>
      <h1 style={{ fontSize: "1.3rem", marginTop: 0 }}>보안 행사 일정 (국내)</h1>
      <p className="muted">수집한 기사에서 브리핑 작업이 뽑은 행사입니다(하루 3회 갱신). 기사에 날짜가 나온 행사만 싣고, 링크는 행사를 다룬 기사입니다. 참가 전 주최 측 공지를 확인하세요.</p>
      <h2 className="sec">다가오는 행사</h2>
      {upcoming.length ? <Table list={upcoming} /> : <p className="empty">앞으로 60일 안에 확인된 행사가 없습니다.</p>}
      {past.length > 0 && (<><h2 className="sec">지난 행사 (30일)</h2><Table list={past} /></>)}
    </>
  );
}
