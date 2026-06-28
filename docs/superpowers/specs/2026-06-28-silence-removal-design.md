# Silence Removal — Design Spec

**Date:** 2026-06-28  
**Status:** Approved for implementation  
**Author:** Claude (brainstorm session with founder)

---

## 1. Feature Summary

Add an AI-powered "Remove silences" feature to the Quip clip editor. When enabled, the video player skips over pauses between words in real time — the user sees a "tight" cut podcast version without waiting for a re-render.

The feature mirrors how Descript's "Remove Silence" works: it uses the existing word-level timestamps from the Deepgram transcript (already available in `ClipOut.words`) to locate inter-word gaps above a configurable threshold and jump over them during playback.

**This spec covers Phase 1 only.** Phase 1 is purely client-side — zero new backend stages, zero re-renders. The downloaded/shared MP4 is still the original. Phase 2 (background re-render that bakes cuts into the video file) is outlined at the end but NOT implemented here.

---

## 2. Decisions Recorded (from Brainstorm)

| Decision | Choice | Rationale |
|---|---|---|
| Where does silence removal appear? | Per-clip toggle in editor + global "always on" setting | Match Descript UX; per-clip gives control, global saves repeated clicks |
| User control granularity | Slider (tightness) + Advanced panel | Simple for most users, tunable for power users |
| Preview mechanism | Client-side `video.currentTime` jump (no re-render) | Instant feedback; uses existing word timestamp data |
| Re-render timing | Phase 2 (deferred); Phase 1 = preview only | Test accuracy first with zero risk |
| Global setting scope | Two separate toggles: "Preview default on" + "Bake into file" | Phase 1 implements preview default; bake is stored but ignored until Phase 2 |

---

## 3. Phase Plan

### Phase 1 (this spec — implement now)
- Client-side silence skip in the video player
- Per-clip toggle + slider + advanced settings panel in the editor
- Global editing defaults in `/account` (preview default + bake placeholder)
- Persistence: global in `profiles.style_preferences` JSONB; per-clip in `ClipEdit.silence_config`
- Zero backend changes

### Phase 2 (deferred — outline only in §9)
- `POST /jobs/{jobId}/clips/{clipId}/apply-silence` endpoint
- New `pipeline/stage_silence_cut.py` using Silero VAD + FFmpeg concat
- Re-render produces a tight MP4 stored alongside (or replacing) the original in R2
- Timeline remapping for reframe regions (the hard part — outlined in §9)

---

## 4. Data Layer

### 4.1 `SilenceConfig` Type

Create **`packages/shared/src/silence.ts`** (or add to existing `types.ts` in shared):

```typescript
export interface SilenceConfig {
  enabled: boolean;
  min_pause_ms: number;   // gaps shorter than this are NOT cut (default: 400)
  padding_ms: number;     // ms of audio kept on each side of a kept segment (default: 50)
  max_pause_ms: number;   // gaps LONGER than this are intentional pauses — NOT cut (default: 2000)
}

export const SILENCE_CONFIG_DEFAULTS: SilenceConfig = {
  enabled: false,
  min_pause_ms: 400,
  padding_ms: 50,
  max_pause_ms: 2000,
};
```

**Slider mapping** (for the "Natural ↔ Tight" slider, a single `number` 0–100):
- Slider value 0 = Natural = `min_pause_ms: 800`
- Slider value 50 = Default = `min_pause_ms: 400`
- Slider value 100 = Tight = `min_pause_ms: 200`
- Formula: `min_pause_ms = Math.round(800 - (800 - 200) * (value / 100))`
- Reverse: `value = Math.round((800 - min_pause_ms) / 6)`

### 4.2 `ClipEdit` — Per-Clip Persistence

`ClipEdit` (in `packages/shared/`) gets a new optional field:

```typescript
// In ClipEdit (generated from backend models.py — add to both places)
silence_config?: SilenceConfig | null;
```

**Backend addition** — in `services/worker/app/models.py`, add to `ClipEdit`:
```python
silence_config: SilenceConfigModel | None = None
```

```python
class SilenceConfigModel(BaseModel):
    enabled: bool = False
    min_pause_ms: int = 400
    padding_ms: int = 50
    max_pause_ms: int = 2000
```

The existing `PATCH /clips/{clipId}/edit` endpoint (used for caption/hook edits) already accepts arbitrary `ClipEdit` fields — no new endpoint needed. Per-clip silence config is saved via the same `patchClipEdit` call already used for all other per-clip settings.

### 4.3 Global Settings — `profiles.style_preferences`

The JSONB `style_preferences` column (already used for style templates, hook timing, etc.) gets two new keys:

```typescript
// New keys inside profiles.style_preferences JSONB
interface StylePreferencesSilence {
  silence_preview_default: boolean;    // pre-check the toggle in editor for every clip (default: false)
  silence_bake_default: boolean;       // Phase 2: bake into rendered MP4 (stored now, ignored until P2)
  silence_min_pause_ms: number;        // global default for slider (default: 400)
  silence_padding_ms: number;          // global default for padding (default: 50)
  silence_max_pause_ms: number;        // global default for max pause (default: 2000)
}
```

These are read when the editor loads a clip: if `clip.silence_config` is null (clip has no saved config yet), fall back to the global profile values. If global values are also absent, use `SILENCE_CONFIG_DEFAULTS`.

**Priority chain:** per-clip `silence_config` → global `style_preferences` silence keys → `SILENCE_CONFIG_DEFAULTS`

---

## 5. Core Library — `lib/silenceMap.ts`

Create **`apps/web/lib/silenceMap.ts`**. Pure functions, no React, fully testable.

```typescript
import type { Word } from "@/lib/types";
import type { SilenceConfig } from "@clipflow/shared";

export interface TimeInterval {
  start: number; // absolute source seconds
  end: number;
}

/**
 * Given words in a clip, compute the intervals of audio to KEEP.
 * All times are absolute source seconds (matching Word.start / Word.end).
 *
 * A gap between word[i].end and word[i+1].start is CUT if:
 *   gap >= min_pause_ms/1000  AND  gap <= max_pause_ms/1000
 *
 * Gaps shorter than min_pause_ms: natural speech rhythm — keep.
 * Gaps longer than max_pause_ms: intentional dramatic pause — keep.
 *
 * padding_ms is added on both sides of every kept segment to avoid
 * clipping plosives and consonants at the boundary.
 */
export function computeKeepIntervals(
  words: Word[],
  clipStart: number,
  clipEnd: number,
  config: SilenceConfig,
): TimeInterval[] {
  const { min_pause_ms, padding_ms, max_pause_ms } = config;
  const minPause = min_pause_ms / 1000;
  const pad = padding_ms / 1000;
  const maxPause = max_pause_ms / 1000;

  // Only words within this clip's time range
  const clipped = words.filter(
    (w) => w.end > clipStart && w.start < clipEnd,
  );

  if (clipped.length === 0) {
    // No transcript data — return the whole clip uncut
    return [{ start: clipStart, end: clipEnd }];
  }

  const keeps: TimeInterval[] = [];
  // Start the first segment from (first word start - padding), clamped to clipStart
  let segStart = Math.max(clipStart, clipped[0].start - pad);

  for (let i = 0; i < clipped.length - 1; i++) {
    const gapStart = clipped[i].end;
    const gapEnd = clipped[i + 1].start;
    const gap = gapEnd - gapStart;

    if (gap >= minPause && gap <= maxPause) {
      // Cut this gap: close current segment with padding, open new one
      const segEnd = Math.min(clipEnd, gapStart + pad);
      if (segEnd > segStart) {
        keeps.push({ start: segStart, end: segEnd });
      }
      segStart = Math.max(clipStart, gapEnd - pad);
    }
    // gap < minPause → conversational rhythm, keep
    // gap > maxPause → intentional pause, keep
  }

  // Close the final segment
  const finalEnd = Math.min(clipEnd, clipped[clipped.length - 1].end + pad);
  if (finalEnd > segStart) {
    keeps.push({ start: segStart, end: finalEnd });
  }

  return keeps;
}

/**
 * Given absolute source time `t` and the keep intervals,
 * return the end of the silence gap if `t` is inside one,
 * or null if `t` is in a keep region.
 *
 * Used by the player to decide whether to seek forward.
 */
export function findSilenceEnd(
  t: number,
  keeps: TimeInterval[],
): number | null {
  if (keeps.length === 0) return null;
  for (let i = 0; i < keeps.length - 1; i++) {
    const gapStart = keeps[i].end;
    const gapEnd = keeps[i + 1].start;
    if (t >= gapStart && t < gapEnd) {
      return gapEnd;
    }
  }
  return null;
}

/**
 * Compute the "tight" duration of a clip (total keep time after silence cuts).
 * Used to display "X seconds saved" in the UI.
 */
export function tightDuration(keeps: TimeInterval[]): number {
  return keeps.reduce((sum, k) => sum + (k.end - k.start), 0);
}

/**
 * Compute the total silence cut from a clip.
 */
export function silenceCut(clipDur: number, keeps: TimeInterval[]): number {
  return Math.max(0, clipDur - tightDuration(keeps));
}
```

**Unit tests** — create `apps/web/lib/__tests__/silenceMap.test.ts`:

```typescript
import { computeKeepIntervals, findSilenceEnd } from "../silenceMap";

const WORDS = [
  { text: "Hello", start: 1.0, end: 1.3, confidence: 1, speaker: 0 },
  { text: "world", start: 1.35, end: 1.7, confidence: 1, speaker: 0 },  // gap 0.05s — keep
  { text: "this",  start: 2.3,  end: 2.6, confidence: 1, speaker: 0 },  // gap 0.60s — cut at 400ms
  { text: "is",    start: 2.65, end: 2.8, confidence: 1, speaker: 0 },  // gap 0.05s — keep
  { text: "great", start: 6.0,  end: 6.4, confidence: 1, speaker: 0 },  // gap 3.2s > 2000ms — keep
];

const CONFIG = { enabled: true, min_pause_ms: 400, padding_ms: 50, max_pause_ms: 2000 };

test("cuts gap above threshold", () => {
  const keeps = computeKeepIntervals(WORDS, 0, 10, CONFIG);
  // Gap of 0.60s between "world"(end=1.7) and "this"(start=2.3) should be cut
  expect(keeps.length).toBe(3);
});

test("keeps gap below threshold", () => {
  const keeps = computeKeepIntervals(WORDS, 0, 10, CONFIG);
  // Gap of 0.05s between "Hello" and "world" should not be cut
  expect(keeps[0].start).toBeCloseTo(1.0 - 0.05, 1); // first word - padding
});

test("keeps gap above max_pause (dramatic pause)", () => {
  const keeps = computeKeepIntervals(WORDS, 0, 10, CONFIG);
  // Gap of 3.2s between "is"(end=2.8) and "great"(start=6.0) > max_pause=2s → keep
  // So keeps[2] should include 2.8..6.0 uncut
  const lastKeep = keeps[keeps.length - 1];
  expect(lastKeep.start).toBeLessThan(6.0);
});

test("returns full clip when no words", () => {
  const keeps = computeKeepIntervals([], 5, 15, CONFIG);
  expect(keeps).toEqual([{ start: 5, end: 15 }]);
});

test("findSilenceEnd returns null when in keep region", () => {
  const keeps = [{ start: 1.0, end: 2.0 }, { start: 2.5, end: 3.5 }];
  expect(findSilenceEnd(1.5, keeps)).toBeNull();
});

test("findSilenceEnd returns gap end when in silence", () => {
  const keeps = [{ start: 1.0, end: 2.0 }, { start: 2.5, end: 3.5 }];
  expect(findSilenceEnd(2.1, keeps)).toBe(2.5);
});
```

---

## 6. Player Integration — `PreviewPlayer.tsx`

### 6.1 New Prop

Add `silenceIntervals` prop to `PreviewPlayer`:

```typescript
export function PreviewPlayer({
  src,
  outerStart,
  outerEnd,
  videoRef,
  frame,
  onTimeChange,
  aspectClass = "aspect-[9/16]",
  silenceIntervals,   // ← NEW
  children,
}: {
  // ... existing props ...
  silenceIntervals?: TimeInterval[] | null;  // from lib/silenceMap.ts
  children?: React.ReactNode;
}) {
```

### 6.2 Silence-Skip Inside Existing rVFC Loop

The existing `requestVideoFrameCallback` effect (lines 179–218 in current `PreviewPlayer.tsx`) already fires on every displayed frame. **Extend this effect** — do NOT add a second rVFC loop (that would cause competing seeks).

Add a `isSeeking` ref alongside the effect:

```typescript
const isSeekingRef = useRef(false);

// ── EXTEND the existing rVFC/rAF effect ──
// Inside the push() function or right after it, add:
const checkSilenceSkip = (mediaTime: number) => {
  if (!silenceIntervals || silenceIntervals.length === 0) return;
  if (isSeekingRef.current) return;
  const silenceEnd = findSilenceEnd(mediaTime, silenceIntervals);
  if (silenceEnd !== null) {
    isSeekingRef.current = true;
    try {
      video.currentTime = silenceEnd;
    } catch {
      /* noop */
    }
    // Reset on `seeked` event — not on a timeout — to avoid races
  }
};
```

**`seeked` event handler** — add to the existing event-listener `useEffect` (the one with `seekToStart`, `onTimeUpdate`, etc.):

```typescript
const onSeeked = () => {
  isSeekingRef.current = false;
};
video.addEventListener("seeked", onSeeked);
// ... in cleanup:
video.removeEventListener("seeked", onSeeked);
```

**Reset `isSeekingRef` when `silenceIntervals` changes** (user moves slider):

```typescript
useEffect(() => {
  isSeekingRef.current = false;
}, [silenceIntervals]);
```

**Full modified rVFC block** (replacing the current one):

```typescript
useEffect(() => {
  const video = videoRef.current as HTMLVideoElement & {
    requestVideoFrameCallback?: (cb: (now: number, meta: { mediaTime: number }) => void) => number;
    cancelVideoFrameCallback?: (id: number) => void;
  } | null;
  if (!video) return;

  let stopped = false;
  let rafId = 0;
  let vfcId = 0;

  const push = (t: number) => {
    setClipNow(Math.max(0, Math.min(clipDur, t - outerStart)));
    onTimeChange?.(t);
  };

  const checkSilence = (t: number) => {
    if (!silenceIntervals || silenceIntervals.length === 0) return;
    if (isSeekingRef.current || video.paused) return;
    const silenceEnd = findSilenceEnd(t, silenceIntervals);
    if (silenceEnd !== null) {
      isSeekingRef.current = true;
      try { video.currentTime = silenceEnd; } catch { /* noop */ }
    }
  };

  const rvfc = video.requestVideoFrameCallback;
  if (typeof rvfc === "function") {
    const onFrame = (_now: number, meta: { mediaTime: number }) => {
      if (stopped) return;
      push(meta.mediaTime);
      checkSilence(meta.mediaTime);
      vfcId = rvfc.call(video, onFrame);
    };
    vfcId = rvfc.call(video, onFrame);
  } else {
    const tick = () => {
      if (stopped) return;
      if (!video.paused) {
        push(video.currentTime);
        checkSilence(video.currentTime);
      }
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
  }

  return () => {
    stopped = true;
    if (rafId) cancelAnimationFrame(rafId);
    const cancel = video.cancelVideoFrameCallback;
    if (vfcId && typeof cancel === "function") cancel.call(video, vfcId);
  };
}, [videoRef, clipDur, outerStart, onTimeChange, silenceIntervals]);  // ← add silenceIntervals
```

**Import** `findSilenceEnd` and `TimeInterval` at the top of `PreviewPlayer.tsx`:
```typescript
import { findSilenceEnd, type TimeInterval } from "@/lib/silenceMap";
```

---

## 7. Editor UI — `SilenceTab.tsx`

Create **`apps/web/components/editor/SilenceTab.tsx`**.

### 7.1 Full Component

```typescript
"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Scissors } from "lucide-react";
import type { SilenceConfig } from "@clipflow/shared";
import { SILENCE_CONFIG_DEFAULTS } from "@clipflow/shared";
import { tightDuration, silenceCut, computeKeepIntervals, type TimeInterval } from "@/lib/silenceMap";
import type { Word } from "@/lib/types";

// Maps slider value 0-100 → min_pause_ms 800→200
function sliderToMs(v: number): number {
  return Math.round(800 - (800 - 200) * (v / 100));
}
function msToSlider(ms: number): number {
  return Math.round((800 - ms) / 6);
}

export function SilenceTab({
  config,
  words,
  clipStart,
  clipEnd,
  onChange,
}: {
  config: SilenceConfig;
  words: Word[];
  clipStart: number;
  clipEnd: number;
  onChange: (next: SilenceConfig) => void;
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // Live stats (pure, instant)
  const keeps: TimeInterval[] = config.enabled
    ? computeKeepIntervals(words, clipStart, clipEnd, config)
    : [];
  const clipDur = clipEnd - clipStart;
  const saved = config.enabled ? silenceCut(clipDur, keeps) : 0;
  const tight = config.enabled ? tightDuration(keeps) : clipDur;

  const patch = (partial: Partial<SilenceConfig>) =>
    onChange({ ...config, ...partial });

  const sliderValue = msToSlider(config.min_pause_ms);

  return (
    <div className="space-y-5 p-4">
      {/* Toggle row */}
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm font-medium text-ink">Remove silences</span>
          {config.enabled && saved > 0.1 && (
            <p className="text-xs text-muted mt-0.5">
              Saves {saved.toFixed(1)}s · tight clip {tight.toFixed(1)}s
            </p>
          )}
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={config.enabled}
          onClick={() => patch({ enabled: !config.enabled })}
          className={`relative inline-flex h-6 w-11 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
            config.enabled ? "bg-accent" : "bg-line"
          }`}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition-transform ${
              config.enabled ? "translate-x-5" : "translate-x-0"
            }`}
          />
        </button>
      </div>

      {/* Slider + label (only when enabled) */}
      {config.enabled && (
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-muted">
            <span>Natural</span>
            <span className="font-medium text-ink">
              Cutting pauses &gt; {config.min_pause_ms}ms
            </span>
            <span>Tight</span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={sliderValue}
            onChange={(e) =>
              patch({ min_pause_ms: sliderToMs(Number(e.target.value)) })
            }
            aria-label="Silence tightness"
            className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-line accent-accent"
          />
        </div>
      )}

      {/* Advanced settings collapsible */}
      {config.enabled && (
        <div className="rounded-lg border border-line">
          <button
            type="button"
            onClick={() => setAdvancedOpen((o) => !o)}
            className="flex w-full items-center justify-between px-3 py-2.5 text-xs font-medium text-muted hover:text-ink transition-colors"
          >
            <span>Advanced settings</span>
            {advancedOpen ? (
              <ChevronUp className="size-3.5" />
            ) : (
              <ChevronDown className="size-3.5" />
            )}
          </button>

          {advancedOpen && (
            <div className="space-y-4 border-t border-line px-3 pb-3 pt-3">
              {/* Padding */}
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <label className="text-muted">
                    Padding
                    <span className="ml-1 text-ink/60">(keeps Xms around speech)</span>
                  </label>
                  <span className="font-mono text-ink">{config.padding_ms}ms</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={150}
                  step={10}
                  value={config.padding_ms}
                  onChange={(e) =>
                    patch({ padding_ms: Number(e.target.value) })
                  }
                  aria-label="Padding around speech"
                  className="h-1 w-full cursor-pointer appearance-none rounded-full bg-line accent-accent"
                />
                <div className="flex justify-between text-[10px] text-muted/60">
                  <span>0ms</span>
                  <span>150ms</span>
                </div>
              </div>

              {/* Max pause to cut */}
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <label className="text-muted">
                    Keep pauses longer than
                    <span className="ml-1 text-ink/60">(dramatic pauses)</span>
                  </label>
                  <span className="font-mono text-ink">{config.max_pause_ms}ms</span>
                </div>
                <input
                  type="range"
                  min={500}
                  max={5000}
                  step={100}
                  value={config.max_pause_ms}
                  onChange={(e) =>
                    patch({ max_pause_ms: Number(e.target.value) })
                  }
                  aria-label="Max pause duration to cut"
                  className="h-1 w-full cursor-pointer appearance-none rounded-full bg-line accent-accent"
                />
                <div className="flex justify-between text-[10px] text-muted/60">
                  <span>0.5s</span>
                  <span>5s</span>
                </div>
              </div>

              {/* Reset to defaults */}
              <button
                type="button"
                onClick={() =>
                  onChange({
                    ...SILENCE_CONFIG_DEFAULTS,
                    enabled: config.enabled,
                  })
                }
                className="text-xs text-muted underline decoration-line underline-offset-2 hover:text-ink transition-colors"
              >
                Reset to defaults
              </button>
            </div>
          )}
        </div>
      )}

      {/* Phase 2 teaser — grayed out */}
      {config.enabled && (
        <div className="rounded-lg border border-line bg-surface/50 p-3">
          <div className="flex items-start gap-2">
            <Scissors className="mt-0.5 size-3.5 shrink-0 text-muted/50" />
            <div>
              <p className="text-xs font-medium text-muted/70">
                Bake into downloaded clip
              </p>
              <p className="mt-0.5 text-[10px] text-muted/50">
                Coming soon — will permanently cut silences in the MP4 file.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

---

## 8. Editor Integration — `ClipEditorScreen.tsx`

### 8.1 Add Silence State

```typescript
// Near other useState declarations
const [silenceConfig, setSilenceConfig] = useState<SilenceConfig>(SILENCE_CONFIG_DEFAULTS);
```

### 8.2 Load Silence Config on Clip Load

Inside the existing clip-load `useEffect` (where `edit`, `words`, `ass` are fetched and set):

```typescript
// After setting edit state:
const savedConfig = edit.silence_config;
if (savedConfig) {
  setSilenceConfig(savedConfig);
} else {
  // Fall back to global profile defaults
  const prefs = await fetchStylePreferences(); // already fetched elsewhere
  setSilenceConfig({
    enabled: prefs?.silence_preview_default ?? false,
    min_pause_ms: prefs?.silence_min_pause_ms ?? SILENCE_CONFIG_DEFAULTS.min_pause_ms,
    padding_ms: prefs?.silence_padding_ms ?? SILENCE_CONFIG_DEFAULTS.padding_ms,
    max_pause_ms: prefs?.silence_max_pause_ms ?? SILENCE_CONFIG_DEFAULTS.max_pause_ms,
  });
}
```

### 8.3 Persist on Change

```typescript
const handleSilenceChange = useCallback(
  (next: SilenceConfig) => {
    setSilenceConfig(next);
    // Debounce or fire immediately — same pattern as other ClipEdit patches
    void patchClipEdit(jobId, clipId, { silence_config: next });
  },
  [jobId, clipId],
);
```

### 8.4 Compute Keep Intervals (memoized)

```typescript
import { computeKeepIntervals, type TimeInterval } from "@/lib/silenceMap";

const silenceIntervals = useMemo<TimeInterval[] | null>(() => {
  if (!silenceConfig.enabled || words.length === 0 || !edit) return null;
  return computeKeepIntervals(
    words,
    edit.start,   // clip start in absolute source seconds
    edit.end,     // clip end in absolute source seconds
    silenceConfig,
  );
}, [silenceConfig, words, edit]);
```

### 8.5 Pass to PreviewPlayer

```typescript
<PreviewPlayer
  src={src}
  outerStart={outerStart}
  outerEnd={outerEnd}
  videoRef={videoRef}
  frame={frame}
  onTimeChange={onTimeChange}
  silenceIntervals={silenceIntervals}   // ← NEW
>
  {/* children */}
</PreviewPlayer>
```

### 8.6 Add Silence Tab to EditorRail

In **`EditorRail.tsx`**, add `"silence"` to the `TABS` constant:

```typescript
export const TABS = ["subtitles", "style", "frame", "hook", "silence", "agent"] as const;
export type Tab = (typeof TABS)[number];

// Tab icon/label mapping (wherever labels are defined):
// "silence" → icon: Scissors (lucide), label: "Silence"
```

### 8.7 Render SilenceTab

In the tab panel section of `ClipEditorScreen.tsx`:

```typescript
{tab === "silence" && edit && (
  <SilenceTab
    config={silenceConfig}
    words={words}
    clipStart={edit.start}
    clipEnd={edit.end}
    onChange={handleSilenceChange}
  />
)}
```

---

## 9. Global Settings — `AccountEditingDefaults.tsx`

Create **`apps/web/components/app/AccountEditingDefaults.tsx`**:

```typescript
"use client";

import { useState, useTransition } from "react";
import { SILENCE_CONFIG_DEFAULTS } from "@clipflow/shared";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { saveStylePreferences, fetchStylePreferences } from "@/lib/api";

export function AccountEditingDefaults() {
  const [previewDefault, setPreviewDefault] = useState(false);
  const [bakeDefault, setBakeDefault] = useState(false);  // stored, Phase 2 only
  const [isPending, startTransition] = useTransition();

  // Load on mount from profiles.style_preferences
  // useEffect(() => { fetch preferences → setPreviewDefault / setBakeDefault }, []);

  const save = (patch: Partial<{ silence_preview_default: boolean; silence_bake_default: boolean }>) => {
    startTransition(async () => {
      await saveStylePreferences(patch);
    });
  };

  return (
    <div className="rounded-lg border border-line bg-surface p-5 space-y-5">
      <Eyebrow tone="faint" as="h2">Editing defaults</Eyebrow>

      {/* Preview default */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-ink">
            Preview clips without silences by default
          </p>
          <p className="mt-0.5 text-xs text-muted">
            The silence toggle will be pre-checked in the editor for every new clip.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={previewDefault}
          disabled={isPending}
          onClick={() => {
            const next = !previewDefault;
            setPreviewDefault(next);
            save({ silence_preview_default: next });
          }}
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
            previewDefault ? "bg-accent" : "bg-line"
          } disabled:opacity-50`}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform ${
              previewDefault ? "translate-x-5" : "translate-x-0"
            }`}
          />
        </button>
      </div>

      {/* Bake default — disabled teaser */}
      <div className="flex items-start justify-between gap-4 opacity-50">
        <div>
          <p className="text-sm font-medium text-ink">
            Bake silence removal into rendered clips
          </p>
          <p className="mt-0.5 text-xs text-muted">
            Downloaded clips will have silences permanently removed.{" "}
            <span className="font-medium">Coming soon.</span>
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={false}
          disabled
          className="relative inline-flex h-6 w-11 shrink-0 cursor-not-allowed rounded-full border-2 border-transparent bg-line transition-colors"
        >
          <span className="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform translate-x-0" />
        </button>
      </div>
    </div>
  );
}
```

**Wire into `apps/web/app/(app)/account/page.tsx`**:

```typescript
// Add import:
import { AccountEditingDefaults } from "@/components/app/AccountEditingDefaults";

// Add to the main column (div.space-y-6) below AccountSecurity:
<AccountEditingDefaults />
```

---

## 10. Backend Changes (Phase 1 only — minimal)

### 10.1 `models.py` — Add `SilenceConfigModel` and `ClipEdit.silence_config`

```python
# In services/worker/app/models.py

class SilenceConfigModel(BaseModel):
    enabled: bool = False
    min_pause_ms: int = 400
    padding_ms: int = 50
    max_pause_ms: int = 2000

# Add field to ClipEdit:
class ClipEdit(BaseModel):
    # ... existing fields ...
    silence_config: SilenceConfigModel | None = None
```

### 10.2 Regenerate Shared Types

After editing `models.py`, run `just types` to regenerate `packages/shared/`. The `SilenceConfigModel` becomes `SilenceConfig` in TypeScript, and `ClipEdit.silence_config` becomes available.

**Do NOT manually edit `packages/shared/` — it is codegen-only.**

---

## 11. Edge Cases & How to Handle Them

| Edge case | Behavior |
|---|---|
| No words in clip (transcript empty) | `computeKeepIntervals` returns `[{ start: clipStart, end: clipEnd }]` — no cuts, player plays normally |
| User scrubs into a silence region | rVFC fires → `findSilenceEnd` detects it → seek to `silenceEnd` — feels like jump-cut seeking |
| All gaps are below `min_pause_ms` (very fast speaker) | No intervals cut; player plays normally; UI shows "0s saved" |
| Clip's `min_pause_ms` = 800ms and all gaps < 800ms | Same as above — no cuts |
| Trailing silence after last word | Not cut in Phase 1 (we don't have Silero VAD). The clip plays to `outerEnd` naturally. If `clip_tail_pad_sec=0.3` is already baked, it's fine. Phase 2 adds Silero VAD for this. |
| Leading silence before first word | Same — not cut in Phase 1 |
| Overlapping words (Deepgram rarely emits these) | `word[i].end > word[i+1].start` → `gap < 0` → `gap < minPause` → not cut. Safe. |
| User drags the slider while video is playing | `silenceIntervals` prop changes → rVFC effect re-runs with new intervals → `isSeekingRef` resets → immediately skips to correct position |
| `isSeekingRef` stuck true (seeked event not firing) | Shouldn't happen — `seeked` always fires after `currentTime` set. As insurance, reset `isSeekingRef` after 500ms in `checkSilence` if `video.seeking === false` |
| Phase 1: user downloads clip expecting tight version | The downloaded MP4 is the original. Make this clear in the UI: "Preview only — download tight version coming soon" (already shown in the "Bake" teaser) |

---

## 12. Files to Create / Modify

### Create (new files)

| File | Purpose |
|---|---|
| `apps/web/lib/silenceMap.ts` | Pure silence computation library |
| `apps/web/lib/__tests__/silenceMap.test.ts` | Unit tests |
| `apps/web/components/editor/SilenceTab.tsx` | Editor panel UI |
| `apps/web/components/app/AccountEditingDefaults.tsx` | Global settings component |

### Modify (existing files)

| File | Change |
|---|---|
| `services/worker/app/models.py` | Add `SilenceConfigModel`, `ClipEdit.silence_config` |
| `packages/shared/` | Regenerated via `just types` — do NOT edit manually |
| `apps/web/components/editor/PreviewPlayer.tsx` | Add `silenceIntervals` prop + silence-skip in rVFC |
| `apps/web/components/editor/ClipEditorScreen.tsx` | Add silence state, `useMemo` for intervals, pass to player, render `SilenceTab` |
| `apps/web/components/editor/EditorRail.tsx` | Add `"silence"` tab with Scissors icon |
| `apps/web/app/(app)/account/page.tsx` | Add `<AccountEditingDefaults />` |

### Shared types (after `just types`)

| Type | Package |
|---|---|
| `SilenceConfig` | `@clipflow/shared` |
| `ClipEdit.silence_config` | `@clipflow/shared` |

---

## 13. Local Test Plan (Phase 1 validation)

Run these checks before declaring Phase 1 done.

1. **Unit tests pass:**
   ```
   cd apps/web && npx jest silenceMap
   ```
   All 6 tests green.

2. **`just check` green:**
   - `ruff` + `mypy` on `models.py` change
   - `tsc` on new `.tsx` / `.ts` files (no type errors)
   - `eslint` clean

3. **Manual test — silence skip works:**
   - Open any clip in the editor with a podcast-style video
   - Switch to Silence tab
   - Toggle "Remove silences" ON
   - Press play — player should visibly skip pauses
   - Confirm no audio cut or stutter (smooth jump)
   - Drag slider → player immediately skips at new threshold

4. **Manual test — scrubbing:**
   - With silence ON, drag the scrub bar into a silence region
   - Player should snap forward to next speech segment

5. **Manual test — persistence:**
   - Set silence config on a clip → navigate away → return
   - Config should be restored (loaded from `ClipEdit.silence_config` via API)

6. **Manual test — global default:**
   - Go to `/account` → Editing defaults
   - Toggle "Preview clips without silences by default" ON
   - Open a new clip in the editor
   - Silence toggle should be pre-checked

7. **Manual test — no regression:**
   - With silence OFF, verify the player behaves exactly as before (no extra jumps, no stutter)
   - Verify reframe mode switching (tight↔wide) still works correctly

---

## 14. Phase 2 — Deferred Outline (Backend Re-render)

> **Do NOT implement in this session. This is a reference for the next phase.**

### 14.1 New Backend Endpoint

```
POST /jobs/{jobId}/clips/{clipId}/apply-silence
Body: { silence_config: SilenceConfig }
Response: { render_job_id: string }  # background Modal job
```

### 14.2 New Pipeline Stage — `stage_silence_cut.py`

**Input:** `source.wav`, `source.mp4`, clip `start`/`end`, `SilenceConfig`
**Output:** `keep_intervals: list[tuple[float, float]]` (absolute source seconds)

**Algorithm:**
1. Transcript-gap engine (same as Phase 1 client logic, ported to Python):
   ```python
   def compute_keep_intervals_from_words(words, clip_start, clip_end, config):
       # Same logic as lib/silenceMap.ts, ported to Python
   ```
2. Silero VAD complement (for leading/trailing silence the transcript misses):
   ```python
   # pip install silero-vad (MIT license, CPU-only, 0.43% CPU for 60min)
   from silero_vad import load_silero_vad, get_speech_timestamps
   model = load_silero_vad()
   audio = load_audio(wav_path, sample_rate=16000)
   vad_stamps = get_speech_timestamps(audio, model)
   # Merge with transcript-gap intervals
   ```
3. Merge both signals, apply padding, produce final `keep_intervals`.

### 14.3 FFmpeg Concat — No Re-encode

```python
# Build concat demuxer input file
with open("concat.txt", "w") as f:
    for start, end in keep_intervals:
        f.write(f"file '{source_mp4}'\n")
        f.write(f"inpoint {start}\n")
        f.write(f"outpoint {end}\n")

# Stream-copy — no re-encode, instant
subprocess.run([
    "ffmpeg", "-f", "concat", "-safe", "0",
    "-i", "concat.txt",
    "-c", "copy",           # stream copy = no quality loss, fast
    "tight_clip.mp4"
])
```

### 14.4 Reframe Region Remapping (the hard part)

Stage 3 (reframe) runs face detection on the original source timeline. The tight clip has a compressed timeline. Reframe regions stored in `job_artifacts.reframe_regions` are in original-source coordinates.

**Remapping algorithm:**
```
tight_time(t) = sum of keep_interval durations before t
```

For each `TrackRegion` in `reframe_regions`:
- `region.t0_tight = tight_time(region.t0)`
- `region.t1_tight = tight_time(region.t1)`
- If the region is entirely inside a cut silence → drop it
- If the region straddles a cut boundary → clip and remap

This remapping must happen before `stage5_render.py` so the crop trajectory is correct for the tight timeline.

### 14.5 What Triggers Re-render

- User downloads the clip while `silence_config.enabled = true` → trigger auto re-render before serving download URL
- OR: explicit "Apply & re-render" button in the Silence tab (replaces "Bake" teaser)
- Global `silence_bake_default = true` → run `stage_silence_cut` automatically after stage 2 for all clips in the job

---

## 15. Constants Reference

| Constant | Default | Range | Purpose |
|---|---|---|---|
| `min_pause_ms` | 400 | 200–800 | Primary slider: cut gaps above this |
| `padding_ms` | 50 | 0–150 | Buffer on each side of kept speech |
| `max_pause_ms` | 2000 | 500–5000 | Intentional dramatic pauses — do not cut |
| Slider "Natural" | 800ms | — | Cuts only long dead air |
| Slider "Tight" | 200ms | — | Cuts almost all inter-word gaps |
| Slider default position | 50/100 | — | Maps to 400ms |

---

*Spec written 2026-06-28. Brainstorm session: founder + Claude. Next step: invoke `writing-plans` skill to produce the implementation task list.*
