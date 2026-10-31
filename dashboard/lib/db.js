// 서버 컴포넌트에서만 호출. 읽기 전용 공개 키(SUPABASE_READ_KEY)를 쓰며,
// DB 정책상 이 키로는 보안·업계 기사와 브리핑 조회만 가능하고 쓰기는 불가능하다.
const URL_ = (process.env.SUPABASE_URL || "").replace(/\/$/, "");
// 공개 키만 쓴다. 비밀(service) 키로 대체하면 행 단위 보안이 우회돼 비공개 기사까지 노출되므로 쓰지 않음.
const KEY = process.env.SUPABASE_READ_KEY || "";

export async function q(table, params = {}, { count = false, revalidate = 0 } = {}) {
  if (!URL_ || !KEY) throw new Error("SUPABASE_URL / SUPABASE_READ_KEY 환경변수를 설정하세요.");
  const u = new URL(`${URL_}/rest/v1/${table}`);
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") u.searchParams.set(k, v);
  const res = await fetch(u, {
    headers: { apikey: KEY, Authorization: `Bearer ${KEY}`, ...(count ? { Prefer: "count=exact" } : {}) },
    ...(revalidate ? { next: { revalidate } } : { cache: "no-store" }),
  });
  // 범위 밖 페이지(예: 결과 47건인데 99쪽): PostgREST 416 → 빈 결과로 처리
  if (res.status === 416) return { rows: [], total: Number((res.headers.get("content-range") || "*/0").split("/")[1]) || 0 };
  if (!res.ok) throw new Error(`DB 오류 ${res.status}: ${await res.text()}`);
  const rows = await res.json();
  const total = count ? Number((res.headers.get("content-range") || "/0").split("/")[1]) : undefined;
  return { rows, total };
}

export const SOURCES = {
  boannews: "보안뉴스", dailysecu: "데일리시큐", etnews_sec: "전자신문", dt_ict: "디지털타임스",
  digitaltoday: "디지털투데이", aitimes: "AI타임스", bloter: "블로터", zdnet: "지디넷코리아", ddaily: "디지털데일리", itchosun: "IT조선", itdonga: "IT동아",
};
export const LABELS = { security: "보안", trend: "보안 동향", pr: "업계 동향", column: "칼럼·기고", not_security: "무관" };

// 날짜 뒤에 요일을 붙인다 (사용자 요청 2026-10-31)
const DOW = ["일", "월", "화", "수", "목", "금", "토"];
const kstParts = (ts) => Object.fromEntries(new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
}).formatToParts(new Date(ts)).map((x) => [x.type, x.value]));
const dowOf = (y, m, d) => DOW[new Date(Date.UTC(+y, +m - 1, +d)).getUTCDay()];

// 'YYYY-MM-DD' → 'YYYY-MM-DD (토)' (브리핑 판 목록)
export function dateWithDow(date) {
  const [y, m, d] = (date || "").split("-");
  return y && m && d ? `${date} (${dowOf(y, m, d)})` : date || "";
}

// 기사 목록용 짧은 시각: "10/26(월) 17:11" (한국 시간, 24시간제)
export function fmtShort(ts) {
  if (!ts) return "";
  const p = kstParts(ts);
  return `${p.month}/${p.day}(${dowOf(p.year, p.month, p.day)}) ${p.hour}:${p.minute}`;
}

// 상태 화면용 시각: "2026-10-26(월) 17:11"
export function fmt(ts) {
  if (!ts) return "";
  const p = kstParts(ts);
  return `${p.year}-${p.month}-${p.day}(${dowOf(p.year, p.month, p.day)}) ${p.hour}:${p.minute}`;
}

// 수집·브리핑 이상 점검 (공개용 DB 함수 system_alerts_public: 오류 원문 대신 분류만).
// 페이지를 열 때마다 DB를 조회하지 않도록 60초 동안 결과를 재사용. 실패해도 페이지는 계속 표시.
export async function getHealth() {
  if (!URL_ || !KEY) return null;
  const call = (opts) => fetch(`${URL_}/rest/v1/rpc/system_alerts_public`, {
    headers: { apikey: KEY, Authorization: `Bearer ${KEY}` }, ...opts,
  });
  try {
    let res = await call({ next: { revalidate: 60 } });
    if (!res.ok) return { error: `점검 실패 (${res.status})`, alerts: [], sources: [] };
    let h = await res.json();
    // 오래 아무도 안 열면 캐시가 '지난 결과'를 먼저 내주므로(그 뒤에야 갱신), 2분 넘은 결과면 바로 새로 조회
    if (!h.checked_at || Date.now() - new Date(h.checked_at).getTime() > 120e3) {
      res = await call({ cache: "no-store" });
      if (res.ok) h = await res.json();
    }
    return h;
  } catch {
    return { error: "점검 서버에 연결하지 못했습니다", alerts: [], sources: [] };
  }
}
