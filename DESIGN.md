# Design System — Quip

> Single source of truth for the **production shell** (marketing site, auth, dashboard, account).
> Tokens live in `apps/web/app/globals.css` (`@theme`). Change values there → whole UI re-skins.
> Read this before any visual/UI decision. In QA/review, flag anything that deviates.

## Product Context
- **What it is:** Quip turns a long video (podcast / interview / stream) into 3–10 vertical
  clips with burned-in subtitles, a hook on top, and an explanation of **why** each one will land.
- **Who:** solo creators, podcasters, coaches, experts, marketers repurposing long content.
- **Wedge (the whole narrative):** not "more clips" (Vizard) — **"fewer clips, but you know WHY
  to post them."** Explainability = hook + why_works + confidence score + clip-type. Plus reframe
  with no flashes and honest pricing (no credit-casino).
- **Memorable thing:** *a precise, honest instrument you trust.* The cold precision IS the
  argument — a tool that hands you confidence scores should look measured and credible.
- **Message:** "Don't just get clips. Know why they're worth posting."

## Direction — Precision Dark (matched to quip.ink)
- **Decision:** match the founder's live brand at **quip.ink** for one coherent identity.
- **Extracted from quip.ink (computed, not guessed):** deep **cool** near-black base, headline
  **Onest 700** at `-2.28px` tracking, body `#7E8AA4` cool blue-grey, **coral** only on the clip
  hook plate + progress, white "Get a spot" pill. The "warmth" is just faint atmospheric corner
  blooms over a cool base.
- **Mood:** measured, premium, trustworthy. Linear/Vercel restraint + the warm coral as the one
  human spark. Hairlines over shadows. Product shown as a real 9:16 clip.
- **Reference:** quip.ink (north-star); design-md/ (linear, vercel, superhuman, cursor, raycast,
  runwayml, elevenlabs).

## Color
Approach: **restrained** — one accent (coral), everything else is a cool neutral ladder.

| Token (`--color-*`) | Hex / value | Use |
|---|---|---|
| `bg` | `#0A0B0F` | page canvas (cool near-black) |
| `surface` | `#111319` | cards, panels |
| `surface-2` | `#171A21` | raised / nested surfaces |
| `surface-3` | `#1E222B` | hover / active fill |
| `ink` | `#EDF0F8` | primary text (quip headline) |
| `muted` | `#7E8AA4` | secondary text (quip body) |
| `faint` | `#565E70` | tertiary / disabled / fine print |
| `line` | `rgba(237,240,248,.08)` | default hairline border |
| `line-strong` | `rgba(237,240,248,.14)` | focus / emphasis border |
| `accent` | `#FF5A3D` | **coral** — CTA, confidence, hook, focus (scarce) |
| `accent-2` | `#E0431F` | coral pressed/hover |
| `accent-tint` | `rgba(255,90,61,.12)` | coral wash (chip bg, glow) |
| `accent-line` | `rgba(255,90,61,.30)` | coral hairline |
| `hook` | `#FF5A3D` | clip-type chip: hook |
| `peak` | `#C06BFF` | clip-type chip: emotional_peak |
| `thought` | `#19BD8B` | clip-type chip: complete_thought |
| `quote` | `#4D8DFF` | clip-type chip: strong_quote |
| `ok` / `warn` / `bad` | `#19BD8B` / `#F5B32E` / `#FF6B6B` | confidence / status semantics |

**Rules:** coral appears once or twice per view max (primary action, confidence, hook). Text
contrast ≥ WCAG AA. No second brand color, no gradients-as-accent, no pure `#000`/`#FFF` surfaces.

## Typography
- **Display:** Onest 700–800, tight negative tracking. (Matches quip.ink; already wired.)
- **Body / UI:** Onest 400–600.
- **Mono / numerals:** IBM Plex Mono — timecodes, scores, prices. Always `tabular-nums`.

| Role | Size / line-height / tracking / weight |
|---|---|
| display-2xl (hero) | 72 / 1.02 / -0.03em / 800 |
| display-xl | 56 / 1.04 / -0.028em / 800 |
| display-lg | 40 / 1.06 / -0.024em / 700 |
| h2 | 30 / 1.12 / -0.02em / 700 |
| h3 | 22 / 1.25 / -0.015em / 600 |
| lead | 19 / 1.55 / -0.01em / 400 (muted) |
| body | 16 / 1.6 / -0.005em / 400 |
| small | 14 / 1.5 / 0 / 400 |
| eyebrow/label | 12.5 / 1 / 0.04em / 500 mono, uppercase |

Clamp display sizes responsively (`clamp()`); never let a headline wrap to 5+ short lines.

## Spacing
- **Base:** 4px. Scale: 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 · 96 · 128.
- **Density:** comfortable. Section vertical rhythm 96–128px desktop / 64px mobile.
- **Max content width:** 1200px (`--container`); prose 680px.

## Layout
- **Approach:** hybrid — disciplined grid for app, editorial asymmetry for marketing (hero is a
  poster, not a centered document; left-aligned headline + product on the right).
- **Border radius:** sm 8 (buttons/inputs/chips) · md 10 · lg 14 (cards) · xl 20 (hero media) ·
  pill 999 (only tiny status chips/eyebrows). `--radius-card` = 14 (back-compat).

## Motion
- **Approach:** intentional, guiding — reveal-on-scroll, focus on CTA. Never decorative chaos.
- **Easing:** `cubic-bezier(.2,.7,.2,1)`. Durations: micro 120 · short 180 · medium 240 · slow 400ms.
- **Tactility:** buttons lift `translateY(-1px)` on hover, settle on `:active`; 150–220ms.
- Respect `prefers-reduced-motion` (already in globals).

## Elevation
- **No drop shadows for structure** — use the surface ladder + hairlines. One soft shadow is
  allowed on the hero product media only.
- **Focus ring:** `0 0 0 2px var(--color-bg), 0 0 0 4px var(--color-accent-line)`.

## Component primitives (`components/ui/`)
Reusable, token-only, a11y-first. No god-components, no hardcoded hex.
`Button` (primary/secondary/ghost, sizes, loading, press feedback) · `Input` · `Card` · `Badge`
(clip-type) · `Chip` · `Container` · `Section` · `Stat` (tabular) · `Logo` · `Eyebrow`.

## Anti-slop (taste pre-flight)
Never: purple/violet "AI gradient", 3-column icon-in-circle grids, centered-everything, uniform
bubble radius, gradient CTAs, system-ui as display/body, stock-photo heroes, "Built for X" filler.
Do: asymmetry, hierarchy, second-read moments, the product shown real, one scarce accent.

## SEO / a11y (build requirements)
`generateMetadata` per page (title/description/canonical), OG + Twitter cards + OG image,
`app/sitemap.ts`, `app/robots.ts`, JSON-LD (SoftwareApplication/Organization/FAQPage), semantic
`<main>/<nav>/<section>`, h1→h2→h3, alt text, `next/font` (CLS≈0), `next/image`. Target Lighthouse
perf/a11y/SEO/best-practices ≥ 90. Contrast AA, visible focus, full keyboard nav.

## Decisions Log
| Date | Decision | Rationale |
|---|---|---|
| 2026-06-13 | System created by /design-consultation | Production shell for Quip |
| 2026-06-13 | Direction = Precision Dark matched to quip.ink | Founder: brand consistency with live site |
| 2026-06-13 | Cool near-black, not warm | quip.ink computed tokens are cool (#EDF0F8/#7E8AA4); warmth was atmospheric only |
| 2026-06-13 | Display = Onest (drop Unbounded) | quip.ink uses Onest 700; already wired |
| 2026-06-13 | Coral kept as sole accent | In quip mark + both ref clusters + burned into every exported clip |
