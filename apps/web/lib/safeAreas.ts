export type SafePlatform = "tiktok" | "reels" | "shorts";
export interface SafeInsets { top: number; bottom: number; left: number; right: number }
export interface SafeBox { top: number; bottom: number; left: number; right: number }

export const SAFE_PLATFORMS: SafePlatform[] = ["tiktok", "reels", "shorts"];

// Fractions (0..1) of the 1080x1920 frame; the SAFE region is INSIDE these. Design-tunable.
export const SAFE_AREAS: Record<SafePlatform, SafeInsets> = {
  tiktok: { top: 0.06, bottom: 0.83, left: 0.055, right: 0.89 },
  reels: { top: 0.115, bottom: 0.8, left: 0.055, right: 0.945 },
  shorts: { top: 0.2, bottom: 0.8, left: 0.05, right: 0.82 },
};

export function safeBoxPx(insets: SafeInsets, renderW: number, renderH: number): SafeBox {
  return {
    top: insets.top * renderH,
    bottom: insets.bottom * renderH,
    left: insets.left * renderW,
    right: insets.right * renderW,
  };
}
