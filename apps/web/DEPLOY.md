# Deploying the Quip web app (apps/web)

The whole site (landing + auth + dashboard + editor + pricing) is **one Next.js app**
in `apps/web`. Everything that changes per-environment is **env-driven — no code edits to
move domains.** This is the checklist to put it on a real domain.

## 1. Vercel project
- ⚠️ The existing Vercel `quip` project builds the **old landing repo** (Shorts-Automatizator),
  **not this app**. Create a **new Vercel project** from the `Varenik-vkusny/Quip` repo.
- **Root Directory = `apps/web`** (it's a pnpm monorepo). Vercel auto-detects Next + pnpm.
- Add your custom domain in Vercel → Domains.

## 2. Environment variables (Vercel → Settings → Environment Variables)

| Var | What | If missing |
|-----|------|-----------|
| `NEXT_PUBLIC_SITE_URL` | Canonical site URL, e.g. `https://quip.ink` | defaults to `https://quip.ink` (metadata/sitemap/robots/OG/canonical use it) |
| `NEXT_PUBLIC_WORKER_URL` | Modal worker base URL (jobs/clips/usage API) | falls back to the built-in mock (`/api/mock`) — the real tool won't work |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | auth runs in **dual-mode** (open, no real accounts) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` (or `_PUBLISHABLE_KEY`) | Supabase anon/publishable key | same as above |
| `POLAR_ACCESS_TOKEN` (server) | Polar API token → real checkout | `/checkout` dual-modes to `/signup` (no dead buttons) |
| `POLAR_SERVER` | `production` or `sandbox` | defaults to `production` |
| `NEXT_PUBLIC_POLAR_PRODUCT_STARTER/PRO/PAYG` | override Polar product IDs | sensible defaults baked into `lib/polar.ts` |
| `NEXT_PUBLIC_TWITTER_HANDLE` | optional, for social cards | omitted |

> Public (`NEXT_PUBLIC_*`) vars ship to the browser — never put secrets there. The Polar
> token and the worker's billing/webhook secrets stay server-side (worker env on Modal).

## 3. External wiring (gotchas)
- **Supabase Auth → URL config:** add the production domain + `https://<domain>/auth/callback`
  to Supabase → Authentication → URL Configuration (otherwise login redirects break).
- **Worker (Modal):** deploy separately (`modal deploy deploy/modal/worker.py`); point
  `NEXT_PUBLIC_WORKER_URL` at the web URL it prints. Worker needs its own secrets (Deepgram,
  Gemini, R2, Supabase service_role, Polar webhook, `BILLING_ENABLED`).
- **CORS:** the worker must allow the production web origin (it currently allows localhost:3000).
- **Polar webhook:** point it at the worker's `POST /webhooks/polar` so plan/credit purchases
  attach to accounts.

## 4. Sanity check after deploy
- `https://<domain>/` landing loads; `/pricing`, `/login`, `/signup`, `/dashboard` resolve.
- `/sitemap.xml` and `/robots.txt` show the real domain (confirms `NEXT_PUBLIC_SITE_URL`).
- A real upload/YouTube job runs end-to-end against the worker.
- A Polar checkout opens in one click (see the `<a>`-not-`<Link>` checkout fix).
