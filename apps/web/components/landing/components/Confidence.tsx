"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { animate, motion, useInView, useMotionValue, useReducedMotion, useTransform } from "motion/react";

type Variant = "hero" | "card" | "inline";

const NUM: Record<Variant, string> = {
  hero: "text-[clamp(64px,11vw,132px)] leading-[0.82]",
  card: "text-[34px] leading-none",
  inline: "text-[22px] leading-none",
};
const SLASH: Record<Variant, string> = {
  hero: "text-[clamp(15px,2vw,22px)]",
  card: "text-[13px]",
  inline: "text-[11px]",
};

/*
  The "needle settles" gauge. On first scroll-in it counts up from 0, the track sweeps,
  and coral ignites only in the final beat as the value locks. Runs once. Reduced-motion
  shows the locked coral value with no animation. This is the page's one animated coral.
*/
export function ConfidenceGauge({
  value,
  variant = "card",
  track = true,
  accent = true,
  className = "",
}: {
  value: number;
  variant?: Variant;
  track?: boolean;
  accent?: boolean;
  className?: string;
}) {
  const t = useTranslations("confidence");
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const reduce = useReducedMotion();
  const count = useMotionValue(0);
  const display = useTransform(count, (v) => Math.round(v));
  const fillW = useTransform(count, (v) => `${v}%`);
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    if (!inView) return;
    if (reduce) {
      // Reduced motion: snap to the final value, no count-up. The lit (coral) state is
      // derived below, so the effect body holds no synchronous setState (react-hooks rule).
      count.set(value);
      return;
    }
    const controls = animate(count, value, { duration: 0.9, ease: [0.2, 0.7, 0.2, 1] });
    const t = setTimeout(() => setLocked(true), 760);
    return () => {
      controls.stop();
      clearTimeout(t);
    };
  }, [inView, reduce, value, count]);

  // Coral ignites at lock. Reduced motion has no timed lock, so derive the lit state
  // once the gauge is in view (keeps the effect free of synchronous setState).
  const lit = locked || (reduce && inView);
  const litText = accent ? "text-accent" : "text-ink";
  const litBg = accent ? "bg-accent" : "bg-muted";

  return (
    <div ref={ref} className={className}>
      {/* real value always in the a11y tree; the animated numeral is decorative */}
      <span className="sr-only">{t("sr", { value })}</span>
      <div className="flex items-baseline gap-1.5" aria-hidden>
        <motion.span
          className={`num font-mono font-medium tabular-nums transition-colors duration-200 ${NUM[variant]} ${
            lit ? litText : "text-faint"
          }`}
        >
          {display}
        </motion.span>
        <span className={`num font-mono ${SLASH[variant]} ${lit ? "text-muted" : "text-faint"}`}>/100</span>
      </div>
      {track && (
        <div className="relative mt-3 h-px w-full bg-line-strong">
          <motion.div
            className={`absolute left-0 top-0 h-px transition-colors duration-200 ${lit ? litBg : "bg-faint"}`}
            style={{ width: fillW }}
          />
          <motion.div
            className={`absolute top-1/2 size-[7px] -translate-y-1/2 rounded-full transition-colors duration-200 ${
              lit ? litBg : "bg-faint"
            }`}
            style={{ left: fillW, marginLeft: -3 }}
          />
        </div>
      )}
    </div>
  );
}
