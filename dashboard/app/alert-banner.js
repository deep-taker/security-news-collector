import { getHealth } from "../lib/db";

// 모든 페이지 상단: 이상이 있을 때만 표시
export default async function AlertBanner() {
  const h = await getHealth();
  if (!h) return null;
  const alerts = h.alerts || [];
  if (h.error) alerts.unshift({ level: "warn", title: h.error });
  if (!alerts.length) return null;
  const level = alerts.some((a) => a.level === "error") ? "error" : "warn";
  return (
    <a href="/status" className={`alert-banner ${level}`}>
      <strong>{level === "error" ? "⛔ 수집 이상" : "⚠️ 주의"} {alerts.length}건</strong>
      <span>{alerts[0].title}{alerts.length > 1 ? ` 외 ${alerts.length - 1}건` : ""}</span>
      <span className="go">상태 보기 →</span>
    </a>
  );
}
