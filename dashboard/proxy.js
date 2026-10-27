import { NextResponse } from "next/server";

// 로그인 없이 공개 운영 (사용자 결정 2026-10-26).
// 나중에 보호가 필요하면 Vercel 환경변수 DASHBOARD_USER / DASHBOARD_PASSWORD를 넣기만 하면 Basic 인증이 켜진다.
export function proxy(req) {
  const user = process.env.DASHBOARD_USER;
  const pass = process.env.DASHBOARD_PASSWORD;
  if (!user || !pass) return NextResponse.next();
  const auth = req.headers.get("authorization") || "";
  const [scheme, encoded] = auth.split(" ");
  if (scheme === "Basic" && encoded) {
    const [u, ...rest] = atob(encoded).split(":");
    if (u === user && rest.join(":") === pass) return NextResponse.next();
  }
  return new NextResponse("인증이 필요합니다.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="security-news", charset="UTF-8"' },
  });
}

export const config = { matcher: "/((?!_next/static|favicon.ico).*)" };
