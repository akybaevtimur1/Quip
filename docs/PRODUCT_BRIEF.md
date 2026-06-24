# Quip — Product Brief (for distribution / go-to-market)

> **Purpose of this file:** a self-contained product overview you can hand to any AI assistant
> (e.g. Claude in the browser) with **no access to the codebase**, so it understands what Quip is,
> who it's for, what it does today, how it's priced, and where it stands — and can help you think
> through **distribution / marketing / growth**. Last updated: 2026-06-21.

---

## 1. One-liner
**Quip turns one long video or podcast into a batch of ready-to-post vertical short clips (9:16) — and, unlike most AI clippers, it tells you *why* each clip will work.**

**Elevator pitch:** You upload a long video (podcast, interview, talk, stream). Quip transcribes it, uses an LLM to find the most postable moments, and produces multiple vertical shorts — each with burned-in animated captions, a hook headline, automatic face/speaker-tracked reframing, and a **confidence score + a plain-English reason** ("why this clip works"). It also builds a **map of the whole video** (narrative, chapters, color-coded "moments") so you understand the source, not just the clips. Then a fast in-browser editor (with an AI chat assistant) lets you tweak everything and export. Live product, real billing.

---

## 2. The problem & who it's for
**Problem:** Creators sit on hours of long-form content (podcasts, webinars, streams, interviews) that's a goldmine for short-form, but cutting it into good vertical clips by hand is slow and skilled work. Existing AI clippers spit out clips but are black boxes ("here are 10 clips, good luck") and the editing is shallow.

**Ideal customers (ICP):**
- **Podcasters & their editors** — the core use case (long episodes → Reels/TikToks/Shorts).
- **Solo creators / coaches / educators** repurposing talks, webinars, livestreams.
- **Agencies & social media managers** clipping for multiple clients (batch + explainability + presets matter most here).
- **B2B / founders** turning interviews & webinars into social proof.

**Platforms it targets:** TikTok, Instagram Reels, YouTube Shorts (it knows their safe-zones).

---

## 3. What it does today (shipped & live)
- **AI clip selection** — finds the best moments from the transcript (not random); up to **30 clips per video**, each ~**20–60s** (sweet spot 20–45s).
- **Explainability (a real differentiator)** — every clip ships with a **confidence score** and a **human-readable "why it works"** reason. Plus a **Video Map**: a connected narrative, chapters, and color-coded moments (tension / quote / emotional / insight / funny) over the whole source.
- **Auto vertical reframing** — scene/shot detection + **face & active-speaker tracking** to keep the talker in frame; modes: tight crop (fill), wide with blurred bars (fit), or **split-screen for 2 speakers** (OpusClip-style).
- **Animated captions** — burned-in, word-by-word highlight/karaoke styles; **21 built-in caption presets** + custom (font, color, size, position, animations, keyword highlighting).
- **Hooks** — an auto-generated top "headline" overlay per clip, restyleable, regenerate-able.
- **A professional in-browser editor** (recently overhauled): a fixed 3-zone "studio" layout, **instant clip switching**, live preview that's **pixel-identical to the export (WYSIWYG)**, and — new — **smart alignment guides + snapping** (drag captions/hook → they snap to center, edges, each other, and **TikTok/Reels/Shorts safe-zones**, with platform safe-area overlays).
- **AI chat agent inside each clip** — tell it in plain language to adjust the clip's in/out points or rewrite the hook; it edits for you (runs in the background, costs nothing extra).
- **Co-watch during processing** — while the pipeline runs, the uploaded video plays immediately and discovered "moments" surface as quote chips, so the wait feels productive.
- **Export** — captioned video, clean (no captions), or SRT. Permanent CDN links.
- **Accounts & billing** — Google / email auth; credit-based plans via Polar (Merchant-of-Record, handles tax).

**Free-tier limits:** watermark on clips + 720p cap; paid tiers remove both and render sharper (1080p).

---

## 4. Why Quip vs. the pack (positioning)
The AI-clipper space is crowded (Opus Clip, Submagic, Vizard, Veed, Captions, Klap, etc.). Quip's edges:
1. **Explainability** — "why this clip works" + confidence score + a full **video map**. Most tools are black boxes. This is the headline differentiator and a trust/teaching angle.
2. **A genuinely good editor** — WYSIWYG preview, instant clip switching, Figma-style snapping with platform safe-zones, and an **in-clip AI chat assistant** — closer to a real editing tool than a one-shot generator.
3. **Reframing quality** — real active-speaker tracking + split-screen, not just a static center crop.
4. **Honest, transparent product** — no silent failures; you cancel before any paid work at $0; clips are explained, not dumped.

**Where it's still behind / honest gaps (useful for positioning & roadmap):**
- No reusable **brand kits / cross-project preset persistence** yet (planned) — styles are per-clip today.
- AI agent edits intervals & hooks, **not yet captions/framing** by chat.
- Hooks are descriptive, not yet strongly emotional/templated (POV/meme/shock styles).
- No team/multi-seat, no scheduling/auto-posting, no analytics — it's a clip *producer*, not a full publishing suite (yet).
- YouTube-link ingestion exists but is currently hidden; upload is the primary input.

---

## 5. Pricing & plans (current — source of truth: `app/billing.py` ⇄ `lib/plans.ts`)
Credit model: **1 credit = 60 minutes of source video.**

| Plan | Price | Credits / mo | Notes |
|---|---|---|---|
| **Free** | $0 | **2** (≈120 min) | watermark, 720p cap |
| **Starter** | **$15/mo** | **10** (≈600 min) | no watermark, 1080p |
| **Pro** | **$35/mo** | **30** (≈1800 min) | 1080p, queue priority |
| **PAYG** | **$3** | 1 credit (one-off) | credits don't expire |

- **Max source length:** 3 hours per video (all plans). Up to 30 clips per video.
- **Billing is honest:** minutes are only charged when clips actually finish; cancelling during the free phase costs $0; PAYG credits are non-expiring and idempotent.

---

## 6. Unit economics (useful for ad math / margins)
- **Cost to produce one video:** ≈ **$0.33–0.40** (transcription ~$0.26 + LLM ~$0.03 + compute).
- **Gross margins:** Starter ~**60–67%**, Pro ~**52–60%**, PAYG ~**84%**.
- **Storage:** clips are kept forever on Cloudflare R2 (egress is free → serving clips costs ~nothing); raw source files auto-delete after 60 days to cap storage growth.
- Implication for GTM: per-clip delivery cost is near-zero, so generous free/trial usage is affordable; the constraint is transcription+compute per *new* video, not per view.

---

## 7. Current state
- **Live in production** at **quip.ink**. Real users, real payments (Polar).
- Frontend on Vercel (Next.js), worker on Modal (Python pipeline), Postgres on Supabase, storage on Cloudflare R2, transcription by Deepgram (nova-3), LLM by Google Gemini (Flash).
- Recently shipped: a full **editor overhaul** (new layout, instant clip switching, fixed a framing bug, grouped panels, preset grids) and **alignment guides + snapping + platform safe-zones**.
- **Not yet built (roadmap):** background-agent UX across navigation, reusable brand kits / preset persistence, a final design/perf polish pass; longer-term: scheduling/auto-post, analytics, teams, multi-language UI.

---

## 8. Distribution questions to think through (what to ask the browser-Claude)
This is the open space — bring these to your distribution session:
- **Channels:** where do podcasters/agencies actually discover clipping tools? (communities, YouTube tutorials, Twitter/X, podcast-host integrations, AppSumo-style deals, affiliate/creator programs, SEO on "podcast to shorts" / "opus clip alternative").
- **Wedge:** lead with the **"explainability / why this clip works"** differentiator, or with editor quality, or with price? Which ICP first (solo podcasters vs agencies)?
- **Free → paid:** is 2 free videos/mo the right hook given near-zero delivery cost? Trial vs freemium?
- **Positioning vs Opus Clip / Submagic:** "the clipper that explains itself" vs "the better editor" vs "cheaper" — pick the spine.
- **Content/SEO:** "X alternative" pages, comparison content, template galleries, creator case studies.
- **Partnerships:** podcast hosts (Riverside, Descript-adjacent), agencies, creator coaches.

> For deeper technical/economics detail (pipeline internals, exact infra costs, code), see `docs/CORE_ARCHITECTURE_AND_FEATURES.md` (the living engineering deep-dive). This brief is the product/GTM-facing summary; current reality baseline = `docs/README.md`.
