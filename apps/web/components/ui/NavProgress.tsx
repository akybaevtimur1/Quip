"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/**
 * Thin top progress bar shown during page navigation.
 *
 * The App Router has no global "navigation started" event, so we start the bar on
 * internal link clicks (capture phase) and finish it when the route commits
 * (usePathname changes). This gives an instant "click accepted" signal — most
 * noticeable in `next dev`, where a route compiles on first visit and the click
 * would otherwise look dead (you click again, thinking nothing happened).
 *
 * Zero dependencies on purpose: no router/history monkey-patching that could break
 * on a new Next version. Just a click listener + usePathname.
 */
export function NavProgress() {
  const pathname = usePathname();
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState(false);
  const creep = useRef<number | null>(null);

  const stopCreep = () => {
    if (creep.current !== null) {
      clearInterval(creep.current);
      creep.current = null;
    }
  };

  // Start on internal link clicks that actually change the path.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey)
        return;
      const a = (e.target as HTMLElement | null)?.closest("a");
      if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
      const href = a.getAttribute("href");
      if (!href) return;
      let url: URL;
      try {
        url = new URL(href, location.href);
      } catch {
        return;
      }
      if (url.origin !== location.origin) return; // external → the browser shows its own loading
      if (url.pathname === location.pathname) return; // same page (anchor/hash) → not a page nav

      stopCreep();
      setActive(true);
      setWidth(10);
      let w = 10;
      creep.current = window.setInterval(() => {
        w = Math.min(90, w + (90 - w) * 0.15); // ease toward 90%, never reach it until done
        setWidth(w);
      }, 180);
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);

  // Route committed (pathname changed) → snap to 100% and fade out. setState is
  // deferred to rAF/timeouts so it never runs synchronously inside the effect body.
  useEffect(() => {
    if (!active) return;
    stopCreep();
    const finish = requestAnimationFrame(() => setWidth(100));
    const hide = window.setTimeout(() => setActive(false), 220);
    const reset = window.setTimeout(() => setWidth(0), 470);
    return () => {
      cancelAnimationFrame(finish);
      clearTimeout(hide);
      clearTimeout(reset);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  useEffect(() => stopCreep, []);

  if (!active && width === 0) return null;
  return (
    <div aria-hidden className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-0.5">
      <div
        className="h-full bg-accent shadow-[0_0_8px_var(--color-accent)] transition-[width,opacity] duration-200 ease-out"
        style={{ width: `${width}%`, opacity: active ? 1 : 0 }}
      />
    </div>
  );
}
