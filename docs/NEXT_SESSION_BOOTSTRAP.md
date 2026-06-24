# Next-session bootstrap prompt

> Paste the block below as your **first message** in a new Claude Code session on Quip. It tells the
> agent what to read (and in what order) so it understands the project + docs before doing anything,
> then waits for your task. Keep it in sync if the reading order in `docs/README.md` changes.

---

You are working on **Quip (ClipFlow)** — a LIVE production product (video → AI-selected vertical
shorts with explainability). Before doing ANY work, get oriented by reading, IN THIS ORDER, and DO NOT
write code or run commands until you have:

1. **`docs/README.md`** — the single source of truth for "current reality" (what's live, deploy map,
   invariants, reading order). If any other doc contradicts it, this file wins.
2. **`CLAUDE.md`** — the binding rules (TDD on pure logic, `just check` green before every commit,
   types are codegen from `services/worker/app/models.py` via `just types` — never hand-edit
   `packages/shared/*`, no silent fallbacks, English-only user-facing text, use parallel sub-agents
   for non-trivial work). The long journal section is HISTORY — don't treat "deferred/Phase 1+" notes
   as current; it all shipped.
3. **`docs/CORE_ARCHITECTURE_AND_FEATURES.md`** — the living deep-dive: how the whole system works
   (stack, pipeline, data model, AI features, frontend). The single best explanation of how it fits together.
4. **`docs/HANDOFF.md`** — run/setup mechanics (PowerShell PATH refresh, `uv run`, `just check`, test datasets).
5. **Task-specific, only what applies** (see the table in `docs/README.md` "How to brief an agent"):
   - Cross-surface bug (grid vs editor / local vs cloud) → **`docs/BACKEND_AUDIT.md`** (L0–L6 map + ledger).
   - Reframe / render / "flashes" → **`docs/REFRAME_FPS_GRID_INVARIANT.md` (MANDATORY before any
     `stage3_reframe`/`stage5_render`/`reframe_cache` edit)**.
   - Web/UI → `apps/web/AGENTS.md` (Next 16 has breaking changes — read before frontend code) + `DESIGN.md`.
   - Billing/credits → `app/billing.py` (source of truth) + `app/polar.py` + README "Money paths".
   - Cost/model choice → `docs/BENCHMARKS.md`.

Environment gotchas (from `CLAUDE.md`) — honor these every time:
- **Run pipeline/ffmpeg/`just`/`uv` via PowerShell**, and refresh PATH first in EACH call:
  `$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`.
  The Bash tool lacks ffmpeg/just/uv.
- **Commit from PowerShell** (pre-commit hook runs `just check`); Cyrillic commit messages → write to a
  UTF-8 file + `git commit -F <file>` (piping mangles encoding).
- **Deploy:** frontend auto-deploys on push to `main` (Vercel `quip-app`); worker = `modal deploy
  deploy/modal/worker.py` (set `$env:PYTHONIOENCODING="utf-8"` first on Windows). Modal hits SHARED
  PROD — there is no per-branch worker env.
- **Verify interactive/visual changes for real** (live authed browser or a `/dev` harness), not blind —
  several past bugs only showed live. Branch + verify before merging anything outward-facing.

When you've read the above, give me a one-paragraph confirmation of the current reality + the
invariants you'll respect, then **wait for my task.** When I give it: if it's non-trivial, restate it,
plan briefly (and for a bug, root-cause first via systematic-debugging — don't guess), then implement
with TDD, keep docs in sync in the same pass, and gate with `just check` before committing.
