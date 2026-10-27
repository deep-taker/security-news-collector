"use client";   // 오류 화면은 클라이언트 컴포넌트여야 함 (Next 16: error·retry)

import { useEffect } from "react";

// DB(Supabase) 장애·키 오류 등으로 화면을 그리지 못했을 때 기본 오류 화면 대신 안내 (2026-10-27)
export default function Error({ error, retry }) {
  useEffect(() => { console.error(error); }, [error]);
  return (
    <div className="card">
      <p className="empty">
        데이터를 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.<br />
        계속되면 <a href="/status">수집 상태</a> 화면이나 Supabase 상태를 확인하세요.
      </p>
      <p style={{ textAlign: "center" }}><button type="button" onClick={() => retry()}>다시 시도</button></p>
    </div>
  );
}
