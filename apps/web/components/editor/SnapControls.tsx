"use client";

import { Magnet } from "lucide-react";
import { SAFE_PLATFORMS, type SafePlatform } from "@/lib/safeAreas";

// ── SnapControls — snapping toggle + safe-area platform picker ──
// Rendered as a semi-transparent chip overlaid on the canvas (e.g. top-right).
// Keeps all state in the parent; this is fully controlled.

const PLATFORM_LABELS: Record<SafePlatform, string> = {
  tiktok: "TikTok",
  reels: "Reels",
  shorts: "Shorts",
};

interface SnapControlsProps {
  snapEnabled: boolean;
  onSnapToggle: (v: boolean) => void;
  platform: SafePlatform | null;
  onPlatformChange: (p: SafePlatform | null) => void;
}

export function SnapControls({
  snapEnabled,
  onSnapToggle,
  platform,
  onPlatformChange,
}: SnapControlsProps): React.ReactElement {
  return (
    <div className="flex items-center gap-1 rounded-lg bg-black/50 px-1.5 py-1 backdrop-blur-sm">
      {/* Snap toggle */}
      <button
        type="button"
        aria-pressed={snapEnabled}
        title="Snap (S)"
        onClick={() => onSnapToggle(!snapEnabled)}
        className={[
          "flex h-6 w-6 items-center justify-center rounded-md transition-colors",
          snapEnabled
            ? "bg-[#FF2D9B]/80 text-white"
            : "text-white/50 hover:bg-white/10 hover:text-white/80",
        ].join(" ")}
      >
        <Magnet size={13} />
      </button>

      {/* Divider */}
      <span className="h-4 w-px bg-white/20" aria-hidden="true" />

      {/* Safe-area platform picker: Off · TikTok · Reels · Shorts */}
      <div className="flex items-center gap-0.5">
        <PlatformChip
          label="Off"
          active={platform === null}
          onClick={() => onPlatformChange(null)}
        />
        {SAFE_PLATFORMS.map((p) => (
          <PlatformChip
            key={p}
            label={PLATFORM_LABELS[p]}
            active={platform === p}
            onClick={() => onPlatformChange(p)}
          />
        ))}
      </div>
    </div>
  );
}

function PlatformChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "rounded px-1.5 py-0.5 text-[10px] font-medium leading-none transition-colors",
        active
          ? "bg-white/20 text-white"
          : "text-white/45 hover:bg-white/10 hover:text-white/70",
      ].join(" ")}
    >
      {label}
    </button>
  );
}
