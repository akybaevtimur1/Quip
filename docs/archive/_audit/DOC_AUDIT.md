# Documentation Audit — Quip / ClipFlow

> **Generated 2026-06-15** by a read-only doc auditor. No existing file was edited.
> Purpose: inventory every project doc, flag what is authoritative vs. stale vs. archive,
> and give a brand-new agent a short, trustworthy reading order.

## Reality baseline used for this audit (current truth as of 2026-06-15)

These are LIVE and many docs predate them — any doc that says otherwise is flagged STALE/CONTRADICTS:

- **Billing is LIVE.** `BILLING_ENABLED` on; Polar webhooks working; Polar signature fix shipped.
- **Modal worker `quip-worker` is DEPLOYED** at `https://akybaevtimur7--quip-worker-web.modal.run`
  (functions `web`/`run_job`/`upload_job`/`render_job` live, `/healthz` 200).
- **Supabase project `qiagetbnsssvbiowuxpp`** with migrations **0001–0004 applied**.
- **Frontend deployed on Vercel project `quip-app`, AUTO-DEPLOYS on push to `main`.**
  → The repeated note "apps/web isn't deployed / the `quip` Vercel project = the landing repo"
  is **OUTDATED** wherever it appears.
- New shipped features: **subscription cancel (`/account`), feedback widget, site-wide support
  email (`ceo@quip.ink`), usage idempotency**.
- Pricing = credit model (Free $0/2 · Starter $10/10 · Pro $25/30 · PAYG $2). Source of truth =
  `services/worker/app/billing.py` mirrored by `apps/web/lib/plans.ts`.

---

## (a) Full doc inventory

Status legend: **AUTHORITATIVE** (current source of truth) · **STALE** (contains now-false claims) ·
**REDUNDANT** (overlaps another doc) · **HISTORICAL** (point-in-time report; archive, not a guide) ·
**CONTRADICTS** (directly conflicts with another doc — named).

### Root-level

| Path | Purpose | Audience | Status | Specific issue / fix |
|------|---------|----------|--------|----------------------|
| `CLAUDE.md` | Working rules + full chronological progress journal | new-agent | **AUTHORITATIVE (rules) / STALE (journal tail)** | Rules sections (1–11, code boundaries, type codegen) are current and binding. The 700+ line journal stops at `feat/modal-boevoy` (06-14) and predates live billing/Modal-deployed/Vercel-auto-deploy. Keep rules; treat journal as history. Still says "auth/payment = Phase 1+, не трогай" (rule 7) which is now obsolete in practice. |
| `CLIPFLOW_DEV_PLAN.md` | Phase 0 "thin pipeline" build plan (A→J) | task-specific | **HISTORICAL** | Phase 0 is fully done. Plan still names Railway hosting, Anthropic LLM, "лендинг не трогаем", repo path `clipflow`. Useful as origin-of-decisions archive, not a current guide. |
| `DESIGN.md` | Design system source of truth (tokens, type, color) for the production shell | founder / new-agent | **AUTHORITATIVE** | Current. Tokens in `apps/web/app/globals.css @theme`. One known caveat documented elsewhere: white-on-coral = 3.09:1 (fails strict AA) — accent Button is an app-wide a11y debt. |
| `AI-Shorts-System-Breakdown.md` | Notes on the OSS SamurAIGPT shorts generator (research reference) | task-specific | **HISTORICAL** | External research, not Quip's own architecture. Fine as a reference; not a guide. Candidate to move under `docs/research/`. |
| (no root `README.md`) | — | — | **MISSING** | There is no top-level README / index. This is the core problem the founder reported — nothing tells you where to start. The recommended fix is a single `README.md` or `docs/INDEX.md` pointing to the reading order below. |

### `docs/` — operational & reference

| Path | Purpose | Audience | Status | Specific issue / fix |
|------|---------|----------|--------|----------------------|
| `docs/HANDOFF.md` | "Read first" operational state: what works, how to run, gotchas | new-agent | **STALE / CONTRADICTS** | Header self-dates **2026-06-11** but body runs to 06-13. Pre-dates live billing + Modal deploy + Vercel auto-deploy. Contains a **DEMO PREP** section assuming a *local* worker on `:8000` and `NEXT_PUBLIC_WORKER_URL=http://<your-IP>:8000` — contradicts the now-live Modal URL. "K1 not done / no deploy plan / worker heavy, needs VPS" is obsolete (Modal live). Run instructions (PowerShell PATH refresh, `uv run`, `just check`) are still valid and valuable. **Biggest single confusion source** because it's labelled "read first" yet is the most out-of-date operational doc. Needs a refresh pass, not deletion. |
| `docs/NIGHT_AUDIT_REPORT_2026-06-15.md` | Latest night-audit summary: bugs fixed + founder action items | new-agent / founder | **AUTHORITATIVE (most current)** | The single most up-to-date doc. Confirms Modal deployed, migration 0003 applied, usage idempotency in prod, billing-ready. This should anchor the reading order. (It's dated a report but is effectively the current state-of-the-world.) |
| `docs/BACKEND_AUDIT.md` | Living layer-map (L0–L6) + regression ledger for the "works here/breaks there" bug class | task-specific / new-agent | **AUTHORITATIVE** | Current and high-value: the cleanest mental model of local-disk-SQLite vs cloud-R2-Postgres dual-mode. Ledger anchored at 06-14 (459→472 tests); slightly behind the 06-15 audit (~520 tests) but the layer map itself is correct. |
| `docs/BENCHMARKS.md` | Living table: speed/cost/quality per model + Modal cost measurements (§7) | task-specific | **AUTHORITATIVE** | Current, ongoing. Cost/latency reference. |
| `docs/EXTERNAL_SERVICES.md` | Which third-party services, why, cost, swap options | task-specific | **STALE** | "Active (Phase 0)" vs "Deferred (Phase 1+, NOT connected)" split is now wrong: R2, Modal, Supabase are LIVE, not deferred. Still lists Railway as the worker host (it's Modal) and Anthropic as the LLM target (it's Gemini). Swap-matrix concept is still useful; the active/deferred buckets need re-sorting. |
| `docs/SUPABASE_SETUP.md` | Checklist for the founder to wire Supabase + pricing | founder | **STALE** | Supabase is already wired (project live, 0001–0004 applied). Mentions **Lemon Squeezy** webhook (payment is Polar). Prices in the table ($12 Starter / 20 videos) are the **old plan model**, not the credit model (Starter $10/10). Superseded by reality + `DEPLOY.md`. Candidate to archive or rewrite as "how it's wired" rather than "to do". |
| `docs/REFRAME_FPS_GRID_INVARIANT.md` | The frame-grid invariant that kills reframe "flashes" — do-not-break | task-specific | **AUTHORITATIVE** | Critical, current, correctly referenced by HANDOFF, BACKEND_AUDIT, and night-audit README. Must-read before any reframe/render edit. |
| `docs/EVAL.md` | How to score clip quality (Q gate) | task-specific | **AUTHORITATIVE** | Stable tooling doc for `app.eval`. Niche but correct. |
| `docs/ROADMAP.md` | "Catch up to Opus Clip" priorities (06-08) | task-specific | **HISTORICAL / CONTRADICTS** | R1 done; R2–R6 partly absorbed elsewhere. Explicitly says "auth, paywall, real site, deploy = Phase 1+, NOT now" — **directly contradicts** current reality (all live). Archive. |
| `docs/PRODUCT_BRAINSTORM_2026-06-13.md` | Product strategy brainstorm (anti-lock-in exports, B-roll, monetization) | founder | **HISTORICAL** | Point-in-time ideation. Keep as strategy archive. |
| `docs/LAUNCH_BRIEF_2026-06-13.md` | Brief that kicked off the MVP-launch night (T1–T6) | founder | **HISTORICAL** | A task brief, now executed (see OVERNIGHT_REPORT). Archive. |
| `docs/OVERNIGHT_REPORT_2026-06-13.md` | Report of the T1–T6 MVP-launch night | founder | **HISTORICAL** | Point-in-time delivery report. Archive. |
| `docs/PRODUCTION_BRIEF_2026-06-13.md` | Brief for the production-shell session (design/landing/auth/dashboard/pay) | founder | **HISTORICAL** | Executed (see PRODUCTION_REPORT). Archive. |
| `docs/PRODUCTION_REPORT_2026-06-13.md` | Report of the production-shell session | founder | **HISTORICAL** | Point-in-time. Mentions auth/Polar "founder to wire" — now wired. Archive. |
| `docs/OVERNIGHT_MODAL_REPORT_2026-06-14.md` | Report of the Modal-worker + i18n night | founder / new-agent | **HISTORICAL / partly STALE** | Good architecture explainer for the dual-mode/Modal design, BUT its headline conclusions are now superseded: "Modal deploy = 1 founder step (NOT yet deployed)" and "Vercel `quip` = landing repo, apps/web push doesn't deploy" are **both now false** (Modal deployed; `quip-app` auto-deploys). Read for the *why* of the architecture, not for current deploy status. |
| `docs/BACKEND_DEBUG_BRIEF.md` | Brief that launched the layer-by-layer backend debug agent | task-specific | **HISTORICAL** | The brief behind `BACKEND_AUDIT.md`. Tells the agent to read CLAUDE.md + HANDOFF first. Archive (its output doc, BACKEND_AUDIT, is the keeper). |

### `docs/night-audit/` — 2026-06-15 swarm working docs

| Path | Purpose | Audience | Status |
|------|---------|----------|--------|
| `docs/night-audit/README.md` | Orchestration rules for the 15-agent debug swarm | task-specific | **HISTORICAL** (session protocol; good template for future swarms) |
| `docs/night-audit/REVIEW.md` | Independent review of the swarm's cumulative diff | task-specific | **HISTORICAL** |
| `docs/night-audit/BE-A…BE-I.md` (9) | Per-domain backend findings/fixes | task-specific | **HISTORICAL** (rolled up into `NIGHT_AUDIT_REPORT_2026-06-15.md`) |
| `docs/night-audit/FE-A…FE-F.md` (6) | Per-domain frontend findings/fixes | task-specific | **HISTORICAL** (rolled up into the same report) |

> These 17 files are the raw working notes whose conclusions live in `NIGHT_AUDIT_REPORT_2026-06-15.md`.
> Keep as an archive folder; a new agent should read only the rollup, not the 17 leaves.

### `docs/superpowers/specs/` and `/plans/` — design & implementation docs

| Path group | Purpose | Audience | Status |
|------------|---------|----------|--------|
| `specs/2026-06-07-phase1-reliability-design.md` + `plans/2026-06-07-phase1-k1-queue.md` | K1 RQ/Redis queue design (deferred, never built) | task-specific | **HISTORICAL** (explicitly deferred; queue still not built) |
| `specs/2026-06-08-continuous-reframe-design.md`, `plans/2026-06-08-active-speaker-reframe.md` | Reframe V2 / active-speaker designs | task-specific | **HISTORICAL** (superseded by Reframe v3 + the FPS-grid invariant) |
| `specs/2026-06-09-editor-core-design.md` + `plans/2026-06-09-editor-core-mvp.md` | Editor Core MVP | task-specific | **HISTORICAL** (shipped; superseded by Editor v2 → v3) |
| `plans/2026-06-09-reframe-cut-snap-flash-fix.md`, `specs/2026-06-10-quip-reframe-flash-fix-design.md` + `plans/...` | Flash-fix designs | task-specific | **HISTORICAL** (folded into `REFRAME_FPS_GRID_INVARIANT.md`, the live keeper) |
| `specs/2026-06-10-mvp-editor-roadmap-and-transcript-cache-design.md` + `plans/2026-06-10-transcript-cache.md` | Transcript cache design | task-specific | **HISTORICAL / partly OPEN** (transcript cache exists in cloud_state; HANDOFF still lists hash(source) cache as a TODO — partial) |
| `specs/2026-06-11-editor-v2-design.md` | Editor v2 | task-specific | **HISTORICAL** (superseded by v3) |
| `specs/2026-06-12-editor-v3-design.md` + `plans/2026-06-12-editor-v3.md` | Editor v3 (current editor) | task-specific | **HISTORICAL but most-relevant editor design** (the editor in prod is v3; read these if touching the editor) |
| `specs/2026-06-12-wysiwyg-libass-preview-design.md` | libass WYSIWYG preview design | task-specific | **HISTORICAL but live-relevant** (libass preview is in prod) |
| `specs/2026-06-12-infra-modal-deploy-design.md` + `plans/2026-06-12-infra-phase-a-state-migration.md` + `plans/2026-06-13-infra-scaling-cloud-worker.md` | Modal/cloud migration design | task-specific | **HISTORICAL** (now executed — Modal live; read for "why" only) |
| `specs/2026-06-13-auth-analytics-design.md` + `plans/2026-06-13-auth-analytics-plan.md` | Auth/analytics design | task-specific | **HISTORICAL** (auth shipped & live) |

> The entire `superpowers/` tree is design+plan history. None is a current "how it works" guide;
> each was the blueprint for one shipped feature. Keep as an `adr/`-style archive. A new agent
> rarely needs these except when re-touching that exact subsystem.

### `apps/web/`

| Path | Purpose | Audience | Status | Issue / fix |
|------|---------|----------|--------|-------------|
| `apps/web/CLAUDE.md` | One-liner `@AGENTS.md` include | new-agent | **AUTHORITATIVE** | Fine — just points to AGENTS.md. |
| `apps/web/AGENTS.md` | "This is Next 16, not the Next you know — read node_modules docs" | new-agent | **AUTHORITATIVE** | Short, current, important warning. Keep. |
| `apps/web/README.md` | Next app scaffold readme | task-specific | **REDUNDANT** | Stock create-next-app boilerplate; low value. Candidate to delete or replace with a one-line pointer to `DEPLOY.md`. |
| `apps/web/DEPLOY.md` | How to deploy the web app on Vercel | founder / task-specific | **STALE / CONTRADICTS** | Says "the existing Vercel `quip` project builds the OLD landing repo — create a NEW Vercel project from `Varenik-vkusny/Quip`." Reality: a `quip-app` Vercel project now exists and **auto-deploys on push to `main`**. The env-var table (NEXT_PUBLIC_WORKER_URL, Supabase, Polar) is still accurate and useful; the "create a new project" framing is obsolete. Fix: replace step 1 with "the `quip-app` project auto-deploys `main`; set `NEXT_PUBLIC_WORKER_URL` to the Modal URL." |
| `apps/web/PERF.md` | Lighthouse CI usage | task-specific | **AUTHORITATIVE** | Stable tooling doc. Keep. |

### `services/worker/` and `deploy/`

| Path | Purpose | Audience | Status | Issue / fix |
|------|---------|----------|--------|-------------|
| `services/worker/README.md` | Worker run instructions + pipeline overview | task-specific | **STALE (minor)** | Says REST is "Phase 0: only /healthz" — long outdated (full job/editor/billing API now). Run commands valid. Quick fix to the one stale line. |
| `deploy/modal/README.md` | Modal heavy-worker scaffold notes | task-specific | **STALE** | Framed as a "spike scaffold" that "only runs the heavy 3 functions; full storage/DB migration is a separate session." Reality: the full dual-mode worker is deployed. Read for ffmpeg-static rationale; update the "spike only" framing. |
| `services/captions-revideo-spike/README.md` | Revideo captions spike | task-specific | **HISTORICAL** | Abandoned spike (Approach B, deferred). Archive or delete with the spike folder. |

### Out of scope (not Quip docs — noted so the index can exclude them)

- `design-md/**` (≈75 brand folders × `DESIGN.md`+`README.md`, ~150 files): a **vendored design-reference
  library** (Airbnb, Linear, Stripe, etc.) used by design skills. NOT Quip documentation. The
  authoritative Quip design doc is the **root `DESIGN.md`**. Exclude `design-md/` from any doc index.
- `node_modules/**`, `**/.venv/**`, `**/site-packages/**`, `.pytest_cache/README.md`: dependency/tooling
  readmes — noise, exclude.

---

## (b) Biggest sources of confusion

1. **"Read first" is the most-stale operational doc.** `docs/HANDOFF.md` is explicitly the
   first-read file (CLAUDE.md says so) yet its DEMO-PREP / "run the worker locally on :8000 / set
   NEXT_PUBLIC_WORKER_URL to your IP" content contradicts the live Modal deployment, and it predates
   live billing. A new agent following it would set up a *local* stack and conclude nothing is deployed.
   **`docs/NIGHT_AUDIT_REPORT_2026-06-15.md` is actually the current truth but isn't pointed to as "read first."**

2. **The Vercel-deploy story is wrong in three places, right nowhere.** `apps/web/DEPLOY.md`,
   `docs/OVERNIGHT_MODAL_REPORT_2026-06-14.md`, and the auto-memory all say "the `quip` Vercel project
   = the landing repo; pushing apps/web doesn't deploy / create a new project." Reality: **`quip-app`
   auto-deploys `main`.** No single doc states the current deploy pipeline. This is the highest-value
   correction.

3. **Two contradictory pricing/payment models + a wrong payment provider in setup docs.**
   `docs/SUPABASE_SETUP.md` documents the **old plan model** ($12 Starter / 20 videos) and **Lemon
   Squeezy** as the webhook; the live model is the **credit model** ($10 Starter / 10 credits) with
   **Polar**. The true source is `billing.py` ↔ `lib/plans.ts`. SUPABASE_SETUP and EXTERNAL_SERVICES
   should be archived or rewritten — they will mislead anyone wiring billing.

4. **"Deferred / Phase 1+ / not yet" framing is everywhere but everything shipped.**
   `ROADMAP.md`, `EXTERNAL_SERVICES.md`, `CLIPFLOW_DEV_PLAN.md`, `SUPABASE_SETUP.md`, and CLAUDE.md
   rule 7 all say auth/payment/cloud/Modal are future work. They're all live. This single false premise
   recurs across ~5 docs.

5. **Volume of point-in-time reports with no archive marker.** 6 brief/report pairs at `docs/` root
   + 17 night-audit leaves + 20 superpowers specs/plans = ~45 historical files sitting beside the ~8
   living references, with nothing visually distinguishing "archive" from "guide."

---

## (c) Recommended reading order for a brand-new agent/session

Read these **in order**, then stop — everything else is reference-on-demand:

1. **`docs/NIGHT_AUDIT_REPORT_2026-06-15.md`** — the actual current state of the world (billing live,
   Modal deployed, Supabase migrations applied, open founder action items). Start here, not HANDOFF.
2. **`CLAUDE.md`** — but **only the "Железные правила" / code-boundary / type-codegen sections** (the
   binding rules). Skim the journal as history; do not treat its "deferred" notes as current.
3. **`docs/BACKEND_AUDIT.md`** — the layer map (L0–L6) and the dual-mode (local disk+SQLite vs cloud
   R2+Postgres) mental model. This is the best single explanation of how the system actually fits together.
4. **`docs/HANDOFF.md`** — for the **run/setup mechanics only** (PowerShell PATH refresh, `uv run`,
   `just check`, test datasets). Mentally override its deploy/billing/Vercel claims with item 1.
5. **`docs/REFRAME_FPS_GRID_INVARIANT.md`** — mandatory before touching any reframe/render code; skip
   only if you're not in that subsystem.

On demand: `DESIGN.md` (any UI work) · `apps/web/AGENTS.md` (any web code — Next 16 caveat) ·
`apps/web/DEPLOY.md` (deploy, with the stale step-1 caveat) · `docs/BENCHMARKS.md` (cost/latency) ·
the relevant `superpowers/specs/*` (only when re-touching that exact feature).

---

## (d) Candidates to archive or merge

**Move to an explicit `docs/archive/` (point-in-time, keep for history, not a guide):**

- `docs/LAUNCH_BRIEF_2026-06-13.md`, `docs/OVERNIGHT_REPORT_2026-06-13.md`
- `docs/PRODUCTION_BRIEF_2026-06-13.md`, `docs/PRODUCTION_REPORT_2026-06-13.md`
- `docs/OVERNIGHT_MODAL_REPORT_2026-06-14.md`, `docs/BACKEND_DEBUG_BRIEF.md`
- `docs/PRODUCT_BRAINSTORM_2026-06-13.md`, `docs/ROADMAP.md`
- `CLIPFLOW_DEV_PLAN.md`, `AI-Shorts-System-Breakdown.md` (latter → `docs/research/`)
- The whole `docs/night-audit/` folder (17 files) — keep, but it's already archive-shaped; the rollup
  `NIGHT_AUDIT_REPORT_2026-06-15.md` stays at `docs/` root.
- The whole `docs/superpowers/` tree (20 files) — treat as ADR archive; consider renaming to `docs/adr/`.
- `services/captions-revideo-spike/README.md` (abandoned spike).

**Rewrite (don't archive — they're referenced but wrong):**

- `docs/SUPABASE_SETUP.md` → either delete (superseded by `DEPLOY.md` + live reality) or rewrite as
  "how Supabase is wired" with the credit model and **Polar** (remove Lemon Squeezy + old prices).
- `docs/EXTERNAL_SERVICES.md` → move R2/Modal/Supabase from "Deferred" to "Active"; replace Railway→Modal
  and Anthropic→Gemini.
- `apps/web/DEPLOY.md` → replace step 1: `quip-app` auto-deploys `main`; keep the env-var table.
- `services/worker/README.md` → drop the "Phase 0: only /healthz" line.
- `deploy/modal/README.md` → drop the "spike scaffold only" framing (worker is fully deployed).

**Refresh in place (high traffic, must be trustworthy):**

- `docs/HANDOFF.md` → re-date, replace DEMO-PREP local-worker section with the live Modal URL, remove
  "not deployed / K1 / Vercel = landing repo" claims, update test count.
- `CLAUDE.md` → add a 2-line banner at the top of the journal: "billing live + Modal deployed +
  `quip-app` auto-deploys `main` as of 2026-06-15; entries below predate this." Soften rule 7.

**Delete / low value:**

- `apps/web/README.md` (stock create-next-app boilerplate).

**Create (the missing piece):**

- A single **`README.md` (root) or `docs/INDEX.md`** that states the current reality baseline (top of
  this file) and the 5-step reading order in (c). This is the founder's requested "single documentation
  index" and the one thing that fixes the "I can't tell which doc is authoritative" complaint.
