import "./globals.css";

export const metadata = {
  title: "정보보안 브리핑", robots: { index: false, follow: false },
  alternates: { types: { "application/rss+xml": [{ url: "/rss.xml", title: "정보보안 브리핑 RSS" }] } },
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>
        <header className="top"><div className="in">
          <a href="/" className="brand">정보보안 브리핑</a>
          <nav>
            <a href="/">브리핑</a>
            <a href="/articles">기사 검색</a>
            <a href="/events">행사 일정</a>
            <a href="/status">수집 상태</a>
            <a href="/rss.xml" title="브리핑 RSS 구독 주소">RSS</a>
          </nav>
        </div></header>
        <main>
          {/* 이상 경고는 '수집 상태' 화면에서만 표시 — 모든 페이지 상단 경고 띠 제거 (사용자 결정 2026-10-30) */}
          {children}
        </main>
      </body>
    </html>
  );
}
