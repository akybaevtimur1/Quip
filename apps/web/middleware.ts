import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// If DEMO_PASSCODE is set in env, all pages require the cookie to match.
// Unset = open access (dev / post-demo).
const PASSCODE = process.env.DEMO_PASSCODE ?? "";

const PUBLIC_PATHS = ["/login", "/api/auth"];

export function middleware(req: NextRequest) {
  if (!PASSCODE) return NextResponse.next();

  const { pathname } = req.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) return NextResponse.next();

  const cookie = req.cookies.get("demo_auth")?.value;
  if (cookie === PASSCODE) return NextResponse.next();

  const loginUrl = new URL("/login", req.url);
  loginUrl.searchParams.set("from", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
