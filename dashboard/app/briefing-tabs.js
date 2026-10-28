"use client";
import { useEffect, useState } from "react";

// 브리핑 절을 탭으로 (주소 #main·#ai 등으로 바로 열기). 본문 HTML은 서버에서 정리(renderMarkdown)한 것만 받는다.
// 휴대폰(720px 이하)에서는 탭 없이 모든 절을 절 제목(.ptitle)과 함께 한 페이지에 나열한다 — CSS로 처리 (사용자 결정 2026-10-27)
export default function BriefingTabs({ tabs }) {
  const [cur, setCur] = useState(tabs[0]?.id);
  useEffect(() => {
    const pick = () => { const h = decodeURIComponent(location.hash.slice(1)); if (tabs.some((t) => t.id === h)) setCur(h); };
    pick();
    window.addEventListener("hashchange", pick);
    return () => window.removeEventListener("hashchange", pick);
  }, [tabs]);
  const go = (id) => { setCur(id); history.replaceState(null, "", `#${id}`); };
  return (
    <>
      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t.id} role="tab" type="button" aria-selected={t.id === cur} aria-controls={`p-${t.id}`}
            className={`tab${t.id === cur ? " on" : ""}`} onClick={() => go(t.id)}>
            {t.title} <span className="cnt">{t.count}</span>
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <section key={t.id} id={`p-${t.id}`} role="tabpanel" hidden={t.id !== cur} className="panel">
          <h2 className="ptitle">{t.title} <span className="cnt">{t.count}</span></h2>
          <div dangerouslySetInnerHTML={{ __html: t.html }} />
        </section>
      ))}
    </>
  );
}
