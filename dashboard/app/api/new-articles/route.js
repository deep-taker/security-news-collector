import { q } from "../../../lib/db";
import { validSince } from "../../../lib/articles";

// 기사 검색 페이지의 '새 기사' 띠용: since 이후 새로 수집된 공개 기사 수 (DB 정책상 공개 대상만 셈)
export async function GET(req) {
  const since = new URL(req.url).searchParams.get("since") || "";
  if (!validSince(since)) {
    return Response.json({ error: "since 형식 오류" }, { status: 400 });
  }
  try {
    const { total } = await q("articles", { select: "id", collected_at: `gt.${since}`, limit: "1" }, { count: true, revalidate: 60 });
    return Response.json({ count: total || 0 }, { headers: { "Cache-Control": "public, max-age=60" } });
  } catch {
    return Response.json({ count: 0 }, { status: 503 });
  }
}
