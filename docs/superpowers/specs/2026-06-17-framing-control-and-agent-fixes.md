# Framing control + agent/preview fixes — Design

> Approved 2026-06-17. Branch `feat/framing-and-agent-fixes`. Four independent items.

## #1 — Manual "force horizontal" mini-timeline (FEATURE)

**Goal:** let the user force a span of the clip to horizontal (fit) — or tight (fill) / back-to-auto —
snapping to auto-detected transitions, so framing mistakes are fixable without re-cutting.

- **UI:** new `apps/web/components/editor/FitTimeline.tsx` — a thin strip under the preview.
  Draws one proportional block per reframe region (a shot between transitions), tinted by current
  mode (fill/fit/split, or "override"). Drag to select a CONTIGUOUS span of segments; selection
  **snaps to region boundaries** (whole shots → clean cuts, never mid-shot). A `[Wide ▼]` control
  (Wide=fit / Tight=fill / Auto=clear) applies the mode to the selected source-time span.
- **Data:** the editor already loads `rawRegions` (clip-time `t0/t1/mode`) from `/reframe` and has
  `edit.source_intervals`. Map a region's clip-time → source-time: walk intervals with a cumulative
  offset (reverse of `regions_to_clip_time`); single-interval case = `source = interval.source_start + clipT`.
- **Backend (REUSE, no change):** `POST /jobs/{job}/clips/{clip}/edit/crop` with
  `{source_start, source_end, mode, center, center_b, version}`; `mode:"auto"` clears overrides in
  the range (`clear_crop_overrides`). API client `setCropOverride` already supports `mode: "auto"`.
- **Integration:** `ClipEditorScreen.tsx` renders `<FitTimeline>` under the `PreviewPlayer`,
  passes `rawRegions` + `source_intervals` + current `overrides` + `nowSec`, and a new
  `handleApplyRange(sourceStart, sourceEnd, mode)` that calls `setCropOverride` then reloads
  edit + reframe (reuse the existing `flushPending` → `setCropOverride` → `setEdit` + `loadReframe`
  pattern from `handleFrameApply`). The Frame tab stays (whole-clip mode + aspect).

## #2 — "Ambiguous → horizontal" auto rule (REFRAME LOGIC)

**Goal:** stop cropping when there's no confident subject; default to horizontal (fit).

- **Where:** `app/pipeline/stage3_reframe.py` → `plan_regions`, the FILL branch only.
- **Rule:** after `target = _pick_target(active, speak_threshold)`, choose fill **only if** the
  target is a confident subject: `target.speak >= speak_threshold` (clear speaker) OR
  `target.width >= _MIN_FACE_FRAC`. Otherwise (silent AND tiny/uncertain face) → emit a `fit`
  region (reset `prev_fill_end_cx=None`), like the no-face case. `_MIN_FACE_FRAC` = module
  constant, default **0.08** (face width as fraction of frame; tunable later — no config knob now
  to keep blast radius to one file).
- **Split unchanged** (user: handle split separately later). No-face and wide branches already → fit.
- **INVARIANT GUARD:** read `docs/REFRAME_FPS_GRID_INVARIANT.md`. This changes ONLY the per-shot
  mode CHOICE (allowed). Region boundaries stay on cut frames (`build_shots_frames` output) — do
  NOT touch `detect_scene_cuts`/`build_shots_frames`/fps wiring/`resample_track`/`aligned_start`.
- **TDD:** `tests/unit/test_stage3_reframe.py` — tiny silent face → fit; big face or clear speaker
  → fill; no face → fit (unchanged).

## #3 — Agent can analyze around the clip (TOOL FIX)

**Goal:** "analyze what's around this clip and trim well" failed because the agent had no tool/context
for transcript BEYOND the clip → it reached for a non-existent tool ("tool name error").

- **New tool `get_surrounding_transcript`** in `app/agent/tools.py`: returns transcript words in a
  window around the current clip (default ±~30s, capped) with SOURCE timestamps so the agent can
  pick clean sentence boundaries. Add to `_DISPATCH`. Pure window-selection helper → unit test.
- **Declare** in `app/agent/clip_agent.py` `_FN_DECLS` (params: optional `seconds_around`:number).
- **Prompt:** mention the new capability in the agent prompt (edit `prompts/agent_clip_editor.v1.txt`
  if it exists, else `DEFAULT_AGENT_PROMPT`) — "you can read surrounding transcript to choose clean
  cut points before calling set_interval."

## #4 — Editor reframe flash (PREVIEW COSMETIC — orchestrator handles)

**Hypothesis:** on a fill→fit transition the preview mounts a fresh blurred-bg `<video>` (D3:
only mounted in fit) that hasn't buffered → one black frame = flash; the baked grid clip has a
clean hard cut so never shows it. Investigate `PreviewPlayer.tsx`; apply a minimal low-risk
smoothing only if clearly that (e.g. warm/preload the bg, avoid the empty frame). User flagged it
as possibly one-off → don't over-engineer; report if not deterministically reproducible.

## Constraints
- New branch off `main`; `just check` green before commit; Conventional commits.
- No `models.py` contract change → no `just types` codegen. No frame-grid invariant geometry change.
- Keep the user's uncommitted doc edits untouched (stage only our files).
</content>
