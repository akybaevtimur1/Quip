# Founder Admin / Monitoring Panel — Research & Recommendation

> Goal: ONE place for the founder to watch (1) Modal spend, (2) Deepgram usage/balance,
> (3) Gemini/Google usage, (4) Cloudflare R2 usage, (5) user traffic + consumption + cost
> (videos, minutes, credits, per-user spend).
>
> Constraint (founder): **do NOT reinvent the wheel** — use ready-made/off-the-shelf first,
> build custom only where necessary. Budget is solo-founder tier ($8–10/mo infra).
>
> Date: 2026-06-15. Stack confirmed from repo: Modal (`deploy/modal/worker.py`),
> Deepgram (`stage1_transcribe.py`), Gemini (`stage2_select`), Cloudflare R2 (`app/storage.py`),
> Supabase Postgres (tables `profiles`/`usage_events`/`jobs`/`feedback`,
> `migrations/0001..0004`), pricing in `app/billing.py` + `docs/BENCHMARKS.md`.

---

## TL;DR Recommendation

**Don't build a unified panel. Bookmark 4 provider dashboards + build ONE tiny thing for the
data only WE have.**

1. **Cost/spend (Modal, Deepgram, Gemini, R2):** bookmark each provider's native billing
   dashboard. All four have one. **No custom code.** Set a **budget alert** in each (the real
   value — "money left" → "tell me before I burn it"). Cost-per-provider APIs exist if we ever
   want to pull them, but for a solo founder at launch that's over-engineering.
2. **User traffic / consumption / per-user cost:** this is the ONLY data no provider has — it
   lives in our Supabase Postgres. Visualize it with **Supabase Studio → Reports** (custom SQL
   chart blocks, built into the dashboard we already pay $0 for). **No custom code, no extra tool.**
3. **Later (only if it earns its keep):** a small `/admin` page in the Next app, or Metabase, if
   the founder wants the consumption view embedded next to live job status / one shared link.

MVP = **4 bookmarks + 4 budget alerts + ~5 saved SQL "Report" charts in Supabase.** Effort: an
afternoon. Cost: **$0**. Zero new infrastructure to maintain.

---

## Part 1 — Provider-native dashboards & APIs (spend / usage)

Every provider we use exposes a spend/usage dashboard, and all four also have a programmatic API.
For a solo founder the **dashboard + budget alert** is the right tool; the API is documented here
only so we know the upgrade path exists.

### Modal (compute — the biggest variable cost)

- **Dashboard:** yes. Refreshed billing UI for all workspaces; shows spend over time, supports
  **workspace budgets** and **incremental billing thresholds** (alert/cap before overspend).
  → This is the "money left on Modal" view. **Bookmark + set a workspace budget.**
- **API / CLI:** yes — `modal billing report` CLI and the `modal.billing.workspace_billing_report`
  API generate tabular spend reports over a date range (`--start/--end` or `--for "last month"`),
  broken down by App or tag (`--tag-names`).
  - ⚠️ **Caveat 1:** these are GA "for all Team and Enterprise plan workspaces." On an
    individual/free workspace the **dashboard is the reliable path**; confirm CLI access once the
    founder's plan is set.
  - ⚠️ **Caveat 2:** report totals are computed **before credits/reservations**, so the API number
    can exceed the actual invoice. For "am I about to run out of money," trust the dashboard +
    budget alert, not a raw report sum.
- **Verdict:** Dashboard + budget alert. API is a nice-to-have for later automation.

### Deepgram (transcription — historically our cost dominant per BENCHMARKS)

- **Dashboard:** yes — Console shows usage and balance.
- **API:** yes, the richest of the four (Management API, needs a management API key):
  - **Balance:** `GET /v1/projects/:project_id/balances` (list) and
    `GET /v1/projects/:project_id/balances/:balance_id` (detail) → **"money/credits left."**
  - **Usage breakdown:** `GET /v1/projects/:project_id/usage/breakdown` — usage by feature/grouping.
  - **Per-request cost:** Get-a-Request returns cost in USD per request ID (we already store
    request metadata in stage1 — could tie cost to a specific job later).
  - **Billing fields:** `GET .../billing/fields` to filter breakdowns.
- **Verdict:** Dashboard + balance alert for MVP. The balance endpoint is the easiest "money left"
  API to wire if we ever want it in our own panel — it's a single authed GET.

### Google / Gemini (LLM — small cost per BENCHMARKS, ~$0.016/run)

- **Dashboard:** yes, two of them:
  - **Google AI Studio → Dashboard → Usage and Limits** (if on a paid AI Studio key): usage +
    remaining credit, **Project Spend Caps** (hard monthly $ limit per project — set this, it's a
    real safety net), and a rate-limit dashboard (RPM/TPM/RPD).
  - **Google Cloud Billing → Daily Cost Breakdown** graph (if the key is under a Cloud project):
    per-project cost over time.
- **API:** **Cloud Billing Budget API** — create/manage budgets programmatically and fire Pub/Sub
  notifications on threshold (overkill for us). Spend itself is pulled via BigQuery billing export,
  not a simple "get balance" call — heavier than Deepgram's.
- **Verdict:** Dashboard + set a **Project Spend Cap** in AI Studio. No API needed; Gemini is our
  cheapest line item.

### Cloudflare R2 (storage)

- **Dashboard:** yes — per-bucket metrics in the Cloudflare dashboard (storage size, Class A/B
  operations). R2 billing also appears under Cloudflare account billing.
- **API:** yes — **GraphQL Analytics API**, datasets `r2StorageAdaptiveGroups` (storage) and
  `r2OperationsAdaptiveGroups` (operations), filtered by `accountTag` (account ID). 31-day
  retention.
  - ⚠️ **Caveat:** Cloudflare explicitly says the GraphQL analytics numbers are **for monitoring,
    not the billing source of truth**. For "what will R2 cost me," use the billing dashboard.
- **Verdict:** Dashboard. R2's free tier (10 GB storage, generous Class B, **zero egress**) means
  storage cost is near-$0 at our scale — lowest monitoring priority. Bookmark and forget until
  volume grows.

### Provider summary

| Provider  | Spend/usage dashboard | "Money left" API                          | MVP action                              |
|-----------|-----------------------|-------------------------------------------|-----------------------------------------|
| Modal     | Yes (budgets+thresholds) | `modal.billing.workspace_billing_report` (Team+) | Bookmark + **workspace budget alert**  |
| Deepgram  | Yes                   | `GET /v1/projects/:id/balances` (easy)    | Bookmark + balance alert                |
| Gemini    | Yes (AI Studio + Cloud) | Cloud Billing Budget API (heavy)          | Bookmark + **Project Spend Cap**        |
| R2        | Yes                   | GraphQL Analytics (monitoring-only)       | Bookmark (lowest priority)              |

**Key insight:** there is **no off-the-shelf product that unifies all four** into one pane without
real plumbing (each has a different auth + data shape, and 2 of 4 warn their API ≠ invoice). A
"single cost pane" is a build, and for a solo founder pre-scale it's **not worth it** — 4 bookmarks
+ 4 budget alerts deliver 95% of the value (the alert is what actually protects the wallet) for ~20
minutes of setup.

---

## Part 2 — User traffic / consumption / per-user cost

This is the data **only we have** — it's already in Supabase Postgres and nobody else can show it:

- `usage_events` — `user_id`, `source_minutes`, `credits`, `month`, `job_id`, `created_at`
- `profiles` — `plan`, `payg_credits`
- `jobs` — `status`, `source_minutes`, `created_at`
- `feedback` (migration 0004)

We can derive **everything the founder asked for** with plain SQL: videos processed, minutes,
credits used, who's spending what, and **cost per user** (join `source_minutes` against the
per-minute costs already documented in `app/billing.py` / `docs/BENCHMARKS.md` — Deepgram $/min +
Modal CPU $/min + ~fixed Gemini per run).

### Options compared (effort vs value)

| Option | What it is | Effort | Cost | Verdict |
|--------|-----------|--------|------|---------|
| **Supabase Studio → Reports** | Built-in dashboard. Save SQL snippets in SQL Editor → drop them as resizable **chart blocks** in Reports. | **~1 afternoon** | **$0** | ✅ **WINNER for MVP** |
| Supabase SQL Editor (raw) | Saved queries, run on demand, export CSV. No charts/layout. | ~1 hr | $0 | Good enough day-0; Reports is the same data with charts |
| **Metabase** (self-host or Cloud) | Real BI: dashboards, filters, scheduled email digests, drill-down. Point at Supabase Postgres (read-only role). | ~Half-day self-host (Docker on Modal/Fly/Render) **+ ongoing maintenance**; Cloud = $ | Self-host ~$5–7/mo VM or free if co-located; Cloud paid | ⏭️ Later, if founder wants emailed weekly digests / richer slicing |
| Grafana | Time-series/observability dashboards. Supabase ships a Prometheus **Metrics API** + ready `supabase-grafana` JSON (~200 DB-health charts). | Half-day | $0 self-host | ❌ Wrong tool — great for **DB health**, awkward for business metrics (per-user revenue/consumption) |
| Tinybird / Evidence.dev / Quotient / Retool | Hosted analytics / SQL-as-code / internal-tool builders. | Med–high (new account, connect, model) | Free tiers exist, then paid | ❌ Overkill — adds a vendor to learn for data Supabase already charts for free |
| Custom Next `/admin` page | Server route reads tables with **service-role** key, renders cards + a chart lib. | **1–2 days** to do well (auth-gate, queries, charts, keep it updated) | $0 (rides Vercel) | ⏭️ Later — only worth it to put consumption **next to live job status** or share one URL |

### Why Supabase Reports wins the MVP

- **Zero new infrastructure / zero new vendor / zero new auth** — it's the dashboard we're already
  logged into, behind Supabase's own auth. Nothing to deploy, patch, or pay for.
- It does **exactly** the 5th ask (per-user/aggregate consumption + cost) with SQL we can write
  in 30 minutes, and renders charts.
- It respects the founder's rule literally: the most off-the-shelf option possible.
- Trade-off: it does **not** show live in-flight job status as nicely as a custom page, and you log
  into Supabase to see it (not embeddable in our own app). Both are fine for a solo founder — and
  both are exactly what the "later" custom `/admin` page would add **if** that gap ever bites.

### Starter SQL (drop these into SQL Editor → save → add to a Report)

```sql
-- 1) This month at a glance
select count(distinct user_id)              as active_users,
       count(*)                             as videos_processed,
       coalesce(sum(source_minutes),0)      as minutes,
       coalesce(sum(credits),0)             as credits_used
from public.usage_events
where month = to_char(now(),'YYYY-MM');

-- 2) Top spenders this month (who's consuming what)
select u.user_id,
       p.plan,
       count(*)                        as videos,
       round(sum(u.source_minutes),1)  as minutes,
       sum(u.credits)                  as credits
from public.usage_events u
join public.profiles p on p.id = u.user_id
where u.month = to_char(now(),'YYYY-MM')
group by u.user_id, p.plan
order by minutes desc
limit 25;

-- 3) Estimated COGS per user this month
--    Plug real $/min from app/billing.py + docs/BENCHMARKS.md
--    (Deepgram $/min + Modal CPU $/min ≈ ~$0.006–0.007/min; Gemini ~ fixed per job).
select user_id,
       round(sum(source_minutes),1)                       as minutes,
       round(sum(source_minutes) * 0.0065, 3)             as est_transcribe_compute_usd,
       count(*) * 0.016                                   as est_llm_usd,
       round(sum(source_minutes) * 0.0065 + count(*)*0.016, 3) as est_total_cogs_usd
from public.usage_events
where month = to_char(now(),'YYYY-MM')
group by user_id
order by est_total_cogs_usd desc;

-- 4) Daily volume trend (chart block)
select date_trunc('day', created_at)::date as day,
       count(*)                            as videos,
       round(sum(source_minutes),1)        as minutes
from public.usage_events
group by 1 order by 1;

-- 5) Job health (failures eat money with no revenue)
select status, count(*)
from public.jobs
where created_at > now() - interval '7 days'
group by status;
```

> Replace the cost constants with the authoritative numbers from `app/billing.py` /
> `docs/BENCHMARKS.md` so COGS-per-user matches reality. Keeping the formula here (and in those
> docs) in sync is the one maintenance item.

---

## Part 3 — Recommended setup (phased)

### MVP (do now — one afternoon, $0)

1. **Bookmark 4 provider dashboards:** Modal billing, Deepgram Console (usage+balance),
   Google AI Studio Usage&Limits (or Cloud Billing), Cloudflare R2 metrics.
2. **Set 4 guardrails** (this is the real money-protection, not the staring-at-graphs part):
   - Modal **workspace budget** + threshold alert.
   - Deepgram low-balance email alert (top-up reminder).
   - Gemini **Project Spend Cap** in AI Studio (hard monthly $).
   - R2 — note the free-tier ceilings; revisit only if storage grows.
3. **Supabase Studio → Reports:** save the 5 SQL snippets above, arrange as one "Quip Ops" report.
   This is the user-traffic/consumption/cost pane.

Result: every number the founder asked for, in at most **5 places he already has logins to**,
with alerts that ping him *before* money runs out. Nothing to host or maintain except keeping the
COGS constants in sync.

### Phase 2 (only when a real gap appears)

- **Custom `/admin` page in Next** — build only if the founder wants (a) consumption next to **live
  job/queue status**, (b) one shareable internal URL, or (c) to stop logging into Supabase. Reads
  `profiles`/`usage_events`/`jobs` with the **service-role key server-side only** (never
  `NEXT_PUBLIC_`), gated behind an allowlisted founder email. ~1–2 days.
- **Pull provider "money-left" into that page** — start with Deepgram's `balances` GET (easiest);
  add Modal's billing report next. Skip Gemini/R2 APIs (dashboards + caps are enough).

### Phase 3 (only at scale / if hiring)

- **Metabase** pointed at Supabase Postgres (read-only role) for scheduled **weekly email digests**
  and self-serve slicing — when "log in and look" stops scaling or someone else needs read access.
- Grafana only if we want DB-health/ops observability (separate concern from business metrics).

---

## Anti-recommendations (what NOT to build)

- ❌ A custom "unified cost cockpit" that scrapes Modal+Deepgram+Gemini+R2 APIs into one pane —
  4 different auths/shapes, 2 of 4 warn API≠invoice, and budget **alerts** already deliver the
  protective value. Pure reinvention.
- ❌ Standing up Metabase/Grafana/Tinybird/Retool **at launch** for a dataset Supabase charts for
  free — a new vendor to learn and maintain for negative marginal value pre-scale.
- ❌ Exposing any of these tables/keys client-side. Consumption data and the service-role key are
  server-only (RLS already enforces per-user read in migration 0001; the admin view must use
  service-role **server-side**).

## Sources

- [Modal Billing docs](https://modal.com/docs/guide/billing) ·
  [`modal billing` CLI](https://modal.com/docs/reference/cli/billing) ·
  [Modal product update (billing API GA)](https://modal.com/blog/product-updates-directory-snapshots-glm-5-billing-updates-and-more)
- [Deepgram — Get Project Balances](https://developers.deepgram.com/reference/manage/billing/list) ·
  [Get a Project Balance](https://developers.deepgram.com/reference/manage/billing/get) ·
  [Usage Breakdown](https://developers.deepgram.com/reference/manage/usage/breakdown/get) ·
  [Logs & Usage](https://developers.deepgram.com/docs/using-logs-usage)
- [Gemini API Billing](https://ai.google.dev/gemini-api/docs/billing) ·
  [More control over Gemini API costs (spend caps)](https://blog.google/innovation-and-ai/technology/developers-tools/more-control-over-gemini-api-costs/) ·
  [Cloud Billing Budget API](https://docs.cloud.google.com/billing/docs/how-to/budget-api-overview)
- [Cloudflare R2 Metrics & Analytics](https://developers.cloudflare.com/r2/platform/metrics-analytics/) ·
  [GraphQL Analytics API](https://developers.cloudflare.com/analytics/graphql-api/) ·
  [Cloudflare usage-based billing](https://developers.cloudflare.com/billing/usage-based-billing/)
- [Supabase Studio Reports/SQL updates](https://supabase.com/blog/tabs-dashboard-updates) ·
  [Supabase SQL Editor feature](https://supabase.com/features/sql-editor) ·
  [supabase-grafana (DB observability)](https://github.com/supabase/supabase-grafana) ·
  [Supabase Metrics API](https://supabase.com/docs/guides/telemetry/metrics)
