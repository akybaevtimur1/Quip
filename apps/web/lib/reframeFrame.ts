import type { CropOverride } from "@/lib/types";

// The reframe override that applies AT a given source-time `t` (last-wins), or null.
//
// A per-shot override only covers its own [source_start, source_end) — it must NOT colour the
// whole clip's live preview. A whole-clip override naturally contains every t. When none contains
// t, the caller falls through to the AI per-shot plan so non-overridden shots preview their real
// mode. (This mirrors the render, which recolours only the covered shots — the old preview took
// the last override unconditionally, so a single-shot "wide" turned the whole preview wide.)
export function pickActiveOverride(overrides: CropOverride[], t: number): CropOverride | null {
  let found: CropOverride | null = null;
  for (const o of overrides) {
    if (o.source_start <= t && t < o.source_end) found = o; // last match wins
  }
  return found;
}
