import { q, SOURCES, LABELS, fmtShort } from "../../lib/db";
import NewBanner from "./new-banner";
import { groupByEvent, searchFilter } from "../../lib/articles";
import { allowed } from "../../lib/md";

export const dynamic = "force-dynamic";
const PAGE = 50;

export default async function Articles(props) {
  // ?q=a&q=b처럼 같은 이름이 반복되면 배열로 오므로 첫 값만 쓴다 (.trim() 오류로 500이 나지 않게)
  const sp = await props.searchParams;
  const searchParams = Object.fromEntries(Object.entries(sp || {}).map(([k, v]) => [k, Array.isArray(v) ? v[0] : v]));
  const raw = (searchParams.q || "").trim().slice(0, 100);
  const text = raw.length >= 2 ? raw : "";   // 1글자 검색은 부하만 크고 쓸모가 적어 무시
  const source = SOURCES[searchParams.source] ? searchParams.source : "";
  // 분류: 기본은 '분류 대기' 포함 전체 (수집 직후 바로 보이도록). 무관 기사는 DB 정책상 공개되지 않음
  const label = ["labeled", "security", "trend", "pr", "column", "pending"].includes(searchParams.label) ? searchParams.label : "";
  const page = Math.max(1, parseInt(searchParams.page || "1", 10) || 1);
  const group = searchParams.group !== "0";   // 같은 사건 묶기 (기본 켬)

  const params = {
    select: "id,title,url,source_id,published_at,collected_at,label,candidate,ai_related,summary_line,summary_source,event_id",
    order: "collected_at.desc,id.desc",   // 새로 수집된 기사가 맨 위
    limit: String(PAGE),
    offset: String((page - 1) * PAGE),
  };
  if (text) {   // 제목과 한 줄 요약에서 검색 (PostgREST or 구문을 깨는 문자는 공백으로)
    const f = searchFilter(text);
    if (f) params.or = f;
  }
  if (source) params.source_id = `eq.${source}`;
  if (label === "labeled") params.label = "in.(security,trend,pr,column)";
  else if (label === "pending") params.label = "is.null";
  else if (label) params.label = `eq.${label}`;

  // 같은 조회는 60초 동안 결과 재사용 (공개 페이지 반복 요청으로 DB 부하가 커지지 않도록)
  const { rows, total } = await q("articles", params, { count: true, revalidate: 60 });
  // 같은 사건 묶기: 브리핑에서 같은 사건으로 묶인 기사들을 이 쪽의 첫 기사 아래로 접어 보여 줌
  const evIds = group ? [...new Set(rows.map((a) => a.event_id).filter(Boolean))] : [];
  let byEvent = {}, evTitle = {};
  if (evIds.length) {
    try {
      const [sib, evs] = await Promise.all([
        q("articles", { select: "id,title,url,source_id,collected_at,event_id", event_id: `in.(${evIds.join(",")})`,
                        order: "collected_at.desc", limit: "500" }, { revalidate: 60 }),
        q("events", { select: "id,title", id: `in.(${evIds.join(",")})` }, { revalidate: 60 }),
      ]);
      for (const a of sib.rows) (byEvent[a.event_id] ||= []).push(a);
      for (const e of evs.rows) evTitle[e.id] = e.title;
    } catch { byEvent = {}; }   // 묶기 실패해도 목록은 그대로 표시
  }
  const { visible, shown, siblings } = groupByEvent(rows, byEvent);
  const now = Date.now();
  const since = new Date(now - 60e3).toISOString();   // 조회 결과는 최대 60초 재사용 → 그만큼 앞에서부터 새 기사 확인
  const isNew = (a) => a.collected_at && now - new Date(a.collected_at).getTime() < 3600e3;
  const qs = (p) => new URLSearchParams({ ...(text && { q: text }), ...(source && { source }), ...(label && { label }), ...(!group && { group: "0" }), page: String(p) }).toString();

  return (
    <>
      <form className="search" method="get">
        <input name="q" defaultValue={text} placeholder="제목·요약 검색 (예: 랜섬웨어, CVE)" />
        <select name="source" defaultValue={source}>
          <option value="">전체 매체</option>
          {Object.entries(SOURCES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select name="label" defaultValue={label}>
          <option value="">전체 (분류 대기 포함)</option>
          <option value="labeled">분류된 기사만</option>
          <option value="security">보안</option>
          <option value="trend">보안 동향</option>
          <option value="pr">업계 동향</option>
          <option value="column">칼럼·기고</option>
          <option value="pending">분류 대기</option>
        </select>
        <select name="group" defaultValue={group ? "1" : "0"}>
          <option value="1">같은 사건 묶기</option>
          <option value="0">모두 펼치기</option>
        </select>
        <button type="submit">검색</button>
      </form>
      <p className="muted">총 {total?.toLocaleString("ko-KR") ?? 0}건 · 2시간마다 수집 직후 반영, 새로 수집된 순{group && shown.size ? " · 같은 사건은 첫 기사 아래에 묶음" : ""}{raw && !text ? " · 검색어는 2글자 이상 입력하세요" : ""}</p>
      <p className="muted">'분류 대기'는 키워드로 고른 후보로, 다음 브리핑(06·12·18시)에서 보안·업계 동향으로 확정되거나 목록에서 빠집니다. 제목 아래 한 줄은 AI가 기사 내용을 핵심만 줄인 요약으로, 수집 직후 몇 분 안에 붙습니다.</p>
      <NewBanner since={since} />
      {rows.length === 0 ? <p className="empty">{page > 1 && total > 0 ? <>이 쪽에는 결과가 없습니다. <a href={`/articles?${qs(1)}`}>첫 쪽으로</a></> : "검색 결과가 없습니다."}</p> : (
        <table className="articles">
          <thead><tr><th>제목</th><th style={{ width: 110 }}>매체</th><th style={{ width: 130 }}>게시 / 수집</th></tr></thead>
          <tbody>
            {visible.map((a) => (
              <tr key={a.id}>
                <td>
                  {allowed(a.url) ? <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a> : <span>{a.title}</span>}{" "}
                  {isNew(a) && <span className="tag new">새 기사</span>}{" "}
                  {a.label ? <span className="tag">{LABELS[a.label]}</span> : <span className="tag pending">분류 대기</span>}{" "}
                  {a.ai_related && <span className="tag">AI</span>}
                  {a.summary_line && ["ai", "claude"].includes(a.summary_source) && <div className="line">{a.summary_line}</div>}
                  {siblings(a).length > 0 && (
                    <details className="same-event">
                      <summary>같은 사건 기사 {siblings(a).length}건 더{evTitle[a.event_id] ? ` · ${evTitle[a.event_id]}` : ""}</summary>
                      <ul>
                        {siblings(a).map((b) => (
                          <li key={b.id}>
                            {allowed(b.url) ? <a href={b.url} target="_blank" rel="noopener noreferrer">{b.title}</a> : <span>{b.title}</span>}
                            <span className="muted"> · {SOURCES[b.source_id] || b.source_id} · {fmtShort(b.collected_at)}</span>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </td>
                <td className="muted meta">{SOURCES[a.source_id] || a.source_id}</td>
                <td className="muted meta when">
                  <span>게시 {fmtShort(a.published_at) || "-"}</span><br /><span>수집 {fmtShort(a.collected_at)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="pager">
        {page > 1 ? <a href={`/articles?${qs(page - 1)}`}>← 이전</a> : <span />}
        {total > page * PAGE ? <a href={`/articles?${qs(page + 1)}`}>다음 →</a> : <span />}
      </div>
    </>
  );
}
