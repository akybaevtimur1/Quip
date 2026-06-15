import { NextResponse } from "next/server";
import { polarConfigured, polarFetch } from "@/lib/polar-api";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { getOptionalUser } from "@/lib/supabase/server";

/** Current user's active Polar subscription (or null = Free). Used by the /account page.
 *  Only ever returns the signed-in user's own subscription (filtered by external_id). */
export async function GET() {
  if (!isSupabaseConfigured) return NextResponse.json({ subscription: null, configured: false });
  const user = await getOptionalUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (!polarConfigured()) return NextResponse.json({ subscription: null, configured: false });

  const res = await polarFetch(
    `/v1/subscriptions?external_customer_id=${encodeURIComponent(user.id)}&active=true&limit=10`,
  );
  if (!res.ok) return NextResponse.json({ error: "Couldn’t load subscription" }, { status: 502 });

  const data = (await res.json()) as { items?: SubRow[] };
  const s = (data.items ?? [])[0];
  const subscription = s
    ? {
        id: s.id,
        status: s.status,
        productName: s.product?.name ?? "Subscription",
        amount: s.amount ?? null,
        recurringInterval: s.recurring_interval ?? null,
        currentPeriodEnd: s.current_period_end ?? null,
        cancelAtPeriodEnd: Boolean(s.cancel_at_period_end),
      }
    : null;
  return NextResponse.json({ subscription, configured: true });
}

type SubRow = {
  id: string;
  status: string;
  amount?: number | null;
  recurring_interval?: string | null;
  current_period_end?: string | null;
  cancel_at_period_end?: boolean;
  product?: { name?: string };
};
