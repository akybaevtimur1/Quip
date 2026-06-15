# Quip

Turn one long video or podcast episode into several **explainable** vertical clips — each with
burned-in captions, a hook, a confidence score, and a plain reason it works.

Monorepo:
- `apps/web` — Next.js 16 frontend (Vercel `quip-app`, auto-deploys on `main`).
- `services/worker` — Python / FastAPI pipeline (Modal `quip-worker`).
- `packages/shared` — TypeScript types, **codegen** from `services/worker/app/models.py` (`just types`).

## 📚 Documentation — start here

**→ [`docs/README.md`](docs/README.md)** is the single index: the current production reality,
the reading order for a new session, what you must not break, and the deploy/infra map. Read it
first; everything else is linked from there.

## Run locally (Windows / PowerShell)

See `docs/HANDOFF.md` §3 — worker via `uv run uvicorn app.main:app`, web via
`pnpm --filter web dev`, pre-commit gate via `just check`. (Deploy/billing notes in HANDOFF are
outdated — trust `docs/README.md`.)
