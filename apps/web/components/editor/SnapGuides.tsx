"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import type { GuideLine } from "@/lib/snapEngine";

// ── SnapGuides — imperative overlay that draws magenta alignment guide lines ──
// Uses a fixed pool of line divs to avoid allocating DOM nodes on pointermove.
// Driven purely by ref mutations (no React state per call) for zero re-renders
// during drag.

export interface SnapGuidesHandle {
  /** Show the given guide lines over a render box of the given dimensions. */
  show(lines: GuideLine[], renderW: number, renderH: number): void;
  /** Hide all guides. */
  hide(): void;
}

// Pool size: up to 4 simultaneous guide lines (x and y for up to 2 snap targets).
const POOL_SIZE = 4;

const SnapGuides = forwardRef<SnapGuidesHandle, Record<string, never>>(
  function SnapGuides(_props, ref) {
    // Keep refs to each pooled line div so we can mutate styles without React state.
    const lineRefs = useRef<(HTMLDivElement | null)[]>(
      Array.from({ length: POOL_SIZE }, () => null),
    );

    useImperativeHandle(ref, () => ({
      show(lines: GuideLine[], renderW: number, renderH: number) {
        lines.slice(0, POOL_SIZE).forEach((line, i) => {
          const el = lineRefs.current[i];
          if (!el) return;
          if (line.axis === "x") {
            // Vertical guide line: positioned at pos/renderW along the X axis.
            const pct = (line.pos / renderW) * 100;
            el.style.left = `${pct}%`;
            el.style.top = "0";
            el.style.width = "1px";
            el.style.height = "100%";
            el.style.transform = "translateX(-0.5px)";
          } else {
            // Horizontal guide line: positioned at pos/renderH along the Y axis.
            const pct = (line.pos / renderH) * 100;
            el.style.top = `${pct}%`;
            el.style.left = "0";
            el.style.height = "1px";
            el.style.width = "100%";
            el.style.transform = "translateY(-0.5px)";
          }
          el.style.opacity = "1";
        });
        // Hide any unused pool slots.
        for (let i = lines.length; i < POOL_SIZE; i++) {
          const el = lineRefs.current[i];
          if (el) el.style.opacity = "0";
        }
      },
      hide() {
        for (let i = 0; i < POOL_SIZE; i++) {
          const el = lineRefs.current[i];
          if (el) el.style.opacity = "0";
        }
      },
    }));

    return (
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-20"
      >
        {Array.from({ length: POOL_SIZE }, (_, i) => (
          <div
            key={i}
            ref={(el) => {
              lineRefs.current[i] = el;
            }}
            style={{
              position: "absolute",
              opacity: 0,
              backgroundColor: "#FF2D9B",
              pointerEvents: "none",
            }}
          />
        ))}
      </div>
    );
  },
);

export default SnapGuides;
