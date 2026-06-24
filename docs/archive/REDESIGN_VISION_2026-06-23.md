# Quip — UI/UX Redesign Vision (2026-06-23)

> Single source of truth for the night's redesign. Every implementation fork reads this first.
> Goal: make Quip **memorable, intentional, NOT AI-templated** — execute the *Warm Precision*
> identity that `DESIGN.md` declares but the code under-delivers. **Design only — no behavior,
> no functionality, no deploy.** **Palette/tokens are LOCKED** (no color changes this iteration).

---

## 1. North star — the thesis

Quip is not a clip mill. It is a **precision instrument** that hands you *evidence*: a hook, a
reason it will land, a **confidence score**, and a clip-type. The wedge is "fewer clips, but you
know WHY." So the interface must **look and feel like a measured, honest instrument** — a thing
that reports readings you trust — while staying warm and premium (Linear/Vercel restraint), never
cold sci-fi, never generic SaaS.

The current build looks like generic dark SaaS: centered headings, equal rounded "menu" cards,
a plain dashed dropzone, text-heavy panels. We keep the excellent tokens and rebuild the
**composition, typography rhythm, structure, states, and motion** into one instrument language.

**One-line test for every screen:** *Does this read like a precise instrument reporting a
measurement, or like a template?* If template → revise.

---

## 2. Hard constraints (do not violate)

- **Palette LOCKED.** Use only existing tokens (`bg/surface/surface-2/surface-3`, `ink/muted/faint`,
  `line/line-strong`, `accent/accent-2/accent-tint/accent-line`, clip-type `hook/peak/thought/quote`,
  `ok/warn/bad`). **No new colors, no gradients-as-accent, no hue shifts.**
- **Behavior frozen.** No logic, data flow, props contracts, or copy *meaning* changes. You may
  improve microcopy wording (English only, per CLAUDE.md) but not what an action does.
- **Types via codegen only.** Never hand-edit `packages/shared/*`.
- **Gate green.** `just check` must pass before every commit. No silent fallbacks.
- **No deploy / no push.** Local commits only.
- **English-only** user-facing text. Russian only in comments/docs.
- **`prefers-reduced-motion`** respected for every animation you add.

---

## 3. The signature system — "instrument language" (the cohesion glue)

These repeated devices make the whole app feel like ONE designed product. Deploy them everywhere.

### 3.1 Mono readouts are first-class
Every number that is a *measurement* — score, timecode, duration, count, %, price, minutes —
renders in **IBM Plex Mono, `tabular-nums`**. Pair a value with a **mono uppercase micro-label**
(the eyebrow). This is the core signature: data presented as instrument readings.
- Big readouts: large Onest-or-mono number + tiny mono label beneath/beside.
- Inline readouts: `font-mono tabular-nums` always.

### 3.2 Hairline panels with labeled headers (not floating cards)
Replace "stack of equal rounded-xl cards" with **panels organized by hairlines**. A panel has:
- a **header row**: mono uppercase eyebrow label on the left, optional value/action on the right,
  separated from the body by a hairline (`border-line`);
- quiet body on `surface`, hairline border, radius `lg` (14px) — **one radius discipline**, no
  more ad-hoc `rounded-xl`.
Think instrument fascia / ledger, not Material cards. Elevation = surface ladder + hairlines,
never drop shadows (one soft shadow allowed only on a hero media element).

### 3.3 The confidence score as a recurring motif
The score is the product's soul. Give it ONE iconic, consistent treatment used on clip cards,
in the editor, in the video map: **mono number + a thin precise meter/track** (hairline rail with
a coral/▢ fill keyed to value). Same component everywhere → instant recognizability.

### 3.4 Coral = the single live signal
Coral appears **once or twice per view max**: the primary action, the *live*/active state, the
current selection, or the peak reading. Never as decoration, never as a gradient, never as
load-bearing body button text (primary buttons stay near-white `bg-ink`; coral is the scarce
"accent" CTA for in-product run/apply/retry and for "signal").

### 3.5 Structural marks encode truth
Eyebrows, hairline dividers, and labels must **mean something** (a real section, a real reading).
No decorative `01 / 02 / 03` unless the content is genuinely a sequence (the pipeline IS one →
allowed there). No icon-in-circle 3-col feature grids.

### 3.6 Motion: intentional, instrument-like
`--ease-snappy` everywhere. Micro 120 / short 180 / medium 240 / slow 400. Buttons lift -1px on
hover. Reveal-on-scroll for marketing. For *processing/live* states, a restrained "scanning"/
sweep or pulse that reads like an instrument working — never confetti, never bouncing.

---

## 4. Foundation pass (do FIRST; shared, palette-preserving)

Build/standardize these in `apps/web/components/ui/` + small `globals.css` additions so all pages
inherit them. **No color tokens change.** The dashboard redesign is the worked reference that
proves these primitives; other domains follow it.

- **`Eyebrow`** — mono uppercase tracked micro-label (`text-eyebrow font-mono uppercase text-muted`).
  Replaces the dozens of inline eyebrow spans.
- **`Panel`** — surface + hairline + radius-lg, with optional `label`/`action` header row split by a
  hairline. Replaces ad-hoc `rounded-xl border border-line bg-surface p-5` blocks. (Keep `Card`
  for simple cases; `Panel` adds the labeled-header instrument fascia.)
- **`Stat` / readout** — value (Onest or mono) + mono label, tabular. For balances/metrics.
- **`Meter`** — the thin track + fill bar (height ~2px hairline rail option), value-keyed color
  (accent default, warn near-limit, bad over). Used by UsageMeter, JobProgress, score motif.
- **`Badge` / `Chip`** — clip-type chips (`hook/peak/thought/quote`) and status chips as real
  primitives (currently inline). One shape discipline.
- **`globals.css`** — add only: a couple of keyframes (subtle `sweep`/`pulse` for live states; a
  `riseIn` already exists), and maybe a `.tnum` helper. No color, no token renames (back-compat
  utility names must stay).

Keep diffs surgical; preserve every existing prop and class consumers rely on (or update consumers
in the same domain). Run `just check` before handing off.

---

## 5. Per-domain direction

### 5.1 Dashboard — the flagship (idle + processing + results)
The 2-col skeleton (intake left, readout rail right) is fine; **the execution is the slop**. Rebuild:
- **Idle / intake:** make the upload the clear protagonist — an **"intake" panel** with intentional
  framing (hairline interior, mono spec line for formats/limits, a real focal target), not a limp
  dashed box. Strong H1 + lead with real hierarchy. The "Clips: Auto/Custom" control reads as an
  instrument setting.
- **Readout rail (right):** convert the 3 equal cards into a tighter **instrument stack**: balance
  as a **readout panel** (big mono number + thin monthly meter + distinct PAYG line), recent
  projects as a **ledger/log** (mono timecodes, status as live signal), promo as a *slim* inline
  action (de-emphasized — it's secondary). Unequal weight = real hierarchy.
- **Processing (JobProgress / CoWatch):** the pipeline is a real sequence → an honest **stepper /
  readout** with live counters (source min / words / moments) as mono readouts and a scanning motion.
  Co-watch quote chips rising = keep, refine.
- **Results (VideoMap + ClipGrid):** VideoMap = an **instrument briefing** (narrative + chapters +
  colored moment ticks) with stronger structure, less wall-of-text. ClipGrid = a disciplined 9:16
  gallery; each **ClipCard** leads with the score motif + clip-type chip + hook, hover lift, crisp
  states (pending/rendering/ready). Make the card feel like a *spec sheet for a clip*, not a generic
  media card.

### 5.2 Editor — the studio
Keep the Fixed-Studio shell (rail / canvas / inspector / timeline). Elevate to instrument-grade:
- **Header**: clip position + duration as mono readouts; Render/Download as clear primary/secondary;
  the "click Render to save" nudge less shouty, more status-line.
- **Rail**: refined active state (coral signal), consistent icon+label rhythm.
- **Inspector tabs** (Subtitles/Hook/Frame/Agent): consistent panel headers (eyebrow), tighter
  control rhythm, line list reads like an editable transcript ledger with mono timecodes.
- **Timeline**: the showpiece — moment legend + region selection + playhead as a precise instrument
  track; mono time ruler; coral = current selection/live. Make it feel measured, not busy.
- **Score motif** present where a clip's strength is shown.

### 5.3 Account & billing
Currently sparse/lonely centered column. Make it **intentionally calm**, not empty: a left-aligned
page header, a clear **plan readout** (current plan, what you get, balance as readouts), subscription
management, redeem. Use the same Panel/Eyebrow/Stat language. Fill the space with structure, not filler.

### 5.4 Landing / marketing
Hero is already editorial/asymmetric (good). Tighten across sections:
- Consistent section rhythm (eyebrow + heading + lead), the instrument language in the live
  "Quip Studio" mock and reasoning cards, the **score motif** echoed from the app so the promise is
  visible. Strong reveal-on-scroll choreography. Pricing cards = clear, honest, one scarce accent on
  the recommended plan. No "Built for X" filler, no icon-circle grids.

---

## 6. Anti-slop checklist (reject if any are true)
- Centered-everything / symmetric equal cards where hierarchy should exist.
- Plain dashed dropzone, generic "feature card" rows, icon-in-circle 3-col grids.
- Uniform bubble radius everywhere; ad-hoc radii (`rounded-xl` where `lg` is the system).
- Numbers in proportional/non-tabular font; data not treated as a readout.
- Coral used more than ~twice per view, or as gradient/decoration.
- Drop shadows used for structure instead of the surface ladder + hairlines.
- Motion that's decorative/bouncy rather than instrument-like; reduced-motion ignored.
- Wall-of-text panels with no labeled structure.

## 7. Verification protocol (every change)
1. `just check` green (PowerShell + PATH refresh).
2. Playwright screenshot at desktop (1440) AND mobile (390) for the touched surface; read it.
3. Check states: hover / active / focus / loading / empty / error.
4. Compare against the `before-*.jpeg` baselines. If it doesn't clearly read better → iterate.
5. Commit locally (conventional commit) with a tight message. Frequent commits for rollback.

## 8. Build order
1. Foundation primitives + globals additions → commit.
2. Dashboard (flagship, sets the standard) → commit.
3. Parallel: Editor / Account / Landing (worktree forks, follow the dashboard pattern; ui + globals
   are READ-ONLY for them) → integrate one at a time, verify visually, commit each.
4. Cross-page consistency + polish + responsive + a11y pass → commit.
