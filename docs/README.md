# Quip — Documentation Index (START HERE)

> **This is the single entry point.** Docs were written session-by-session and got scattered —
> this file is the map: what's TRUE right now, what to read (and in what order), what's just
> history, and what you must NOT break. If a doc contradicts this file, **this file wins** for
> "current reality"; the older doc is kept only for the *why*/history.
>
> Last reality check: **2026-06-15.**

---

## 🟢 Current reality (the baseline — many older docs predate this)

- **It's LIVE in production.** Not a local prototype anymore.
- **Frontend:** Vercel project **`quip-app`** — **auto-deploys on every push to `main`**.
  (The old note "apps/web isn't deployed / the `quip` Vercel project is the landing repo" is
  **OUTDATED**. `quip` = old landing; `quip-app` = the real app.)
- **Worker:** Modal app **`quip-worker`** — `https://akybaevtimur7--quip-worker-web.modal.run`
  (functions `web` / `run_job` / `upload_job` / `render_job`; `/healthz` → 200). Redeploy =
  `modal deploy deploy/modal/worker.py` (on Windows set `PYTHONIOENCODING=utf-8` first).
- **State:** Supabase Postgres project **`qiagetbnsssvbiowuxpp`**, migrations **0001–0005 applied**
  (billing, credits, usage-idempotency, feedback, promo codes). Clips in **Cloudflare R2**
  (`cdn.quip.ink`).
- **Billing is ON** (`BILLING_ENABLED`). Payments via **Polar** (NOT Lemon Squeezy). Webhook live
  and verified. Pricing = **credit model** (Free $0 / 2 · Starter $10 / 10 · Pro $25 / 30 · PAYG $2);
  source of truth = `services/worker/app/billing.py`, mirrored by `apps/web/lib/plans.ts`.
- **Auth:** Supabase (Google OAuth + email). The `(app)` route group is gated.
- **Uploads = direct browser→R2** (presigned PUT), NOT through the worker. `POST /jobs/upload-url`
  → browser PUTs straight to R2 → `POST /jobs/{id}/upload-complete` spawns processing. Needs an R2
  **CORS rule** on the bucket (set in Cloudflare dashboard — done; JSON in `deploy/modal/r2_setup.py`).
  Local dev still uses the old multipart `POST /jobs/upload`. (Old single-POST path broke on big files.)
- **Editor preview video = a lightweight `preview.mp4` proxy** (≤720p H.264 faststart, made per job),
  served via CDN (`cdn.quip.ink`); source also CDN now. Render still uses the full source. Old jobs
  fall back to source. (Editor video used to load the full 50–160 MB source → slow.)
- **Vercel Analytics** is wired (`<Analytics/>`), invisible. ⚠️ Must be **enabled once** in the Vercel
  project dashboard (Analytics tab) for data to flow.
- **Pipeline needs audio:** a video with no audio track fails early with a clear message (Quip cuts on speech).

### Shipped (this is "all of it" up to 2026-06-15)
Phase 0 pipeline → Editor v3 → production shell (landing/auth/dashboard/pricing) → Modal deploy →
night-audit bug sweep → **billing live** (Polar signature fix, PAYG decrement, usage idempotency)
→ **subscription cancel** (`/account`) → **feedback widget** (floating, → Supabase `feedback`) →
**site-wide support email** (`ceo@quip.ink`) → **promo codes** (`redeem_promo` RPC; code `PODCAST2`
= 2 credits live) → **upload-only source form** (YouTube link hidden for now) → **Free per-video cap
removed** (video length limited only by remaining minutes + 3h technical ceiling) → dashboard
flash fix → **hook styling parity** (preset gallery + controls + entrance animation + drag) →
**editor lag/UX** (instant client-side caption preview, durable edits, libass stale-frame fix, preset
no longer resets position, "All clips" → grid directly) → **Vercel Analytics** → **editor video speedup**
(preview-proxy + CDN) → **upload rewrite** (direct browser→R2, fixes large uploads) → no-audio clear
error. Founder account = Pro + 1000 credits (for testing).

> 2026-06-15 detail → `docs/JOURNAL.md` (last two entries). ⚠️ The upload architecture changed this
> session — read the "Upload ПЕРЕПИСАН на direct→R2" journal entry before touching the upload path.

---

## 📖 Read in this order (new agent / new session), then stop

1. **`docs/README.md`** ← you are here (reality + map).
2. **`CLAUDE.md`** — the **rules** (Железные правила, code boundaries, type codegen, commit gate).
   Binding. The long journal below the rules is **history** — skim, don't treat "deferred/Phase 1+"
   notes as current (it all shipped).
3. **`docs/BACKEND_AUDIT.md`** — the layer map (L0–L6) + the **dual-mode** model (local disk+SQLite
   vs cloud R2+Postgres). Best single explanation of how the system fits together.
4. **`docs/HANDOFF.md`** — for **run/setup mechanics only** (PowerShell PATH refresh, `uv run`,
   `just check`, test datasets). ⚠️ Ignore its deploy/billing/DEMO-PREP sections — outdated; trust
   §"Current reality" above instead.
5. **`docs/REFRAME_FPS_GRID_INVARIANT.md`** — **mandatory before ANY reframe/render edit.**

On demand: `DESIGN.md` (UI work) · `apps/web/AGENTS.md` (Next 16 caveat — read before web code) ·
`docs/BENCHMARKS.md` (cost/latency) · the matching `docs/superpowers/specs/*` (only when re-touching
that exact feature) · `docs/ADMIN_PANEL_RESEARCH.md` (monitoring spend/usage).

---

## ⛔ Do NOT break (invariants)

- **Reframe frame-grid (Δ=0).** Read `docs/REFRAME_FPS_GRID_INVARIANT.md` before touching
  `stage3_reframe` / `stage5_render` / `reframe_cache`. Breakage shows ONLY on ≠25fps video; unit
  tests stay green. The "flashes" come back if you break it.
- **Type contract.** Types are codegen from `services/worker/app/models.py` → `just types`. Never
  hand-edit `packages/shared/*`. Changing `models.py` → run `just types`.
- **Money paths.** `billing.py` is the source of truth for plans/credits; `lib/plans.ts` mirrors it
  (change BOTH). Polar webhook signature uses the **raw secret bytes** as the HMAC key (Polar quirk —
  see `app/polar.py`). PAYG credits + usage are idempotent per `job_id` — keep it that way.
- **Commit gate.** `just check` (ruff + mypy + tsc + eslint + unit tests + anti-drift) must be green
  before every commit. Commit from PowerShell (pre-commit hook needs `just` on the refreshed PATH);
  if ruff-format reformats, `git add` + recommit.
- **No silent fallbacks** (rule #8): errors must surface (JobError / failed status), never `except: pass`.

---

## 🤖 How to brief an agent (copy-paste)

> "Read `docs/README.md` first (the reality baseline + reading order). Then read [X] for this task."

Pick [X] by task:

| Task | Read |
|------|------|
| Anything backend | `CLAUDE.md` rules + `docs/BACKEND_AUDIT.md` |
| Reframe / render / "flashes" | `docs/REFRAME_FPS_GRID_INVARIANT.md` (mandatory) |
| Editor (timeline/captions/preview) | `docs/superpowers/specs/2026-06-12-editor-v3-design.md` + `…wysiwyg-libass-preview…` |
| Billing / Polar / credits | `app/billing.py`, `app/polar.py`, this file's "Money paths" |
| UI / design | `DESIGN.md` + `apps/web/AGENTS.md` |
| Deploy / infra | "Deploy & infra map" below (ignore `apps/web/DEPLOY.md` step 1) |
| Cost / model choice | `docs/BENCHMARKS.md` |

---

## 🏗️ Deploy & infra map

| Piece | Where | How it deploys | Dashboard |
|-------|-------|----------------|-----------|
| Frontend (`apps/web`) | Vercel **`quip-app`** | **auto on push to `main`** | vercel.com/timurkas-projects/quip-app |
| Worker (`services/worker`) | Modal **`quip-worker`** | `modal deploy deploy/modal/worker.py` | modal.com (workspace akybaevtimur7) |
| State / auth / billing data | Supabase **`qiagetbnsssvbiowuxpp`** | SQL Editor / migrations `0001–0005` | supabase.com dashboard |
| Clip storage | Cloudflare **R2** (`cdn.quip.ink`) | n/a | Cloudflare dashboard |
| Payments | **Polar** (production) | products + webhook configured | polar.sh dashboard |

Secrets: worker reads Modal secrets `quip-worker` (Deepgram/Gemini/Supabase/R2) + `quip-billing`
(`BILLING_ENABLED` + `POLAR_WEBHOOK_SECRET` + product IDs). Frontend reads Vercel env
(`NEXT_PUBLIC_SUPABASE_*`, `NEXT_PUBLIC_WORKER_URL`, `POLAR_ACCESS_TOKEN`, `POLAR_SERVER`).

---

## 📦 Doc status (so you know what's a guide vs. history)

**🟢 Living / authoritative** (trust these):
`docs/README.md` (this) · `CLAUDE.md` (rules) · `DESIGN.md` · `docs/BACKEND_AUDIT.md` ·
`docs/BENCHMARKS.md` · `docs/REFRAME_FPS_GRID_INVARIANT.md` · `docs/EVAL.md` · `apps/web/AGENTS.md` ·
`apps/web/PERF.md` · `docs/ADMIN_PANEL_RESEARCH.md` · `docs/NIGHT_AUDIT_REPORT_2026-06-15.md`.

**🟡 Useful but partly stale** (read with the banner caveat at their top):
`docs/HANDOFF.md` (run mechanics ✓, deploy/billing ✗) · `apps/web/DEPLOY.md` (env table ✓, "create
a new Vercel project" ✗) · `docs/EXTERNAL_SERVICES.md` · `docs/SUPABASE_SETUP.md` (Lemon Squeezy/old
prices ✗).

**📦 History / archive** (the *why*, not a current guide): `CLIPFLOW_DEV_PLAN.md` · `docs/ROADMAP.md` ·
all `docs/*BRIEF*` / `*REPORT*` / `PRODUCT_BRAINSTORM*` / `OVERNIGHT_*` · the whole
`docs/night-audit/` folder (rolled up into `NIGHT_AUDIT_REPORT_2026-06-15.md`) · the whole
`docs/superpowers/` tree (specs/plans = ADRs per shipped feature).

> Full per-doc table + rationale: **`docs/_audit/DOC_AUDIT.md`**.
> Not Quip docs (ignore): `design-md/**` (vendored brand reference), `node_modules/**`, `.venv/**`.
