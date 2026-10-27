"use client";
import { useEffect, useState } from "react";

// 페이지를 열어 둔 동안 5분마다 새로 수집된 기사가 있는지 확인해 띠로 알린다.
// 보던 위치가 갑자기 바뀌지 않도록 자동 새로고침은 하지 않고, 눌렀을 때만 새로 불러온다.
export default function NewBanner({ since }) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let stop = false;
    const check = async () => {
      if (document.hidden) return;
      try {
        const r = await fetch(`/api/new-articles?since=${encodeURIComponent(since)}`);
        if (r.ok && !stop) setCount((await r.json()).count || 0);
      } catch {}
    };
    const id = setInterval(check, 5 * 60e3);
    const onVis = () => !document.hidden && check();
    document.addEventListener("visibilitychange", onVis);
    return () => { stop = true; clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, [since]);
  if (!count) return null;
  return (
    <button type="button" className="new-banner" onClick={() => window.location.reload()}>
      새로 수집된 기사 {count}건 — 눌러서 보기
    </button>
  );
}
