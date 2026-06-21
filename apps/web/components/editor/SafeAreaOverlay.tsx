"use client";

import type { ReactElement } from "react";
import { SAFE_AREAS, type SafePlatform } from "@/lib/safeAreas";

// ── SafeAreaOverlay — dashed safe-zone border over the render canvas ──
// Shows a single platform's safe region as a dashed inset rectangle so the
// user knows which area is cropped on TikTok/Reels/Shorts. Subtle so it
// doesn't fight the video.

const PLATFORM_LABELS: Record<SafePlatform, string> = {
  tiktok: "TikTok safe",
  reels: "Reels safe",
  shorts: "Shorts safe",
};

interface SafeAreaOverlayProps {
  platform: SafePlatform | null;
}

export function SafeAreaOverlay({ platform }: SafeAreaOverlayProps): ReactElement | null {
  if (!platform) return null;

  const insets = SAFE_AREAS[platform];

  // Convert fractions to percentages for CSS positioning.
  const topPct = insets.top * 100;
  const leftPct = insets.left * 100;
  // right/bottom in CSS inset terms: distance from the opposite edge.
  const rightPct = (1 - insets.right) * 100;
  const bottomPct = (1 - insets.bottom) * 100;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-10"
    >
      <div
        style={{
          position: "absolute",
          top: `${topPct}%`,
          left: `${leftPct}%`,
          right: `${rightPct}%`,
          bottom: `${bottomPct}%`,
        }}
        className="border border-dashed border-white/50"
      >
        {/* Label chip at top-left corner of the safe rect */}
        <span className="absolute left-0 top-0 rounded-br-[3px] bg-black/40 px-1 py-px text-[9px] font-medium leading-tight tracking-wide text-white/70">
          {PLATFORM_LABELS[platform]}
        </span>
      </div>
    </div>
  );
}
