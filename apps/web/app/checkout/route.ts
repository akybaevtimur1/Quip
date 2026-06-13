import { Checkout } from "@polar-sh/nextjs";
import { NextRequest, NextResponse } from "next/server";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";

// Dynamic Polar checkout (route handler, не статические ссылки). Открывается с
// ?products=<polar_product_id>. Server-side подставляет customerExternalId = Supabase
// user.id → вебхук связывает оплату с аккаунтом (profiles.plan / payg_credits).
//
// Dual-mode: без POLAR_ACCESS_TOKEN (фаундер впишет позже) CTA уводит на /signup —
// воронка не упирается в тупик. POLAR_SERVER = "sandbox" | "production".
export async function GET(req: NextRequest) {
  const token = process.env.POLAR_ACCESS_TOKEN;
  const products = req.nextUrl.searchParams.get("products");

  // Сессию читаем СНАЧАЛА: нужна и для external_id, и для разумного фолбэка без Polar.
  let userId: string | null = null;
  if (isSupabaseConfigured) {
    try {
      const supabase = await createSupabaseServerClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();
      userId = user?.id ?? null;
    } catch {
      // нет сессии → анонимный checkout позже свяжется по email
    }
  }

  if (!token || !products) {
    // Polar ещё не сконфигурирован (фаундер впишет POLAR_ACCESS_TOKEN). НЕ кидаем
    // залогиненного на /dashboard (через /signup): держим его на /pricing с пометкой;
    // незалогиненного — в воронку регистрации.
    const dest = userId ? "/pricing?checkout=unavailable" : "/signup";
    return NextResponse.redirect(new URL(dest, req.url));
  }

  // Привязка покупки к аккаунту: external_id = supabase user.id.
  const url = new URL(req.url);
  if (userId && !url.searchParams.get("customerExternalId")) {
    url.searchParams.set("customerExternalId", userId);
  }

  const handler = Checkout({
    accessToken: token,
    successUrl: `${url.origin}/dashboard?checkout=success`,
    server: (process.env.POLAR_SERVER as "sandbox" | "production") ?? "production",
    theme: "dark",
  });
  return handler(new NextRequest(url, { headers: req.headers }));
}
