# Next-session brief — Hook styling + editor lag/bugs

> Paste this as the session prompt. Follow the system: **read `docs/README.md` first**, then the
> code it points to, and **use the sub-agent system** (`superpowers:dispatching-parallel-agents`)
> for research/audit/parallel work. Keep docs in sync (CLAUDE.md §«Документация ⇄ код»).
> Editor touches captions/render — mind `docs/REFRAME_FPS_GRID_INVARIANT.md` if you go near render.

---

## Task A — Make HOOKS stylable like subtitles

Right now subtitles (captions) have full styling in the editor: a **Style tab** with 12 presets +
customization (color, size, font, position, animation, uppercase, emphasis). The **hook** (the
top-text plate) only has a **Hook tab** with text / on-off / window (whole clip vs first N sec) —
**no style picker**. Bring the hook to **parity**: pick style/preset, color, font, size, position,
animation — same UX as captions.

**Where it lives:**
- Hook model: `HookOverlay` inside `CaptionTrack` (services/worker/app/models.py); compiled into the
  SAME ASS as captions via `build_hook_event` (`app/pipeline/stage4_captions.py`) so preview == export.
- Front: `components/editor/HookTab.tsx` (current minimal hook UI), `StyleTab.tsx` (the rich caption
  styling to mirror), `CaptionsTab.tsx`, preset system (`app/editor/preset_seeds.py`, `presets.py`).
- Likely cleanest: reuse the `CaptionStyle` / preset machinery for the hook (a hook style ≈ a caption
  style), so you don't build a second styling system.

**Before coding: research ready-made / OSS (don't reinvent).** How do OpusClip / Captions / Submagic /
Zubtitle expose hook/title styling? Is there an OSS caption-styling UI or an ASS style-builder we can
lean on? Find prior art for "title/hook overlay style presets" before designing ours.

---

## Task B — Editor feels laggy + caption bugs (investigate root cause first)

Use `superpowers:systematic-debugging` — these are intermittent, so instrument before guessing.
Founder-reported symptoms (all in the clip editor `/edit/[jobId]/[clipId]`):

1. **Subtitles sometimes double/overlap** after editing captions and editing again. NOT always —
   intermittent. (Hypothesis to test: a stale libass layer / second draw not cleared, or a race where
   an old ASS render overlaps the new one. See `components/LibassLayer.tsx` + the ASS-refresh queue in
   `ClipEditorScreen.tsx`.)
2. **Changing caption type/preset makes subtitles jump position** (e.g. higher up the video), then
   they're hard to move back. (Hypothesis: the preset's `margin_v` overrides the user's manual
   position when a preset is applied — applying a style resets position. Decide: presets should keep
   the user's current position unless they explicitly change it.)
3. **Dragging subtitles in the preview is laggy / inconvenient.** (Hypothesis: drag updates only on
   `timeupdate` (~4Hz) + a CSS transition + a backend round-trip per move. Make the drag local/optimistic
   and smooth; persist on drop, not per pixel.)
4. **Lag EVERYWHERE — even changing style or animation has a big delay.** This is the big one.
   (Hypothesis: every tweak → PATCH to the worker → recompile ASS → re-fetch `/ass` → libass re-render
   in WASM, plus the single mutation queue serializes changes. The round-trip + recompile + WASM
   re-init per keystroke is the latency.) **Direction:** profile the change→repaint path; debounce
   rapid changes; consider compiling the ASS **client-side** for instant preview (only persist to the
   worker in the background) so style/animation/color changes are instant; avoid re-initializing the
   libass instance on every change. Look at how the OSS clippers get instant style preview (almost
   certainly client-side styling, no per-change server round-trip).

**Deliverable:** root-cause each symptom (with evidence), then fix — smooth, instant-feeling editor.
Keep preview == export (the WYSIWYG invariant: same ASS feeds libass preview and the ffmpeg burn).

---

## Guardrails
- WYSIWYG: whatever you change must keep **libass preview == ffmpeg export** (same compiled ASS).
- Don't touch the reframe frame-grid (Task B is captions/preview, not render geometry — but if you
  optimize the render path, read the invariant doc).
- Update `HookTab`/docs and `docs/JOURNAL.md` as you ship; bump `just types` if you change `models.py`.
