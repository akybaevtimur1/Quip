# Brief: full-stack, layer-by-layer debug of Quip (eliminate the _class_ of bugs)

You are a long-running debugging agent on **Quip** (repo root `C:\Users\user\Desktop\ClipClow`,
GitHub `Varenik-vkusny/Quip`). Read `CLAUDE.md` and `docs/HANDOFF.md` first, then this brief.

## Why you exist

We keep hitting the **same class of bug**: something works in one place and breaks in another —
editor vs. the clips grid, local vs. cloud (Modal/R2/Supabase), the batch render vs. the editor
render, preview vs. exported file. Point-fixing one symptom keeps regressing another layer
("fixed here, broke there"). **Stop point-fixing. Map the system into layers and debug it
layer by layer, root cause first, with a regression guard so a lower-layer fix never silently
breaks a layer you already verified.** Take as long as you need. Investigate _everything_.

## The root pattern to hunt

**Divergent paths / duplicated logic / silent fallbacks.** Examples already seen:

- Two caption renderers (editor libass vs. grid CSS overlay) → different animations, missing hook.
- The batch render makes a _clean_ clip; the editor render **overwrites** `clips/<id>.mp4` with a
  _captions-burned_ one → the grid then double-draws captions.
- Cloud-only failures: `media/<job>/reframe_<clip>.json` 404 (not uploaded to R2), the source video
  `<video>` throwing `NotSupportedError` (the editor mounts the source 4× — master + blur-bg + 2
  split halves — all with `src` set even when hidden), `willReadFrequently` canvas spam.
- Dual-mode (disk+SQLite local vs. R2+Postgres cloud) divergence in URLs/artifacts.
- "Two downloads" on upload (client upload, then a server stage labelled like a download).

These are **symptoms of one disease**: the same job/clip/caption/reframe data takes different
code paths in different surfaces/environments, and nobody owns the single source of truth.

## Method — non-negotiable

1. **Use the `superpowers:systematic-debugging` skill discipline.** No fix without a reproduced
   root cause. Add evidence/instrumentation at each component boundary before proposing a fix.
2. **Map the architecture into layers, then work in dependency order (bottom → top).** Suggested
   layers (refine as you learn):
   - **L0 Environment & parity** — local (disk, SQLite, bundled ffmpeg) vs. cloud (Modal, R2,
     Supabase Postgres, static ffmpeg). Most bugs are "works local, breaks cloud." You MUST
     exercise BOTH paths, not just local.
   - **L1 Storage / artifacts** — `app/storage.py`, `app/artifacts.py`: what files exist, their
     names, which are uploaded to R2 vs. only on disk, how they're served (presigned 302).
   - **L2 State** — `app/db.py`, `app/cloud_state.py`, `app/store.py`: job/clip/edit/render rows,
     dual-mode adapters, `row_to_wire` URL resolution.
   - **L3 Pipeline** — `app/run.py`, `app/pipeline/*`, `app/editor/*`, `app/tasks.py`: import →
     transcribe → select → reframe → captions → render; what gets burned when; the clean-vs-burned
     file question; the REFRAME_FPS_GRID Δ=0 invariant.
   - **L4 API** — `app/main.py`: every endpoint, what URLs/shapes it returns, edit-state lazy
     creation, `/render`, `/ass`, `/export/*`, `/media`, CORS, upload.
   - **L5 Frontend data** — `apps/web/lib/*`: `api.ts` URL resolution, dual-mode, auth headers.
   - **L6 Frontend UI** — `apps/web/components/*`: editor, grid, `ClipPreview`, players, progress.
     For each layer: list its **contracts and invariants**, find every place a path **diverges or
     duplicates**, reproduce the failure with evidence, fix at the source (unify on ONE path / ONE
     source of truth), verify with real output.
3. **Regression guard.** Keep a running checklist (in the audit doc below) of every behaviour you
   have verified. After fixing any layer, re-run `just check` AND re-verify the previously-green
   items — especially anything in a layer below the one you just changed. Never declare a layer
   done until everything beneath it is still green.
4. **Protect the hard invariants** (do not regress these):
   - **REFRAME_FPS_GRID Δ=0** — mode-region boundaries land exactly on cut frames (no flashes).
     Verify with the existing `tmp/dod_*` style direct reframe checks.
   - **WYSIWYG** — editor preview == grid preview == exported file. One ASS, one renderer.
   - **No silent fallbacks / no `except: pass`** — surface errors (JobError + failed status).
   - `just check` green before every commit (lint + mypy + tsc + unit + anti-drift; pre-commit
     hook enforces it — commit from PowerShell with the registry PATH refresh).
5. **Prefer unification over patching.** When two paths disagree, the fix is usually to delete one
   and route both through the other — not to make the second path mimic the first.

## Seed symptom list (NOT exhaustive — find the rest yourself)

- `render_clip_edit_job` (`app/tasks.py`) overwrites `clips/<id>.mp4` with a burned file → decide
  the right model (e.g. keep the clip file clean forever, render captions to a separate file,
  point downloads at it) so preview/grid/editor/export never disagree and never double-draw.
- Cloud: `reframe_<clip>.json` 404 (editor frame preview can't get the real fit/fill/split plan →
  falls back to center-fill → editor crop ≠ rendered crop). Either serve it from R2 or expose it
  via an endpoint.
- Cloud: source `<video>` `NotSupportedError` ×N and the source mounted 4× in `PreviewPlayer` →
  lazy-load secondary videos; verify 302-presigned playback across all video elements.
- Upload UX: client upload + server "preparing" stage (already relabelled) — confirm there is no
  _actual_ redundant fetch/transcode, only the inherent R2 round-trip.
- Editor↔grid parity for captions/hook/karaoke (just unified to libass — verify on cloud).
- `ExportMenu` "With captions" currently points at the clip's own URL — confirm it resolves to the
  truly captioned file in every state (clean / rendered / edited-after-render).

## Deliverables

- A **living audit doc** `docs/BACKEND_AUDIT.md`: the layer map, every divergence found, the root
  cause, the fix, and the **evidence** (commands + real output) per item, plus the regression
  checklist you keep re-running.
- One focused commit per fix, conventional commits, `just check` green each time.
- A final report: what was structurally wrong, what you unified, what invariants now hold, and
  anything that needs the founder (secrets/deploy/product decisions).

## Constraints

- **Do NOT touch** `apps/web/app/(auth)/login` or `/signup` (another agent owns them).
- Don't create the founder's cloud secrets or deploy on their behalf; if a check needs the live
  cloud, say exactly what to run.
- Repo is `Varenik-vkusny/Quip`; the web app deploys separately from this repo (see memory) — your
  job is correctness in the code, not deploying.
- When you genuinely can't reproduce without the live cloud, instrument + document the exact repro
  and hand it back rather than guessing.
