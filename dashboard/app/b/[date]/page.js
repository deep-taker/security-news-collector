import { notFound } from "next/navigation";
import Briefing, { listEditions, latestDaily } from "../../briefing-view";

export const dynamic = "force-dynamic";

// /b/2026-10-26-am, -noon, -pm, -week(월요일 주간 요약), 또는 /b/2026-10-26 (그 날의 최신 일일 판)
export default async function Page(props) {
  const { date: id } = await props.params;
  const m = /^(\d{4}-\d{2}-\d{2})(?:-(am|noon|pm|week))?$/.exec(id);
  if (!m) notFound();
  const editions = await listEditions();
  let edition = m[2];
  if (!edition) edition = latestDaily(editions, m[1])?.edition || "am";
  return <Briefing date={m[1]} edition={edition} editions={editions} />;
}
