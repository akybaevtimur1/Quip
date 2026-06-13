"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";

/** Scroll-reveal wrapper. Toggles the `data-reveal` attribute the CSS animates
 *  (fade + rise). One-shot IntersectionObserver; honors prefers-reduced-motion
 *  via the CSS rule. `delay` staggers siblings. */
export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      data-reveal={shown ? "in" : ""}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
      className={className && cn(className)}
    >
      {children}
    </div>
  );
}
