import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { SUPABASE_ANON_KEY, SUPABASE_URL, isSupabaseConfigured } from "@/lib/supabase/config";

// Next 16 renamed Middleware → Proxy. This refreshes the auth session cookie and
// does OPTIMISTIC redirects only; the authoritative gate is the (app) server layout
// (getUser). When Supabase isn't configured the app stays open (dev).
const PROTECTED = ["/dashboard", "/edit", "/account"];

function isProtected(path: string): boolean {
  return PROTECTED.some((p) => path === p || path.startsWith(`${p}/`));
}

export async function proxy(request: NextRequest) {
  if (!isSupabaseConfigured) return NextResponse.next();

  // Only pay the Supabase getUser() round-trip where the session matters: protected app
  // routes (the gate) + auth pages (bounce logged-in users). Public marketing pages
  // (/, /pricing, /terms, …) skip it → no per-navigation latency (fixes slow /pricing).
  const path = request.nextUrl.pathname;
  const isAuthPage = path === "/login" || path === "/signup";
  if (!isProtected(path) && !isAuthPage) return NextResponse.next();

  let response = NextResponse.next({ request });
  const supabase = createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  // IMPORTANT: getUser() validates the JWT with the auth server (never getSession()).
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user && isProtected(path)) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", path);
    return NextResponse.redirect(url);
  }
  if (user && isAuthPage) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  // Run on app routes; skip static assets and metadata files.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|ico|txt|xml|webp)$).*)"],
};
