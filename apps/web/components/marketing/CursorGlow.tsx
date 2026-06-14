"use client";

import { useEffect, useRef } from "react";

/**
 * Soft coral blob that trails the cursor (lerped, so it lags slightly) — adds a
 * subtle "alive" feel on the marketing pages. Sits behind content (z-0; the page
 * wrapper is z-10), so it only shows through transparent sections. Skipped entirely
 * on touch / coarse-pointer devices and when reduced-motion is requested.
 */
export function CursorGlow() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const el = ref.current;
    if (!el || !fine || reduced) return;

    let mx = window.innerWidth / 2;
    let my = window.innerHeight / 2;
    let cx = mx;
    let cy = my;
    let raf = 0;

    const onMove = (e: PointerEvent) => {
      mx = e.clientX;
      my = e.clientY;
    };
    const onLeave = () => {
      el.style.opacity = "0";
    };
    const onEnter = () => {
      el.style.opacity = "1";
    };

    const tick = () => {
      cx += (mx - cx) * 0.08; // smooth lag
      cy += (my - cy) * 0.08;
      el.style.transform = `translate3d(${Math.round(cx)}px, ${Math.round(cy)}px, 0)`;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    window.addEventListener("pointermove", onMove);
    document.addEventListener("mouseleave", onLeave);
    document.addEventListener("mouseenter", onEnter);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("mouseleave", onLeave);
      document.removeEventListener("mouseenter", onEnter);
    };
  }, []);

  return (
    <div
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed left-0 top-0 z-0 -ml-80 -mt-80 size-[640px] rounded-full opacity-100 transition-opacity duration-500 will-change-transform"
      style={{
        background:
          "radial-gradient(circle at center, rgba(255,90,61,0.08) 0%, rgba(255,90,61,0.03) 35%, transparent 70%)",
      }}
    />
  );
}
