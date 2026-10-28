// 보안 헤더: 다른 사이트에 끼워 넣기 차단, 외부 스크립트·연결 차단, 리퍼러 최소화
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",   // Next.js 화면 전환용 인라인 스크립트
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "connect-src 'self'",
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

/** @type {import('next').NextConfig} */
export default {
  poweredByHeader: false,
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "Content-Security-Policy", value: csp },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), interest-cohort=()" },
        { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
      ],
    }];
  },
};
