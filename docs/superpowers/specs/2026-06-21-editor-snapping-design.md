# Editor Alignment Guides + Snapping — Workstream C (design spec)

> Date: 2026-06-21 · Status: **approved, implementing** · Owner: editor
> Part of the editor-overhaul program. Builds on WS-A (Fixed-Studio shell, stable canvas, aspect-contain).

## Goal

When the user drags the hook or captions on the video, alignment **guide lines** appear and the element
**snaps** to meaningful positions — horizontal/vertical center, canvas edges, platform **safe-area**
boundaries (TikTok / Reels / Shorts), and the *other* element — so placement feels precise and effortless
(Figma/Canva/CapCut-style). Snapping is helpful, not aggressive: a small threshold, a clear guide line,
**hold `Alt` to suspend**, and a snap on/off toggle.

## Context (where it plugs in)

- `OverlaySelectionBox.tsx` owns the on-video drag. During `onBodyMove` it positions the box
  **imperatively** (`node.style.left/top` as % of the render box) with **zero React state per move**, and
  commits center-X + anchored-edge fractions on `onBodyUp`. Snapping hooks into `onBodyMove` (adjust the
  px left/top before writing the style) and `onBodyUp` (the committed fractions reflect the snapped box).
- The render box = `node.offsetParent` (PreviewPlayer's inner aspect box, now correctly sized after WS-A).
- `ClipEditorScreen` already holds both elements' live rects (`subRects: { hook, caption }`) and renders
  both `OverlaySelectionBox`es — so it can pass each box the *other's* rect + the snap config.
- Coordinates: the box geometry from `getBoundingClientRect()` is **screen px**; the render box is screen
  px. Snapping math runs in render-box-relative px (so threshold is a real screen distance).

## Architecture — decide vs. draw (mostly pure, TDD'd)

### Pure logic (unit-tested, no DOM)
- **`lib/snapEngine.ts`** — the heart.
  ```ts
  interface DragBox { left: number; top: number; width: number; height: number } // px in render box
  type Axis = "x" | "y";
  interface SnapTarget { axis: Axis; pos: number; kind: GuideKind } // pos = px line on that axis
  type GuideKind = "center" | "edge" | "safe" | "element";
  interface SnapResult { left: number; top: number; guides: GuideLine[] }
  interface GuideLine { axis: Axis; pos: number; kind: GuideKind }
  function computeSnap(box: DragBox, targets: SnapTarget[], threshold: number): SnapResult;
  ```
  For each axis, the box exposes candidate **features**: `x` → left edge, center-x, right edge;
  `y` → top edge, center-y, bottom edge. For every (feature, target-on-same-axis) pair within
  `threshold` px, it picks the **nearest** per axis, shifts `left`/`top` so that feature lands exactly on
  the target line, and emits a `GuideLine` at the target. At most one snap per axis (nearest wins). No
  match → unchanged + no guide. Pure, deterministic.
- **`lib/snapTargets.ts`** (pure): `buildTargets(renderW, renderH, other, safe) → SnapTarget[]`.
  Emits: canvas centers (x=W/2, y=H/2, kind "center"); canvas edges (x=0,W; y=0,H, "edge"); safe-area
  boundaries from `safe` ("safe"); and the other element's center-x + edges ("element"). `other` is the
  other element's `{left,top,width,height}` in render-box px (or null); `safe` is the active platform's
  fractions (or null when "Off").
- **`lib/safeAreas.ts`** (pure data): per-platform safe-zone **fractions** of the 1080×1920 frame
  (refinable; sourced from the WS-A research). Approximate v1 values:
  ```ts
  // {top, bottom, left, right} as fractions (0..1) of the frame; the SAFE region is inside these.
  tiktok: { top: 0.06,  bottom: 0.83, left: 0.055, right: 0.89 }
  reels:  { top: 0.115, bottom: 0.80, left: 0.055, right: 0.945 }
  shorts: { top: 0.20,  bottom: 0.80, left: 0.05,  right: 0.82 }
  ```
  Multiply by render-box dims to get px lines. (Values are design-tunable constants, not magic in logic.)

### DOM (imperative, zero re-render during drag)
- **`SnapGuides.tsx`** — a guide-line overlay absolutely covering the render box, exposing an **imperative
  ref API** `{ show(lines: GuideLine[]): void; hide(): void }`. Pre-renders a small fixed pool of line
  divs; `show` positions/colors the active ones (thin **magenta** lines, full span of the render box) and
  `hide` clears them. Driven by `OverlaySelectionBox` during the gesture — no React state per move.
- **`SafeAreaOverlay.tsx`** — draws the active platform's safe-zone rectangle (dashed border + a small
  label like "TikTok safe") over the canvas; rendered only when a platform is selected. Purely visual;
  its boundaries also feed `snapTargets` so elements snap to them.

### Wiring
- `OverlaySelectionBox` gains props: `otherRect: OverlayRect | null`, `safe: SafeAreaConfig | null`,
  `snapEnabled: boolean`, and `guidesRef` (the `SnapGuides` imperative handle). In `onBodyMove`, after
  computing raw `left/top`, if `snapEnabled && !e.altKey`: build targets (memoized per-gesture from the
  render box + otherRect + safe), run `computeSnap`, use the snapped `left/top`, and `guidesRef.show(...)`.
  Else `guidesRef.hide()`. On `onBodyUp`/cancel: `guidesRef.hide()`. The commit math is unchanged — it
  reads the final (snapped) box rect, so the persisted fraction is the snapped one.
- `ClipEditorScreen` owns: `snapEnabled` + `safePlatform` state (init from **localStorage**), renders one
  `SnapGuides` (shared, inside the canvas) + the `SafeAreaOverlay`, and passes each `OverlaySelectionBox`
  the other element's rect (`subRects.hook`/`subRects.caption`) + the resolved `safe` config + `snapEnabled`
  + the `guidesRef`.
- **Controls** (`SnapControls.tsx` or inline on the canvas): a small magnet toggle (snap on/off) + a
  "Safe area: Off / TikTok / Reels / Shorts" segmented picker, sitting unobtrusively on the canvas (e.g.
  top-right corner overlay). Both persist to `localStorage` (keys `quip.editor.snap`, `quip.editor.safe`).

## Behavior & defaults
- **Threshold:** 8px screen distance (forgiving but not sticky).
- **Suspend:** hold `Alt` during a drag → no snapping, no guides (free placement).
- **Toggle off:** the magnet toggle disables snapping entirely (guides never show).
- **Guides:** thin magenta lines, shown ONLY during an active drag, cleared on release.
- **Safe-area overlay:** off by default; when a platform is picked, its zone draws on the canvas and its
  boundaries become snap targets. Persisted locally.
- **YAGNI v1:** no numeric distance labels, no equal-spacing-between-3+-elements (only 2 movable elements
  exist: hook + caption). Center+edges+safe+element covers the useful cases. Easy to extend later.

## Out of scope (seams for later)
- Cross-clip / cross-project persistence of the snap/safe preference (that's **WS-D** — v1 uses localStorage).
- Snapping the resize/width gestures (v1 snaps the MOVE gesture only).
- Distance/measurement labels.

## Invariants / constraints
- Preserve the **zero-re-render drag** (snapping + guides are imperative; no React state per pointermove).
- Preserve commit semantics (center-X + anchored-edge fractions; `clamp01`).
- The render box stays the overlay measurement element (don't disturb `offsetParent`).
- English-only user-facing strings ("Snap", "Safe area", platform names). No silent fallbacks (localStorage
  read failures fall back to defaults explicitly).
- Next 16: client components only; no routing changes.
- Does not touch reframe/render, billing, or types contract.

## Testing
- **TDD pure logic:** `snapEngine` (snaps a feature within threshold to the nearest target per axis;
  ignores beyond threshold; one snap per axis; empty targets → identity; multi-axis snap), `snapTargets`
  (emits the expected center/edge/safe/element lines from given dims + otherRect + safe; null other/safe
  handled), `safeAreas` (fraction → px mapping; each platform's region is inside the frame).
- **Visual dogfood (login-gated, user):** drag hook/caption → guide appears + snaps at center/edges; snaps
  to the other element; safe-area overlay shows + snaps; `Alt` suspends; toggle off disables; feels smooth
  (no jank), commit persists the snapped position.
- Gate: `just check` green (incl. the new vitest specs).

## File-level plan (sketch — refined in the implementation plan)
**New (web):** `lib/safeAreas.ts`, `lib/snapTargets.ts`, `lib/snapEngine.ts` (+ their `.test.ts`),
`components/editor/SnapGuides.tsx`, `components/editor/SafeAreaOverlay.tsx`, `components/editor/SnapControls.tsx`.
**Changed (web):** `components/editor/OverlaySelectionBox.tsx` (snap hook in move + guides), `ClipEditorScreen.tsx`
(snap/safe state from localStorage, render SnapGuides/SafeAreaOverlay/SnapControls, pass props to both boxes),
possibly `lib/overlayBox.ts` (a px-rect helper if useful).
**Unchanged:** mutation/ASS machinery, reframe/render, types contract, billing.
