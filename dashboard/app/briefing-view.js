import { q } from "../lib/db";
import { renderMarkdown } from "../lib/md";
import { splitSections, mainIncidents } from "../lib/briefing";
import BriefingTabs from "./briefing-tabs";
import BriefingSide from "./briefing-side";

export const EDITION_LABEL = { am: "06시판", noon: "12시판", pm: "18시판", week: "주간 요약" };
const RANK = { pm: 3, noon: 2, am: 1, week: 0 };   // 같은 날 안에서 표시 순서 (주간 요약은 그날 06시판 아래)

// 최근 판 목록 (날짜 역순, 같은 날은 18·12·06시판·주간 요약 순)
export async function listEditions() {
  const { rows } = await q("briefings", { select: "date,edition", order: "date.desc", limit: "60" });
  return rows.map((r) => ({ ...r, id: `${r.date}-${r.edition}` }))
    .sort((a, b) => (a.date === b.date ? (RANK[b.edition] ?? -1) - (RANK[a.edition] ?? -1) : a.date < b.date ? 1 : -1));
}

// 첫 화면·날짜만 준 주소는 가장 최근 '일일' 판
export const latestDaily = (editions, date) => editions.find((e) => e.edition !== "week" && (!date || e.date === date));

export default async function Briefing({ date, edition, editions }) {
  const { rows } = await q("briefings", { select: "date,edition,markdown", date: `eq.${date}`, edition: `eq.${edition}` });
  const b = rows[0];
  const cur = `${date}-${edition}`;
  const html = b ? renderMarkdown(b.markdown) : "";
  const incidents = b ? mainIncidents(splitSections(html).tabs) : [];
  return (
    <div className="grid">
      <aside className="dates">
        {editions.map((e) => (
          <a key={e.id} href={`/b/${e.id}`} className={e.id === cur ? "on" : ""}>
            {e.date} {EDITION_LABEL[e.edition]}
          </a>
        ))}
      </aside>
      <article className="card md">
        {b ? <Sections html={html} /> : <p className="empty">해당 브리핑이 없습니다.</p>}
      </article>
      <BriefingSide incidents={incidents} />
    </div>
  );
}

// 제목·대상 줄은 위에, 절(주요 사건·사고, 기타 사건·사고, AI 보안 …)은 탭으로. 절이 하나 이하면 탭 없이 그대로.
function Sections({ html }) {
  const { head, tabs } = splitSections(html);
  if (tabs.length <= 1) return <div dangerouslySetInnerHTML={{ __html: html }} />;
  return (
    <>
      <div dangerouslySetInnerHTML={{ __html: head }} />
      <BriefingTabs tabs={tabs} />
    </>
  );
}
