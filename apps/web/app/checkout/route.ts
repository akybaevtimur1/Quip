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
  if (!token || !products) {
    return NextResponse.redirect(new URL("/signup", req.url));
  }

  // Привязка покупки к аккаунту: external_id = supabase user.id (читаем сессию на сервере).
  const url = new URL(req.url);
  if (isSupabaseConfigured && !url.searchParams.get("customerExternalId")) {
    try {
      const supabase = await createSupabaseServerClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();
      if (user) url.searchParams.set("customerExternalId", user.id);
    } catch {
      // нет сессии → анонимный checkout; вебхук свяжет по email
    }
  }

  const handler = Checkout({
    accessToken: token,
    successUrl: `${url.origin}/dashboard?checkout=success`,
    server: (process.env.POLAR_SERVER as "sandbox" | "production") ?? "production",
    theme: "dark",
  });
  return handler(new NextRequest(url, { headers: req.headers }));
}
