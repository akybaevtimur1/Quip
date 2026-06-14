"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

/**
 * Mobile nav menu (marketing). Controlled dropdown with light-dismiss — closes on a
 * click/tap outside or Escape, same as the app's account menu and ExportMenu. (The old
 * native <details> only toggled via its own button, so tapping elsewhere left it open.)
 */
export function MobileMenu({
  links,
  authed = false,
}: {
  links: { href: string; label: string }[];
  authed?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative md:hidden" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={open ? "Close menu" : "Open menu"}
        className="flex size-9 cursor-pointer items-center justify-center rounded-md border border-line text-muted transition-colors hover:text-ink"
      >
        {open ? <X className="size-5" /> : <Menu className="size-5" />}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-11 w-56 rounded-lg border border-line bg-surface p-2 shadow-[0_24px_60px_-28px_rgba(0,0,0,.9)]"
        >
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              role="menuitem"
              onClick={() => setOpen(false)}
              className="block rounded-md px-3 py-2.5 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-ink"
            >
              {l.label}
            </a>
          ))}
          <Link
            href={authed ? "/dashboard" : "/login"}
            role="menuitem"
            onClick={() => setOpen(false)}
            className="mt-1 block rounded-md px-3 py-2.5 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-ink"
          >
            {authed ? "Dashboard" : "Sign in"}
          </Link>
        </div>
      )}
    </div>
  );
}
