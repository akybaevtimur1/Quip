# Spec: Clip Card Redesign + Explanation Quality

**Date:** 2026-06-28  
**Branch:** `feat/clip-card-redesign`  
**Status:** Approved — ready for implementation

---

## Goal

Replace the "Confidence 87/100 + one sentence" clip card with a design that **explains why a moment was chosen** so the user feels agreement and enjoyment rather than anxiety about a score prediction.

---

## Current State (read before touching anything)

### Frontend — `apps/web/components/ClipCard.tsx`

The card currently renders:
- `<Stat label="Confidence" value={score100} suffix="/100" meter={displayScore} meterTone="ok|neutral">` — green meter, ink-coloured or coral number on top clip
- Count-up animation (`requestAnimationFrame` over 600ms, easeOutCubic) for the score
- `<ReasonChip type={clip.type}/>` — chip at `top-left` of thumbnail showing clip type
- Select checkbox at `top-right` of thumbnail
- `clip.hook` as bold heading
- `"Why it works"` eyebrow + `clip.why_works ?? clip.reason` below a hairline
- Optional `clip.transcript` snippet (faint italic, last line)

Uses **Tailwind only** (no CSS files). Component library: `Card`, `Stat`, `Eyebrow`, `Numeral` from `@/components/ui/`.

### Backend — `Segment` model (`services/worker/app/models.py:75`)

Current fields: `start`, `end`, `reason`, `score`, `type`, `hook`, `why_works`, `hook_style`  
**Missing:** `tone`, `key_quote`

### Backend — `ClipOut` wire model (`services/worker/app/models.py:119`)

Current fields: `id`, `start`, `end`, `duration`, `reason`, `type`, `score`, `video_url`, `thumbnail_url`, `transcript`, `words`, `hook`, `why_works`, `hook_style`  
**Missing:** `tone`, `key_quote`

### Backend — `postprocess()` (`services/worker/app/pipeline/stage2_select.py:213`)

Reads `hook`, `why_works`, `hook_style` from the raw LLM dict — **`tone` is read by the LLM but silently dropped** (not passed to `Segment()`). The `Segment()` constructor call is at line ~265.

### Backend — `_LlmSegment` (`services/worker/app/pipeline/stage2_select.py:356`)

Has: `start_word_index`, `end_word_index`, `reason`, `score`, `type`, `tone`, `hook_style`, `hook`, `why_works`  
**Missing:** `key_quote`

Note: `_LlmSegment` is used for structured-output validation — add `key_quote: str | None = None` there.

### Backend — LLM prompt (`services/worker/app/prompts/select_moments.v2.txt`)

Already generates `tone` as STEP 1, `hook_style` as STEP 2, `hook` as STEP 3, `why_works` as STEP 4.  
**Missing:** `key_quote` — needs to be added as STEP 5.

### Backend — Routes (`services/worker/app/main.py`)

All routes are in `main.py`. Pattern: `@app.post("/jobs/{job_id}/...")`. There is no separate clips router.  
Relevant endpoints: `POST /jobs`, `GET /jobs/{job_id}`, etc.  
The new refresh endpoint should follow this pattern: `POST /jobs/{job_id}/clips/{clip_id}/refresh-analysis`.

### Backend — Segment → ClipOut mapping

Find where `Segment` fields are mapped to `ClipOut` (search for `ClipOut(` in `run.py` / `cloud_state.py` / `db.py`). When adding `tone` and `key_quote` to both models, also update this mapping site.

---

## Visual Design (locked)

### Score block — Variant C (same structure as current, amber colour)

```tsx
// Replace the <Stat> component entirely:
<div className="mb-2.5">
  <div className="flex items-baseline gap-0.5 mb-1.5">
    <span className="text-[28px] font-extrabold leading-none text-amber-400 tabular-nums">
      {score100}
    </span>
    <span className="text-xs text-muted">/100</span>
  </div>
  <div className="h-1 bg-surface-2 rounded-full overflow-hidden">
    <div
      className="h-full rounded-full"
      style={{
        width: `${displayScore * 100}%`,
        background: 'linear-gradient(90deg, rgba(251,146,60,0.55) 0%, #fb923c 55%, #fde68a 100%)',
        boxShadow: '0 0 7px rgba(251,146,60,0.5)',
      }}
    />
  </div>
</div>
```

**Keep the count-up animation** (the `requestAnimationFrame` easeOutCubic logic for `displayScore`) — it's good UX, just change the colour.

**Stale state:** score number `text-surface-3`, bar fill `bg-surface-3 shadow-none`.

### Glow card by tone

Add inline `style` to the root `<Card>` based on `clip.tone`:

```ts
const TONE_GLOW: Record<string, { border: string; shadow: string }> = {
  shocking:     { border: '#2a1515', shadow: '0 0 0 1px rgba(255,70,70,0.14), 0 0 18px rgba(255,70,70,0.09), inset 0 0 28px rgba(255,60,60,0.04)' },
  funny:        { border: '#2a2510', shadow: '0 0 0 1px rgba(250,204,21,0.14), 0 0 18px rgba(250,204,21,0.09), inset 0 0 28px rgba(250,200,20,0.04)' },
  touching:     { border: '#1e1228', shadow: '0 0 0 1px rgba(192,132,252,0.14), 0 0 18px rgba(192,132,252,0.09), inset 0 0 28px rgba(192,132,252,0.04)' },
  relatable:    { border: '#131d13', shadow: '0 0 0 1px rgba(74,222,128,0.14), 0 0 18px rgba(74,222,128,0.09), inset 0 0 28px rgba(74,222,128,0.04)' },
  inspiring:    { border: '#1a1710', shadow: '0 0 0 1px rgba(251,146,60,0.14), 0 0 18px rgba(251,146,60,0.09), inset 0 0 28px rgba(251,146,60,0.04)' },
  controversial:{ border: '#160e20', shadow: '0 0 0 1px rgba(167,139,250,0.14), 0 0 18px rgba(167,139,250,0.09), inset 0 0 28px rgba(167,139,250,0.04)' },
  insightful:   { border: '#101820', shadow: '0 0 0 1px rgba(56,189,248,0.14), 0 0 18px rgba(56,189,248,0.09), inset 0 0 28px rgba(56,189,248,0.04)' },
};
const glow = (!analysisStale && clip.tone && TONE_GLOW[clip.tone]) || null;
// apply as: style={{ borderColor: glow?.border, boxShadow: glow?.shadow }}
```

If `clip.tone` is null or stale → neutral card (no glow, existing default border).

### Tone emoji badge — replaces `ReasonChip`

`ReasonChip` currently sits at `top-left` of thumbnail. **Replace it with the emoji badge** (same position: `absolute left-2 top-2 z-40`). The select checkbox stays at `top-right` — no conflict.

```tsx
const TONE_EMOJI: Record<string, string> = {
  shocking: '😮', funny: '😂', touching: '🥺',
  relatable: '🙌', inspiring: '🔥', controversial: '🤔', insightful: '💡',
};
const emoji = clip.tone && TONE_EMOJI[clip.tone];

// In JSX (replaces <ReasonChip>):
{emoji && !analysisStale && (
  <span
    className="pointer-events-none absolute left-2 top-2 z-40 select-none rounded-md text-[22px] leading-none"
    style={{ padding: '3px 4px', background: 'rgba(0,0,0,0.62)' }}
  >
    {emoji}
  </span>
)}
```

Stale state: don't render the emoji badge (or render greyed out — simpler to just hide it).

### Key moment block

Add below the hook heading, above the "Why it works" section:

```tsx
{clip.key_quote && (
  <div className="mt-3 rounded-sm border-l-2 border-emerald-500 bg-emerald-950/40 px-2.5 py-1.5">
    <p className="mb-1 text-[7px] font-bold uppercase tracking-widest text-emerald-500">
      ★ Key moment
    </p>
    <p className={`text-[10px] italic leading-relaxed ${analysisStale ? 'text-muted/30' : 'text-emerald-200'}`}>
      "{clip.key_quote}"
    </p>
  </div>
)}
```

### "Why this clip ↓" accordion

Replace the current always-visible "Why it works" block with a collapsible accordion:

```tsx
const [open, setOpen] = useState(false);

<button
  type="button"
  onClick={() => setOpen(o => !o)}
  className="mt-2 text-[10px] text-muted hover:text-ink transition-colors"
>
  {open ? 'Why this clip ↑' : 'Why this clip ↓'}
</button>

{open && (
  <div className="mt-2 border-t border-line pt-2 space-y-2">
    {/* Quality signals */}
    <p className="text-[7.5px] font-bold uppercase tracking-wider text-muted">Quality signals</p>
    <div className="flex gap-2">
      {computeSignalBars(clip).map(({ label, bars }) => (
        <div key={label} className="flex flex-1 flex-col items-center gap-1">
          <div className="flex items-end gap-0.5 h-3.5">
            {[4, 7, 11, 14].map((h, i) => (
              <div
                key={i}
                className="w-1 rounded-[1px]"
                style={{
                  height: h,
                  background: i < bars ? '#4ade80' : '#262626',
                }}
              />
            ))}
          </div>
          <span className="text-[7px] text-muted text-center">{label}</span>
        </div>
      ))}
    </div>
    {/* Reason */}
    <p className={`text-[10.5px] leading-relaxed border-t border-line pt-2 ${analysisStale ? 'text-muted/30' : 'text-muted'}`}>
      {clip.why_works ?? clip.reason}
    </p>
  </div>
)}
```

#### `computeSignalBars()` helper (put in same file or `/lib/clipSignals.ts`)

```ts
function computeSignalBars(clip: ClipOut): { label: string; bars: number }[] {
  const score = clip.score; // 0–1
  return [
    {
      label: 'Hook',
      bars: score >= 0.85 ? 4 : score >= 0.70 ? 3 : score >= 0.55 ? 2 : 1,
    },
    {
      label: 'Standalone',
      bars: ['standalone', 'emotional_peak'].includes(clip.type) ? 4
          : clip.type === 'complete_thought' ? 3
          : clip.type === 'strong_quote' ? 3
          : 2,
    },
    {
      label: 'Energy',
      bars: ['shocking', 'funny', 'controversial'].includes(clip.tone ?? '') ? 4
          : ['inspiring', 'relatable', 'insightful'].includes(clip.tone ?? '') ? 3
          : clip.tone === 'touching' ? 2
          : 1,
    },
    {
      label: 'Speaker',
      bars: (clip.hook?.length ?? 0) > 60 ? 3 + (clip.why_works ? 1 : 0)
          : (clip.hook?.length ?? 0) > 30 ? 2 + (clip.why_works ? 1 : 0)
          : 1 + (clip.why_works ? 1 : 0),
    },
  ].map(s => ({ ...s, bars: Math.min(4, Math.max(1, s.bars)) }));
}
```

These are visual approximations — no LLM cost, no DB field. Can be tuned without migration.

### Stale state

Triggered **client-side** when `|newStart - originalStart| > 5s OR |newEnd - originalEnd| > 5s`.

`analysisStale` is a local boolean — **not stored in DB, no migration needed**.

Stale card:
- Score number: `text-surface-3` (dark grey), bar: `bg-surface-3 shadow-none`
- Hook text: `text-muted/40`
- Emoji: hidden
- Glow: removed (neutral border)
- Replace key-moment block with stale banner:
  ```tsx
  <div className="flex items-center justify-between gap-2 rounded-sm border border-line bg-surface-2 px-2 py-1.5">
    <span className="text-[9px] text-muted">Clip moved · AI analysis may be outdated</span>
    <button onClick={handleRefresh} className="text-[9px] font-bold text-amber-400 shrink-0 
      px-1.5 py-0.5 bg-amber-400/10 border border-amber-400/20 rounded">
      ↻ Refresh
    </button>
  </div>
  ```
- `why_works` text: `text-muted/30`
- Signal bars: all grey (`#262626`)

After Refresh resolves: reset `originalStart`/`originalEnd` to new values, clear stale flag, update card from API response.

---

## Backend Changes

### 1. `models.py` — `Segment` model (line 75)

Add after `hook_style`:
```python
tone: str | None = None
key_quote: str | None = None
```

### 2. `models.py` — `ClipOut` model (line 119)

Add after `hook_style`:
```python
tone: str | None = None
key_quote: str | None = None
```

### 3. `stage2_select.py` — `_LlmSegment` (line 356)

Add after `why_works`:
```python
key_quote: str | None = None
```

(`tone` already exists in `_LlmSegment` — no change needed there.)

### 4. `stage2_select.py` — `postprocess()` (line ~245)

In the section that reads `hook_raw`, `why_raw`, `style_raw` — add:
```python
tone_raw = item.get("tone")
key_quote_raw = item.get("key_quote")
tone = str(tone_raw).strip().lower() or None if tone_raw else None
key_quote = str(key_quote_raw).strip() or None if key_quote_raw else None
```

In the `Segment(...)` constructor call (~line 265), add:
```python
tone=tone,
key_quote=key_quote,
```

### 5. `prompts/select_moments.v2.txt`

After the `why_works` line in the STEP section, add:

```
STEP 5 — `key_quote`: copy the single most impactful verbatim line from within this clip's word
range. Must be a direct quote (exact words spoken), not a paraphrase. Max 180 chars. This is the
line a viewer would screenshot or share. If no single line stands out, pick the strongest sentence.
```

Also add `key_quote` to the HARD RULES / REQUIRED list at the bottom.

### 6. Segment → ClipOut mapping

Search for `ClipOut(` in `run.py`, `cloud_state.py`, and `db.py`. Add `tone=segment.tone, key_quote=segment.key_quote` at every site. (There may be 1–3 mapping sites.)

### 7. New endpoint — `POST /jobs/{job_id}/clips/{clip_id}/refresh-analysis`

Add to `main.py` (follow the pattern of other `@app.post("/jobs/{job_id}/...")` endpoints):

```python
@app.post("/jobs/{job_id}/clips/{clip_id}/refresh-analysis")
def refresh_clip_analysis(
    job_id: str,
    clip_id: str,
    body: RefreshClipBody,  # { start: float, end: float }
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> ClipOut:
    """Re-run tone/key_quote/score analysis for a single clip after user edits its boundaries."""
```

Logic:
1. Auth check (`_resolve_user`)
2. Load job transcript from DB/artifacts
3. Slice words to `[body.start, body.end]`
4. Call `select_segments(words_slice, title=job.title, n=1, ...)` — returns 1 `Segment`
5. Update `job_artifacts` for this clip: `score`, `reason`, `why_works`, `hook`, `tone`, `key_quote`, `type`, `hook_style`
6. Return updated `ClipOut`

Cost: ~1 Gemini Flash call (~$0.0002). Runs synchronously in the existing FastAPI worker.

### 8. Run codegen

After all model changes:
```
just types
```

This regenerates `packages/shared/src/types.ts`. Do NOT touch that file manually.

---

## Files to Change

| File | Change |
|------|--------|
| `services/worker/app/models.py` | Add `tone`, `key_quote` to `Segment` AND `ClipOut` |
| `services/worker/app/pipeline/stage2_select.py` | Pass `tone`/`key_quote` through `postprocess()`, add `key_quote` to `_LlmSegment` |
| `services/worker/app/prompts/select_moments.v2.txt` | Add STEP 5 `key_quote` |
| `services/worker/app/main.py` | Add `POST /jobs/{job_id}/clips/{clip_id}/refresh-analysis` |
| `run.py` / `cloud_state.py` / `db.py` | Map `tone`+`key_quote` in every `ClipOut(...)` call |
| `apps/web/components/ClipCard.tsx` | Full redesign per above |
| `packages/shared/src/types.ts` | **Auto-generated via `just types` — do not touch manually** |

---

## Out of Scope

- Per-plan rate limits on Refresh calls
- Animations on the score bar (bar width transition is fine)
- Bulk refresh after major re-cut
- The `ReasonChip` component itself — keep the file, just stop using it in `ClipCard`
- Any change to `ClipGrid.tsx` or `ClipPreview.tsx`

---

## Test Plan

### Backend (TDD — write failing tests first per CLAUDE.md)

**`test_stage2_select.py`:**
```python
def test_postprocess_passes_tone_and_key_quote():
    raw = [{
        "start_word_index": 0, "end_word_index": 5,
        "type": "emotional_peak", "reason": "test", "score": 0.8,
        "tone": "shocking", "hook": "test hook", "why_works": "works",
        "hook_style": "story", "key_quote": "This changed everything."
    }]
    words = [Word(text=f"word{i}", start=i*1.0, end=i*1.0+0.9) for i in range(10)]
    result = postprocess(raw, words)
    assert result[0].tone == "shocking"
    assert result[0].key_quote == "This changed everything."

def test_postprocess_tone_none_when_missing():
    # tone absent → Segment.tone is None, no crash
    ...
```

**`test_refresh_analysis.py`:**
```python
def test_refresh_returns_updated_clip(mock_gemini):
    # Call endpoint with new start/end
    # Assert tone/key_quote/score updated in response
    ...
```

### Frontend (manual — load real editor)

1. Upload a video, wait for clips to appear
2. Verify: glow colour matches `clip.tone`, emoji at top-left of thumbnail, 28px amber score, key moment quote shows
3. Move a clip boundary > 5s in the editor → verify stale banner appears on the card
4. Click ↻ Refresh → verify card returns to active state, new data renders
5. Clip with `tone: null` → verify neutral card (no glow, no emoji)
6. `prefers-reduced-motion: reduce` → count-up starts from final score (existing behaviour preserved)

### Gate

Run `just check` before committing (ruff + mypy + tsc + eslint + unit tests).

---

## Visual Reference

Approved mockup: `.superpowers/brainstorm/935-1782653330/content/clip-card-final-approved.html`  
Visual companion: `http://localhost:62556` (local only)
