import { q, SOURCES, fmtShort } from "../../lib/db";
import { allowed } from "../../lib/md";

export const dynamic = "force-dynamic";
export const metadata = { title: "칼럼·기고 · 정보보안 브리핑" };

// 보안 분야 칼럼·기고 (브리핑 작업이 `column`으로 분류한 기사) — 최근 30일, 최신순 (사용자 결정 2026-10-31)
export default async function Columns() {
  const since = new Date(Date.now() - 30 * 86400e3).toISOString();
  let rows = [];
  try {
    ({ rows } = await q("articles", {
      select: "id,title,url,source_id,published_at,collected_at,summary_line",
      label: "eq.column", collected_at: `gte.${since}`, order: "collected_at.desc,id.desc", limit: "200",
    }, { revalidate: 300 }));
  } catch { rows = []; }
  return (
    <>
      <h1 style={{ fontSize: "1.3rem", marginTop: 0 }}>칼럼·기고 (보안 분야)</h1>
      <p className="muted">수집한 매체의 보안 칼럼·기고·사설을 브리핑 작업이 골라 모은 목록입니다(최근 30일, 하루 3회 갱신). 제목을 누르면 원문 기사로 갑니다.</p>
      {rows.length ? (
        <table className="articles">
          <thead><tr><th style={{ width: 110 }}>날짜</th><th>칼럼</th><th style={{ width: 120 }}>매체</th></tr></thead>
          <tbody>{rows.map((a) => (
            <tr key={a.id}>
              <td className="muted meta when">{fmtShort(a.published_at || a.collected_at)}</td>
              <td>
                {allowed(a.url || "") ? <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a> : <span>{a.title}</span>}
                {a.summary_line && <div className="line">{a.summary_line}</div>}
              </td>
              <td className="muted meta">{SOURCES[a.source_id] || a.source_id}</td>
            </tr>))}
          </tbody>
        </table>
      ) : <p className="empty">최근 30일 동안 모인 칼럼·기고가 없습니다. 새 분류는 2026-10-31부터 쌓입니다.</p>}
    </>
  );
}
