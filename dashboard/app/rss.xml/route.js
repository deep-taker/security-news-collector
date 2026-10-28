import { q } from "../../lib/db";
import { renderMarkdown } from "../../lib/md";
import { buildRss } from "../../lib/articles";

// 브리핑 RSS (06·12·18시판·주간 요약 최근 30개, 만든 순). RSS 앱·메일 구독용. 본문은 화면과 같은 방식으로 정리한 HTML.
export async function GET() {
  let rows = [];
  try {
    ({ rows } = await q("briefings", { select: "date,edition,markdown,created_at", order: "date.desc,created_at.desc", limit: "30" },
                        { revalidate: 300 }));
  } catch {
    return new Response("브리핑을 불러오지 못했습니다.", { status: 503 });
  }
  const xml = buildRss(rows, renderMarkdown);
  return new Response(xml, { headers: { "Content-Type": "application/rss+xml; charset=utf-8", "Cache-Control": "public, max-age=300" } });
}
