import { getHealth, fmt } from "../../lib/db";

export const dynamic = "force-dynamic";
export const metadata = { title: "수집 상태 · 정보보안 브리핑" };

function ago(ts) {
  if (!ts) return "기록 없음";
  const m = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (m < 60) return `${m}분 전`;
  if (m < 60 * 48) return `${Math.round(m / 60)}시간 전`;
  return `${Math.round(m / 1440)}일 전`;
}

const KIND = {
  collect_restart: "수집 중단 → 수집 재실행",
  briefing_refire: "브리핑 누락 → 브리핑 작업 재실행",
  sync_retry: "브리핑 반영 실패 → 반영 재실행",
  briefing_fix: "브리핑 출력 오류 → 보완 요청",
  backup_retry: "백업 실패 → 백업 재실행",
  notify: "지속 오류 → 휴대폰 알림",
  repair_request: "매체 구조 변경 → 수리 요청(PR)",
};

function Remediations({ rows }) {
  if (!rows.length) return <p className="muted">없음 — 10분마다 점검합니다.</p>;
  return (
    <div className="scroll">
      <table>
        <thead><tr><th>시각</th><th>조치</th><th>대상</th><th>결과</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td className="muted">{fmt(r.run_at)}</td>
              <td>{KIND[r.kind] || r.kind}</td>
              <td className="muted">{r.target}</td>
              <td><span className={`dot ${r.ok ? "ok" : "warn"}`} />{r.ok ? "실행" : "미실행(설정 필요)"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const MB = (b) => (b == null ? "-" : `${(Number(b) / 1e6).toFixed(1)}MB`);

function BackupTable({ b }) {
  const rows = [
    ["주 백업 · 매일 변경분 (Supabase Storage)", b.storage_last, `${MB(b.storage_used)} / 상한 900MB`],
    ["주 백업 · 전체 사본 (일요일·매월 1일)", b.storage_full, ""],
    ["복구 시험 (매월 2일)", b.restore_test_last, ""],
  ];
  return (
    <div className="scroll">
      <table>
        <thead><tr><th>항목</th><th>상태</th><th>마지막 실행</th><th>용량</th></tr></thead>
        <tbody>
          {rows.map(([name, r, cap]) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{!r ? <span className="muted">아직 없음</span> : <><span className={`dot ${r.ok ? "ok" : "error"}`} />{r.ok ? "정상" : "실패"}
                {!r.ok && r.detail && <div className="muted detail">{r.detail}</div>}</>}</td>
              <td className="muted">{r ? `${fmt(r.run_at)} (${ago(r.run_at)})` : "-"}</td>
              <td className="muted">{cap || (r?.bytes ? MB(r.bytes) : "")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const WHY = { missing: "응답 누락", short: "너무 짧음", long: "80자 초과", chars: "링크·기호 포함", inject: "지시문 의심", title: "제목 반복" };

function AiTable({ ai }) {
  if (!ai) return <p className="muted">기록 없음</p>;
  const l = ai.last || {};
  const cov = ai.coverage_n ? Math.round((100 * ai.coverage_filled) / ai.coverage_n) : null;
  const why = (l.why || []).map((w) => { const [k, v] = String(w).split("="); return `${WHY[k] || k} ${v}`; }).join(", ");
  const usd = Number(ai.month_cost_usd || 0);
  const rows = [
    ["마지막 실행", l.run_at ? <><span className={`dot ${l.ok ? "ok" : "warn"}`} />{fmt(l.run_at)} ({ago(l.run_at)}) · 대상 {l.target}건 → 완료 {l.done}건{l.rejected ? ` · 다음 실행 재시도 ${l.rejected}건${why ? ` (${why})` : ""}` : ""}{l.error && <div className="muted detail">{l.error}</div>}</> : "기록 없음"],
    ["24시간", `실행 ${ai.runs_24h}회 · 요약 ${ai.done_24h}건 · 재시도 ${ai.rejected_24h}건 · 실패한 실행 ${ai.failed_runs_24h}회`],
    ["채움률 (3~27시간 전 수집분)", cov == null ? "-" : <><span className={`dot ${cov >= 90 ? "ok" : cov >= 50 ? "warn" : "error"}`} />{cov}% ({ai.coverage_filled}/{ai.coverage_n}건)</>],
    ["이번 달 사용량", `입력 ${Number(ai.month_in_tok).toLocaleString("ko-KR")} · 출력 ${Number(ai.month_out_tok).toLocaleString("ko-KR")} 토큰 → 예상 $${usd.toFixed(usd < 1 ? 3 : 2)} (Haiku 5.5: 입력 $${ai.price_in_per_mtok}·출력 $${ai.price_out_per_mtok} / 100만 토큰)`],
  ];
  return (
    <div className="scroll">
      <table><tbody>{rows.map(([k, v]) => <tr key={k}><td style={{ width: 190 }}>{k}</td><td className="muted">{v}</td></tr>)}</tbody></table>
    </div>
  );
}

export default async function Status() {
  const h = (await getHealth()) || { alerts: [], sources: [], error: "환경변수가 설정되지 않았습니다" };
  const alerts = h.alerts || [];
  return (
    <>
      <h1 style={{ fontSize: "1.3rem", marginTop: 0 }}>수집 상태</h1>
      <p className="muted">
        점검 시각 {fmt(h.checked_at)} (최대 1분 전 결과) · 마지막 수집 {fmt(h.last_collect_at)} ({ago(h.last_collect_at)}) · DB {h.db_size_mb ?? "?"}MB / 500MB
      </p>

      <h2 className="sec">알림</h2>
      {h.error && <div className="alert warn"><strong>{h.error}</strong></div>}
      {alerts.length === 0 && !h.error ? (
        <div className="alert ok"><strong>✅ 이상 없음</strong> — 모든 매체가 정상 수집 중이고 누락된 브리핑이 없습니다.</div>
      ) : alerts.map((a, i) => (
        <div key={i} className={`alert ${a.level}`}>
          <strong>{a.level === "error" ? "⛔" : "⚠️"} {a.title}</strong>
          {a.detail && <div className="muted detail">{a.detail}</div>}
        </div>
      ))}

      <h2 className="sec">매체별 현황</h2>
      <div className="scroll">
        <table>
          <thead><tr><th>매체</th><th>상태</th><th>마지막 성공</th><th>24시간 수집</th><th>24시간 새 기사</th></tr></thead>
          <tbody>
            {(h.sources || []).map((s) => {
              const st = s.consecutive_fails >= (s.fail_alert_after || 3) ? ["error", `${s.consecutive_fails}회 연속 실패`]
                : s.consecutive_fails > 0 ? ["warn", `실패 ${s.consecutive_fails}회`]
                : s.runs_24h >= 3 && s.new_24h === 0 ? ["warn", "새 기사 없음"] : ["ok", "정상"];
              return (
                <tr key={s.id}>
                  <td>{s.name}</td>
                  <td><span className={`dot ${st[0]}`} />{st[1]}{s.consecutive_fails > 0 && s.last_error && <div className="muted detail">{s.last_error}</div>}</td>
                  <td className="muted">{ago(s.last_ok_at)}</td>
                  <td className="muted">{s.runs_24h}회</td>
                  <td className="muted">{s.new_24h}건</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <h2 className="sec">AI 한 줄 요약</h2>
      <AiTable ai={h.ai} />

      <h2 className="sec">자동 조치 (최근 48시간)</h2>
      <Remediations rows={h.remediations || []} />

      <h2 className="sec">백업</h2>
      <BackupTable b={h.backup || {}} />

      <p className="muted" style={{ marginTop: 16 }}>
        알림 기준: 2시간 넘게 수집 없음 · 매체 연속 실패(디지털데일리·디지털투데이 2회, 나머지 3회, 그 미만은 주의) · 24시간 새 기사 0건 · 놓친 기사 가능 구간 · 브리핑 예정 1시간 후에도 없음(06시판 07시, 12시판 13시, 18시판 19시) · 브리핑 반영 검증 실패 · 실행 신호 오류 · 주 백업 26시간 없음 · 백업 용량 상한(900MB)의 90% · 복구 시험 실패 · DB 400MB 초과 · AI 요약 채움률 50% 미만 · 이번 달 AI 요약 비용 $20 초과 · 수집 원문 지시문 의심. 실패한 매체는 매시 27분에 다시 수집하고, 10분마다 자동 조치(수집·브리핑·반영·백업 재실행, 지속 오류 알림)를 점검합니다.
      </p>
    </>
  );
}
