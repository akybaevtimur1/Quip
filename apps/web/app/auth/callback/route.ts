import { NextResponse } from "next/server";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/** Email-confirmation / OAuth callback: exchanges the code for a session, then
 *  redirects to `next` (validated as an internal path). */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const rawNext = url.searchParams.get("next") ?? "/dashboard";
  const next = rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "/dashboard";

  if (code && isSupabaseConfigured) {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) {
      // PKCE/code exchange failed (expired or already-used link). Don't redirect to a
      // protected route — the (app) gate would bounce to /login with no explanation,
      // looking like a silent loop. Surface a real reason on the login page instead.
      const login = new URL("/login", url.origin);
      login.searchParams.set("next", next);
      login.searchParams.set("error", "Sign-in link is invalid or expired. Please try again.");
      return NextResponse.redirect(login);
    }
  }

  return NextResponse.redirect(new URL(next, url.origin));
}
