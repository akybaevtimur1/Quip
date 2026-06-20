# Editor "Fixed Studio" Redesign — Workstream A (design spec)

> Date: 2026-06-20 · Status: **approved direction, pre-implementation** · Owner: editor
> Part of the larger editor-overhaul program (see "Program context"). This spec covers **Workstream A only**.

## Program context

The clip editor (`/edit/[jobId]/[clipId]`, orchestrated by `apps/web/components/editor/ClipEditorScreen.tsx`)
is being overhauled across **5 workstreams**, each shipped as its own spec → plan → PR:

| WS | Scope | Status |
|----|-------|--------|
| **A** | **Editor IA / layout ("Fixed Studio") + framing-bug fix + restructure perf wins** | **this spec** |
| B | Background AI-agent architecture (navigation-safe, notifications, multi-run) | later |
| C | Canvas alignment guides + snapping + platform safe-areas | later |
| D | Style/preset persistence (clip → project → account → named presets → brand kit) | later |
| E | Final design + perf pass + critical re-review | later |

A is the backbone: it makes the canvas a **stable reserved region** and gives B/C/D clean seams
(agent-activity badge, presets rail item, canvas as snapping host). A does **not** implement B/C/D.

## Goal

A clean, fast, professional 9:16 clip editor where:
1. Opening any control panel **never resizes or repositions the video** (kills the #1 trust bug).
2. The structure is obvious and controls are 1–2 clicks away, optimized for editing **many clips fast**.
3. Switching clips is **instant** (no full-page remount).
4. The restructure itself removes layout-shift and avoidable re-renders.

## Problems being fixed (from the Phase-0 audit)

- **P0 — framing panel shrinks the video.** Confirmed *not* a resolution change. Root cause: `<main>` is
  `lg:overflow-visible` (`ClipEditorScreen.tsx:997`) so the shared grid row grows to the tallest tab, and
  the video is `flex-1` of that same row (`:1002`). Frame is the tallest tab (`FrameTab.tsx:110-132`), so
  opening it stretches the row → the video box changes size while its width stays pinned → reads as a
  resolution change. Worse on mobile (`sticky h-[44vh]` preview + tall scrolling panel).
- **P0 — Frame mode requires explicit "Apply"** (`FrameTab.tsx:155-165`) while every other control is live
  and the panel is literally labelled "Preview is live" — inconsistent exactly where the reflow confuses.
- **P1 — clip ‹ › nav is a full route remount + 4 cold fetches** (`EditorHeader.tsx:79,99` →
  `ClipEditorScreen.tsx:219-284`), no prefetch — the dominant latency for batch editing.
- **P1 — no keyboard shortcuts** anywhere.
- **P1 — `nowSec` (timeupdate ~4Hz) re-renders the whole 1240-line tree**; `frame`/`replyRanges` memos
  rebuild new object identities on every caption keystroke (`:898-924`, `:756-760`).
- **P1 — Hook tab overloaded** (text + presets + timing + a full duplicated style system,
  `HookTab.tsx:86-355`); **FitTimeline duplicates FrameTab's framing modes** via a different UI.
- **Cleanliness — built-in preset names are in Russian** (`preset_seeds.py`), violating the English-only rule.

## Chosen direction: "Fixed Studio"

A CapCut/Descript-style **fixed 3-zone frame** where the canvas is sized by the *viewport*, never by panel
content. Chosen over (a) "Floating Inspector" (Figma-style overlay panels — biggest canvas but heavier state
+ occlusion risk for a high-frequency tool) and (b) "Task Focus modes" (calm but adds a click per task switch,
hurting batch speed). Fixed Studio is the smallest conceptual leap from today's tabbed panel, structurally
eliminates the bug, and cleanly hosts the agent badge / presets / snapping.

### Layout

```
┌─ Header: ←Clips  ‹ Clip N/M ›  [agent-badge slot]      Render ▾ ─┐
├──┬───────────────────────────────────────────┬──────────────────┤
│Ag│            ┌────────────┐                  │  CONTEXTUAL      │
│Cp│            │    9:16    │   canvas sized    │  INSPECTOR       │
│Hk│            │   VIDEO    │   to viewport,    │  (fixed ~360px,  │
│St│            │ [caption ] │   NEVER to panel  │   internal       │
│Fr│            └────────────┘                  │   scroll)        │
│Pr│      FitTimeline strip (shrink-0)          │                  │
├──┴───────────────────────────────────────────┴──────────────────┤
│  TimelineV2 (whole-video, collapsible to trim strip)             │
└──────────────────────────────────────────────────────────────────┘
```

- **Left rail** (`EditorRail.tsx`, new): Agent · Captions · Hook · Style · Frame · Presets. Icon + label,
  active state, reserves a badge overlay slot on the Agent item (B fills it). Replaces the top tab-bar.
- **Center** (`EditorCanvas.tsx`, new): the stable-sizing box (see fix) hosting `PreviewPlayer`, `LibassLayer`,
  `OverlaySelectionBox` ×2, inline caption textarea, and the FitTimeline strip in a `shrink-0` slot.
- **Right** (`Inspector.tsx`, new): fixed-width container, `overflow-hidden` + inner `overflow-y-auto`;
  renders the active panel. On narrow viewports it becomes a right-edge **overlay** (canvas stays full size).
- **Header / footer**: keep `EditorHeader` + `TimelineV2`; header gains the agent-badge slot + shortcut hints.

## The framing-bug fix (mechanism)

1. Page grid stays `grid-rows-[auto_minmax(0,1fr)_auto]`. **Remove `lg:overflow-visible`** from the editor
   body; body is `min-h-0 overflow-hidden`.
2. Body = `grid-cols-[auto_minmax(0,1fr)_var(--inspector-w)]` → rail / canvas / inspector.
3. Inspector: `overflow-hidden` outer + `overflow-y-auto` inner → **its content height can never expand the
   row.**
4. Canvas column: `min-w-0 min-h-0 flex flex-col`; canvas-area `flex-1 min-h-0 grid place-items-center`;
   video `max-h-full max-w-full` + aspect class, `object-contain`. FitTimeline below in `shrink-0`.
5. **Result:** canvas height = stable row height (a function of viewport only). No tab, including Frame, can
   resize the video. Aspect changes scale *within* the stable box with a short `transition` so they read as
   intentional, not as breakage.

True clip resolution is unaffected (it always was — crop is fractional, `PreviewPlayer.tsx:230`). The
`"approximate crop / exact after render"` caveat copy (`FrameTab.tsx:167-171`) is removed once Frame is live
and stable.

## In-page clip switcher (no remount)

**Approach — keep the shell mounted, reset only the per-clip data layer.**

- `clipId` becomes **client state** of the editor shell instead of forcing a route remount. The route param
  still provides the *initial* clip (deep links / refresh work unchanged).
- ‹ › and any "open clip" action call `setActiveClip(id)`; the shell stays mounted (header/rail/canvas chrome
  persist). The URL is updated **shallowly** (no remount) so deep-linking/back still reflect the active clip.
  *(Next 16 caveat: the exact shallow-URL API must be confirmed against `node_modules/next/dist/docs/` before
  coding — candidates are `window.history.replaceState`/`pushState`, which Next supports, vs a router shallow
  option.)*
- **Per-clip reset is reused, not rebuilt.** The existing load effect already keys on `[jobId, clipId, loadKey]`
  and resets all per-clip state (`ClipEditorScreen.tsx:219-284`); with `clipId` as state, that same effect
  re-runs on switch and resets `edit/words/assText/rawRegions/renderState/editingReply/...` **without
  unmounting**.
- **Durability is preserved.** The keepalive flush effect is keyed `[jobId, clipId]`
  (`ClipEditorScreen.tsx:433-456`); its cleanup runs `persistNow()` on every `clipId` change, so pending
  caption edits for the outgoing clip are flushed before the new clip loads — same guarantee as today's
  unmount, now firing on in-page switch too.
- **Mutation-queue isolation.** `patchChain` / `pendingCaptionsRef` / `flushTimerRef` / `optGenRef` /
  `assSeq` must be **reset on clip switch** so an in-flight PATCH or stale ASS for clip A cannot apply to
  clip B. (New: clear the debounce timer + reset the pending refs and the chain to `Promise.resolve()` as part
  of the switch.)
- **Agent reconnect** rewires to the new clip (today `AgentTab` is keyed by clipId; under WS-A it still
  reconnects per active clip — full global background behavior is WS-B).
- **Prefetch.** Warm adjacent clips' `edit`/`ass`/`reframe` into a small in-memory cache on idle, so ‹ › uses
  warm data. Cache is keyed by clipId and bounded (e.g. current ±1).

This converts the dominant batch-editing latency (multi-second cold remount) into an instant swap, while
reusing the existing, correctness-critical reset/flush effects rather than rewriting them.

## Inspector content reorg (this pass)

- **Live Frame mode**: remove the explicit "Apply to clip" button; frame-mode changes apply live (debounced),
  matching every other control. Keep a "Reset framing" affordance. (Fixes P0 inconsistency.)
- **De-overload the Hook tab**: split into a compact primary section (show toggle · text · regenerate ·
  timing) and a collapsible "Style" section, removing the deep-scroll wall (`HookTab.tsx:86-355`). No new
  capabilities — reorganization only.
- **Merge FitTimeline into the Frame inspector context** (remove the duplicate per-shot framing UI under the
  canvas vs. FrameTab modes). The canvas keeps a *minimal* framing strip only where it aids direct
  manipulation; the authoritative per-region framing controls live in the Frame inspector.
- **English-ify built-in preset names** (`preset_seeds.py`) — server-side `name` strings only; no behavior
  change. (Preset *persistence/scopes* remain WS-D.)

## Perf (falls out of the restructure)

- **Inspector is its own memoized subtree** → the ~4Hz `nowSec` tick stops re-rendering the controls.
- **Stabilize `frame` memo identity** — return the previous object reference when the resolved crop is
  shallow-equal, so `PreviewPlayer` doesn't re-render every tick on static-crop clips.
- **Scope `replyRanges`/active-reply recompute** to `edit.captions.replies` + `words` (not full `edit`
  identity) so style keystrokes don't walk all words.
- **Keyboard shortcuts**: `Space` play/pause · `[` / `]` prev/next clip · `1–6` rail · `R` render ·
  `Esc` close overlay / cancel inline edit. (Disabled while typing in an input/textarea.)
- **CLS eliminated** by the stable canvas.

## UX states & edge cases

- **Loading**: canvas skeleton + inspector skeleton; the existing 4× backoff retry on cold worker stays.
- **Error**: non-blocking top banner (unchanged).
- **libass failure**: `simplified preview` badge stays (honest, no silent fallback).
- **Aspect change**: canvas scales within the stable box with a short transition.
- **Narrow viewport**: inspector → right overlay (slides over the gutter; canvas unchanged behind it);
  timeline collapses; rail stays.
- **Agent activity**: badge slot on the rail's Agent item is present but inert in WS-A (placeholder for B).
- **Clip switch mid-edit**: pending caption edits flushed (keepalive) before the new clip loads; in-flight
  render state for the old clip is dropped from the UI (the render still completes server-side).

## Creator's-eye lens (the bar every decision is held to)

The editor is a tool a creator opens **dozens of times a day** to grind through many clips. It must feel
*effortless and smooth*, never fiddly. Concretely, A is validated by walking the real creator journey and
demanding it feels good at each step:

**The journey (what a creator actually does, in order):**
1. Open a clip → **video is playing/ready instantly**, captions visible, nothing jumps. No "where do I click."
2. Glance at the framing → looks right, or one click on the rail to adjust — **the video does not move when I
   open the panel** (the whole reason for this redesign).
3. Tweak caption style / hook → **changes appear live on the video as I drag/click**, no "Apply", no reload.
4. Fix one caption's wording → tap it on the video, type, Enter. Done.
5. Trim the start/end → drag the timeline, the preview follows.
6. Hit **next clip** → it's *instant*, my place is kept, my last edits are saved without me thinking about it.
7. Render/Export when happy → clear that "live preview" is now being written to the file.

**Smoothness principles (non-negotiable, enforced in review):**
- **Zero layout jank.** Nothing reflows, jumps, or resizes from opening a panel, switching a tab, or changing
  aspect. Transitions are short and purposeful (≤200ms), never gratuitous.
- **Live, not modal.** Every visual edit reflects on the canvas immediately; "Apply"/round-trips are removed
  or hidden behind optimistic preview. The creator never wonders "did that take?".
- **Autosave is invisible but trustworthy.** Edits persist on their own (debounced + flush-on-switch); the
  "saving/saved" signal is calm and the "render writes to file" concept is unmistakably separate from saving.
- **Minimal clicks, predictable placement.** Common actions (caption text, hook text, framing, next clip) are
  1–2 clicks and always in the same place; the rail order matches frequency of use.
- **Keyboard-first for power users**, mouse-first for everyone — both fully supported, neither required.
- **Fast perceived performance.** Instant clip switching (prefetch), no full-tree re-renders on playback,
  skeletons not spinners, optimistic UI everywhere.
- **Forgiving.** Inline edits are escapable (Esc), framing is resettable, nothing is destructive without intent.

**Verification = dogfooding as a creator.** Before WS-A is "done", drive the live authed editor in a real
browser (Playwright MCP persistent session — memory: live-editor-browser-access) **as a creator would**:
open a real job, switch across several clips, tweak captions/hook/framing on each, on 9:16 + 1:1 + 4:5 + 16:9,
and confirm every smoothness principle holds. Screenshots captured for the before/after. A "unit tests pass"
result is *not* sufficient evidence the editor feels good — the felt experience is judged by eye.

## Out of scope (WS-A) — seams left for later

- Background-agent global store / notifications / multi-run (B) — rail badge slot + per-clip reconnect only.
- Alignment guides / snapping / safe-area overlays (C) — canvas is the host; no guides yet.
- Preset persistence / scope picker / brand kit / "apply to all" (D) — Presets rail item opens today's gallery.
- Deep perf instrumentation + editor Lighthouse budget (E).

## Risks & invariants to preserve

- **Do not touch the mutation/reconciliation machinery's semantics** — `patchChain`, `optGenRef`/`assSeq`
  anti-clobber, `flushCaptions`/`flushPending` durability. We only (a) reset them on clip switch and (b) move
  the JSX around them. These took production bugs to get right.
- **No silent fallbacks** (rule #8): clip-switch flush failures, prefetch failures, shallow-URL failures must
  surface or be explicitly best-effort-logged, never swallowed.
- **English-only user-facing text** for every new/edited string.
- **Next 16 caveat**: read `node_modules/next/dist/docs/` before writing the shallow-routing + any new
  client component.
- **Reframe frame-grid Δ=0**: WS-A does not touch `stage3_reframe`/`stage5_render`/`reframe_cache`; live
  Frame mode only changes *when* `setCropOverride` is called (debounced vs Apply), not the crop math.
- Visual changes verified for real (live authed browser / `/dev` harness), not blind.

## Testing strategy

- **Pure-logic TDD**: the prefetch cache (bounded, keyed), the keyboard-shortcut dispatcher (ignore-while-typing
  + key→action map), the `frame`-identity stabilizer, and the clip-switch reset reducer get failing unit tests
  first.
- **No-regression**: the mutation-queue/flush behavior must keep its existing tests green; add a test that a
  clip switch flushes pending edits and resets the chain.
- **Visual/manual**: framing bug gone (switch every tab on 9:16/1:1/4:5/16:9 — canvas size invariant);
  clip ‹ › is instant; shortcuts work; narrow-viewport overlay doesn't resize the canvas. Verified in the live
  authed editor via Playwright MCP persistent browser (memory: live-editor-browser-access).
- Gate: `just check` green before commit.

## File-level change plan (sketch — refined in the implementation plan)

**New (web):** `EditorRail.tsx`, `EditorCanvas.tsx`, `Inspector.tsx`, a `useClipSwitch`/prefetch hook, a
keyboard-shortcut hook.
**Changed (web):** `ClipEditorScreen.tsx` (compose the shell, `clipId` as state, reset-on-switch, remove
`overflow-visible`/`flex-1` coupling), `EditorHeader.tsx` (badge slot, shortcut hints, switch via callback not
`router.push`), `FrameTab.tsx` (live mode, drop Apply), `HookTab.tsx` (split sections), `FitTimeline` (fold into
Frame context), the `(app)/edit/[jobId]/[clipId]/page.tsx` (initial-clip handoff to client state).
**Changed (worker):** `editor/preset_seeds.py` (English names only).
**Unchanged:** all caption mutation/ASS reconciliation logic; reframe/render; billing; types contract.

## Open questions

None blocking. The only implementation-time unknown is the exact Next 16 shallow-URL API, resolved by reading
`node_modules/next/dist/docs/` during implementation.
