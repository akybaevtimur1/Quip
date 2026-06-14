"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { buttonVariants, type ButtonSize, type ButtonVariant } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

/**
 * Checkout / PAYG CTA.
 *
 * `/checkout` is a route handler that 307-redirects to Polar (cross-origin). A Next
 * <Link> navigates through the RSC client router, whose fetch (`?_rsc=…`) follows that
 * redirect to polar.sh and dies on CORS (`net::ERR_FAILED`). The first click is then
 * swallowed — the user sees nothing happen and has to click again (and each failed try
 * burns a Polar checkout session). So for `/checkout` we render a plain <a>: a top-level
 * browser navigation follows the 307 natively, in a single click, with no RSC/CORS.
 *
 * Internal targets (e.g. the free plan → /signup) keep the client-side <Link>.
 *
 * Either way we flip an immediate pending state on click: a spinner + locked button so
 * the CTA never looks dead during the redirect round-trip, and a second click can't
 * fire a duplicate navigation.
 */
export function CheckoutCta({
  href,
  children,
  variant = "secondary",
  size = "md",
  className,
}: {
  href: string;
  children: React.ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
}) {
  const [pending, setPending] = useState(false);
  const classes = cn(
    buttonVariants({ variant, size }),
    className,
    pending && "pointer-events-none",
  );
  const content = (
    <>
      {pending && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </>
  );

  // Route handler → external redirect: must be a real navigation, not the RSC router.
  if (href.startsWith("/checkout")) {
    return (
      <a
        href={href}
        onClick={() => setPending(true)}
        aria-busy={pending || undefined}
        className={classes}
      >
        {content}
      </a>
    );
  }

  // Internal page (e.g. /signup): the client-side <Link> is correct and fast.
  return (
    <Link
      href={href}
      prefetch={false}
      onClick={() => setPending(true)}
      aria-busy={pending || undefined}
      className={classes}
    >
      {content}
    </Link>
  );
}
