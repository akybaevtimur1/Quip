"use client";

import { useSearchParams } from "next/navigation";
import { Container } from "@/components/ui/Container";

// Shown when /checkout funnels a logged-in user back here because Polar isn't wired yet
// (?checkout=unavailable). Honest, non-blocking: they can still start on Free.
export function CheckoutNotice() {
  const reason = useSearchParams().get("checkout");
  if (reason !== "unavailable") return null;
  return (
    <Container className="pt-8">
      <div className="mx-auto max-w-5xl rounded-lg border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn">
        Checkout is being set up. Paid plans go live shortly; you can start on Free right now.
      </div>
    </Container>
  );
}
