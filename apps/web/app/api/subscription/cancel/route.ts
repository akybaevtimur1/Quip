import { NextResponse } from "next/server";
import { polarConfigured, polarFetch } from "@/lib/polar-api";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { getOptionalUser } from "@/lib/supabase/server";

/** Cancel the signed-in user's active subscription at period end (no further charges; they
 *  keep access until the period they already paid for ends). Refunds are NOT handled here —
 *  by design those go through support email. Only touches the caller's own subscription. */
export async function POST() {
  if (!isSupabaseConfigured) return NextResponse.json({ error: "Not available" }, { status: 503 });
  const user = await getOptionalUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (!polarConfigured())
    return NextResponse.json({ error: "Billing isn’t configured" }, { status: 503 });

  const listRes = await polarFetch(
    `/v1/subscriptions?external_customer_id=${encodeURIComponent(user.id)}&active=true&limit=10`,
  );
  if (!listRes.ok)
    return NextResponse.json({ error: "Couldn’t load your subscription" }, { status: 502 });

  const list = (await listRes.json()) as { items?: { id: string; cancel_at_period_end?: boolean }[] };
  const active = (list.items ?? []).filter((s) => !s.cancel_at_period_end);
  if (active.length === 0) return NextResponse.json({ canceled: 0, endsAt: null });

  let canceled = 0;
  let endsAt: string | null = null;
  for (const s of active) {
    const r = await polarFetch(`/v1/subscriptions/${s.id}`, {
      method: "PATCH",
      body: JSON.stringify({ cancel_at_period_end: true }),
    });
    if (r.ok) {
      canceled++;
      const j = (await r.json().catch(() => ({}))) as { current_period_end?: string };
      endsAt = j.current_period_end ?? endsAt;
    }
  }
  if (canceled === 0)
    return NextResponse.json(
      { error: "Couldn’t cancel — please try again or contact support" },
      { status: 502 },
    );
  return NextResponse.json({ canceled, endsAt });
}
