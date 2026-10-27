import Briefing, { listEditions, latestDaily } from "./briefing-view";

export const dynamic = "force-dynamic";

export default async function Home() {
  const editions = await listEditions();
  if (!editions.length) return <p className="empty">아직 브리핑이 없습니다. 브리핑은 매일 06시·12시·18시에 생성됩니다.</p>;
  const latest = latestDaily(editions) || editions[0];
  return <Briefing date={latest.date} edition={latest.edition} editions={editions} />;
}
