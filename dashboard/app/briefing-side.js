import { q } from "../lib/db";
import { allowed } from "../lib/md";
import { eventDate } from "../lib/articles";

// 넓은 화면(1440px 이상) 오른쪽 보조 칸 — 순서: 이번 판 주요 사건 → 최근 진행 중 사건 → 다가오는 보안 행사(맨 끝) (사용자 결정 2026-10-27)
// 제목은 모두 대표 기사(행사는 행사 기사)로 연결한다.
const Link = ({ href, children }) =>
  href && allowed(href) ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>;

export default async function BriefingSide({ incidents }) {
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  const since = new Date(Date.parse(today) - 7 * 86400e3).toISOString().slice(0, 10);
  const until = new Date(Date.parse(today) + 14 * 86400e3).toISOString().slice(0, 10);
  let ongoing = [], upcoming = [];
  try {
    const [ev, se] = await Promise.all([
      q("events", { select: "id,title,category,last_seen", last_seen: `gte.${since}`, order: "last_seen.desc,id.desc", limit: "20" }, { revalidate: 300 }),
      q("security_events", { select: "id,name,start_date,end_date,url,major", and: `(start_date.gte.${today},start_date.lte.${until})`,
        order: "start_date.asc,name.asc", limit: "8" }, { revalidate: 300 }),
    ]);
    upcoming = se.rows;
    // 이번 판 주요 사건과 같은 사건은 '진행 중 사건'에서 뺀다 (대표 기사 주소 → 사건 번호로 대조)
    const hrefs = incidents.map((x) => x.href).filter(Boolean);
    const shown = new Set();
    if (hrefs.length) {
      const { rows } = await q("articles", { select: "event_id", url: `in.(${hrefs.map((h) => `"${h.replace(/"/g, "")}"`).join(",")})` }, { revalidate: 300 });
      for (const a of rows) if (a.event_id) shown.add(a.event_id);
    }
    const list = ev.rows.filter((e) => !shown.has(e.id)).slice(0, 6);
    const ids = list.map((e) => e.id);
    const rep = {};
    if (ids.length) {
      const { rows } = await q("articles", { select: "event_id,url,collected_at", event_id: `in.(${ids.join(",")})`, order: "collected_at.desc", limit: "200" }, { revalidate: 300 });
      for (const a of rows) rep[a.event_id] ||= a.url;   // 사건마다 가장 최근 기사
    }
    ongoing = list.map((e) => ({ ...e, url: rep[e.id] || "" }));
  } catch { /* 보조 칸은 실패해도 본문에 영향 없음 */ }
  return (
    <aside className="side">
      <div className="box">
        {incidents.length > 0 && (<>
          <h4>🔴 이번 판 주요 사건</h4>
          <ol>{incidents.map((x, i) => <li key={i}><Link href={x.href}>{x.text}</Link></li>)}</ol>
        </>)}
        <h4>🔁 최근 진행 중 사건</h4>
        {ongoing.length ? (
          <ul>{ongoing.map((e) => <li key={e.id}>{e.category && <span className="tag">{e.category}</span>}<Link href={e.url}>{(e.title || "").split(" — ")[0]}</Link></li>)}</ul>
        ) : <p className="empty2">최근 7일 동안 이어진 사건이 없습니다.</p>}
        <h4>📅 다가오는 보안 행사</h4>
        {upcoming.length ? (
          <ul>{upcoming.map((e) => <li key={e.id}><span className="when">{eventDate(e)}</span> <Link href={e.url}>{e.name}</Link>{e.major && <> <span className="tag new">주요</span></>}</li>)}</ul>
        ) : <p className="empty2">앞으로 14일 안에 수집된 국내 보안 행사가 없습니다. <a href="/events">행사 일정</a></p>}
      </div>
    </aside>
  );
}
