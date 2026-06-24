# Night-Audit Integration Review — `a4ce036..HEAD`

Reviewer: integration/correctness pass over the cumulative diff of 5 commits
(`8a819f2`, `191816e`, `a6c8927`, `ecfb791`, `9a07bf4`).
Method: read per-domain rationale (`docs/night-audit/*.md`), then verified the **code**
against the intent + ran the touched test suites. Evidence below.

## Verdict summary

| # | Focus area | Verdict |
|---|------------|---------|
| 1 | PAYG money math (BE-H) | ✅ correct |
| 2 | ASS escaping (BE-D) | ✅ correct |
| 3 | Reframe finally-release (BE-C) | ✅ correct — invariant untouched |
| 4 | Gemini retry classifier (BE-B) | ✅ correct |
| 5 | Auth proxy cookies (FE-F) | ✅ correct |
| 6 | getJob timeout (FE-D) | ✅ correct |
| 7 | editRef sync (FE-C) | ✅ correct (one cosmetic gap, not a live bug) |

**Concerns by severity: 0 critical, 0 high, 0 medium, 3 low (all advisory).**
Nothing blocks calling the night done. No bug requires a fix before ship.

Verification run (this review, not just agent claims):
- `pytest` over all touched backend suites → **300 passed** (test_tasks, test_billing,
  test_supa, test_db, test_stage2_select, test_stage3_reframe, test_stage4_captions,
  test_captions_v2, test_editor_ops, test_editor_api, test_stage0_import,
  test_stage1_transcribe, test_hook).
- `pnpm --filter web exec tsc --noEmit` → **EXIT=0**.

---

## 1. PAYG money math (a6c8927) — ✅ correct

Traced the full accounting loop:

- `check_quota` (billing.py:166-178): `from_monthly = min(source, monthly_remaining)`,
  `shortfall = source - from_monthly` = `from_payg`. The two are **disjoint and sum to
  `source_minutes`** — no overlap, so no double-count is possible at the source.
- Gate reads `get_monthly_usage(...).minutes` (= `SUM(source_minutes)` from `usage_events`)
  and `payg_credits` (tasks.py:42-45), computes the decision, and stows it in
  `holder["decision"]` (tasks.py:49). **Same `QuotaDecision` object** is read by `_meter`
  via `holder.get("decision")` (tasks.py:71) — gate and meter cannot drift (one source of
  truth; same `meta.duration` feeds both, per run.py).
- `_meter` records **only `from_monthly_min`** into the monthly window
  (`db.record_usage(..., monthly_minutes, ...)`, tasks.py:75) and deducts
  `payg_credits_for_split` = `ceil(from_payg_min/60)` (billing.py:202-204). No path records
  full minutes when PAYG covered part. ✅ double-charge killed.
- Floor-at-0 verified in **both** backends: db.py `MAX(0, payg_credits-?)` and supa.py
  `max(0, current-credits)`; both no-op on `credits<=0` and on missing profile. Tested
  (`test_supa.py::test_floors_at_zero`, `test_missing_profile_is_noop_no_patch`,
  `test_zero_is_noop`).
- Billing-off path unchanged: no decision → `monthly_minutes = full_minutes`,
  `payg_credits = 0`, PAYG untouched (tasks.py:69-77). Tested
  (`test_meter_no_decision_falls_back_to_full_monthly`).

Full-PAYG edge (monthly exhausted) records `source_minutes=0` into the monthly window, so it
does **not** consume monthly minutes — the gate reads minutes, not the `credits` column, so
the misleading `credits_per_video(0)=1` audit value is harmless. Documented and tested
(`test_meter_all_payg_records_zero_monthly`).

**Residual risk (pre-existing, not introduced, agent already flagged):** `record_usage` /
`deduct_payg` are **not idempotent** — no `UNIQUE(job_id)` on `usage_events`. Normal flow is
safe (one `_meter` per `job_id` after `set_done`; re-render does not call `_meter`). If a
future retry/re-dispatch re-runs the same `job_id`, PAYG could over-deduct and monthly could
double. **Advisory for when billing goes live:** add `UNIQUE(usage_events.job_id)` + idempotent
upsert. Not a regression of this diff.

## 2. ASS escaping (BE-D, 191816e) — ✅ correct

`escape_ass_text` (stage4_captions.py:21-35): order is `\` → `⧵` (U+29F5) **first**, then
`{` → `\{`, `}` → `\}`. Backslash-first is the critical ordering — it prevents the `\{` we
emit from being re-escaped. ✅

Our own override tags are **never** passed through escape:
- stage4 `build_ass`: escapes `ch.text` only; `Dialogue:` scaffolding added after.
- captions_v2 `up()` (captions_v2.py:217-219) escapes glyph text **after** `.upper()`; the
  karaoke/`\1c`/`\t`/`\fscy` tags from `_karaoke_word` and the `{{\\1c…}}` emphasis wrappers
  (captions_v2.py:249) are concatenated **around** the already-escaped text, so they pass
  through untouched. Verified by reading `_reply_text` end-to-end (all 4 branches: override
  with word-map, override plain, karaoke, plain+emphasis).
- `build_hook_event` escapes `hook.text` after upper/strip, before assembling the Dialogue.

The U+29F5 substitution means a user's literal `\` renders as a look-alike glyph (font must
contain the codepoint), not a real backslash. This is a **documented, acceptable** tradeoff
(ASS has no literal-backslash escape) and WYSIWYG holds because preview (libass.wasm) and
export (ffmpeg) consume the identical ASS string. Not a bug. Tested across stage4/captions_v2/hook.

## 3. Reframe finally-release (BE-C, 8a819f2) — ✅ correct, invariant untouched

`detect_scene_cuts` (stage3_reframe.py:556-575): the only change is moving
`vid.capture.release()` into a `finally` with a `vid is not None` guard and adding `vid = None`
before the `try`. **Frame-grid math is byte-identical:** `return [s[0].get_frames() for s in
scenes[1:]]` unchanged; `ContentDetector(threshold=...)`, `get_scene_list()` unchanged. Cross-checked
against `docs/REFRAME_FPS_GRID_INVARIANT.md` — no cut-frame/`build_shots_frames`/`trim` code in
the diff. `scenes` is only referenced on the success path (the `except` re-raises before it),
so no unbound-variable risk. Δ=0 invariant preserved by construction. Two new tests assert
release-on-failure and release-on-success (frame contract pinned).

## 4. Gemini retry classifier (BE-B, 8a819f2) — ✅ correct

`is_transient_gemini_error` (stage2_select.py:174-187): if `exc.code` is an int in
`{400,401,403,404,422}` → permanent (fail fast); **everything else → transient** (retry),
including 429, all 5xx, and any exception without an int `.code` (network/unknown). The
default-True for unknown types means a genuinely transient error is **never** misclassified as
fatal — it errs toward reliability, exactly as required. Permanent path raises
`JobError(... ) from e` preserving root cause, and short-circuits both the primary and the
fallback-model retry loops (stage2_select.py:306-309, 322-324). 408 (Request Timeout) → transient
(correct). 9 unit cases cover 429/500/503→transient, 400/401/403/404→permanent,
httpx ReadTimeout/ConnectError→transient, RuntimeError→transient.

## 5. Auth proxy cookies (FE-F, 9a07bf4) — ✅ correct

`redirectWithCookies` (proxy.ts:49-53) copies **all** `response.cookies.getAll()` (the cookies
`setAll` wrote during `getUser()`'s token rotation) onto the redirect via the full
`ResponseCookie` object. **Both** branches use it: `!user && isProtected` → `/login`
(proxy.ts:59) and `user && isAuthPage` → `/dashboard` (proxy.ts:64). Dual-mode passthrough is
safe — `if (!isSupabaseConfigured) return NextResponse.next()` (proxy.ts:15) returns before any
of this, and the public-page short-circuit (proxy.ts:22) is also before the rotation. No churn,
no auth bounce loop. tsc clean.

## 6. getJob timeout (FE-D, ecfb791) — ✅ correct

`fetchWithTimeout` (api.ts:127-136): `AbortController` with a 15s timer cleared in `finally`
(no leak on either success or throw). Applied **only** to `getJob` (the polling path) — other
api.ts calls are unchanged. A timeout → `AbortError` propagates out of `getJob` → throws (the
`!res.ok` path is not even reached) → counts as a poll failure in `useJob`'s catch (increments
`fails`, reaches MAX_FAILS → surfaces "Lost connection"). The timeout is a **real failure**, not
swallowed. Correct.

## 7. editRef sync (FE-C, ecfb791) — ✅ correct (one cosmetic gap)

There are 6 `setEdit(...)` call sites. Five are paired with a synchronous `editRef.current =`:
- refetchAfter (line 277/278) — **fixed** (the named race path)
- patchChain inner (351/352) — pre-existing, in-queue, correct
- handlePresetApply inner (449/450) — pre-existing, correct
- handleFrameApply (480/481) — **fixed**
- handleAspectChange (497/498) — **fixed**

The three direct-setEdit race paths the report names (trim/frame/aspect) are all covered. The
mutation queue reads `editRef.current` (line 341), so a stale ref → 409 → reload is now avoided.

**[LOW, advisory — not a live bug]** The 6th call, the **initial load** `setEdit(editData)`
(ClipEditorScreen.tsx:197), is **not** paired with `editRef.current = editData`. This is *not* a
race: it runs on mount before the UI is interactive (`setPhase("ready")` follows), and the sync
`useEffect` (line 262-264) commits the ref long before any user mutation can be queued
(`editRef.current` starts `null`; the first mutation is many commits later). Harmless today, but
for consistency/defense-in-depth, adding `editRef.current = editData;` next to line 197 would
make the invariant "every setEdit also sets editRef" total. Optional.

---

## Other-domain scan (BE-A/E/F/G/I, FE-A/B/E, cosmetic)

Reviewed the remaining diffs for systematic errors:

- **stage0_import / stage1_transcribe / run.py / config.py / editor/ops.py / main.py** — all
  defensive hardening: fail-fast guards replacing silent fallbacks (fps<=0, duration<=0,
  missing Deepgram duration, inverted/overlapping editor intervals), HTTP 400 translation for
  editor ops (`_op_or_400`), dispatch-failure → visible `failed` + 500 (`create_job`,
  `post_render`), and a provider-aware transcript cache key (`transcript_cache_model`). All
  consistent with rule #8. No silent swallows.
- **deploy/modal/worker.py (BE-I)** — `YTDLP_COOKIES_FILE` now set only inside
  `if _COOKIES.exists()`, coupled to `add_local_file`. Correct fix for the env/file decoupling.
  (BE-I's flagged HIGH-arch upload-path-on-Modal hang and chapters-cache-not-in-Postgres are
  **not fixed** — they are cross-file/architectural and were explicitly handed to the
  orchestrator. Track separately; neither is introduced by this diff.)
- **generate_chapters_job empty-result → failed** (tasks.py:197-208): `ChaptersData` imported
  locally at line 188 before use (no NameError). Tested.

### Low-severity advisory notes (none blocking)

1. **[LOW] `SignOutButton` empty `catch {}`** (SignOutButton.tsx) — swallows a sign-out
   failure but re-enables the button so the user can retry. Legitimate UX; the user does get
   feedback (no permanently-disabled button), so not a true rule-#8 silent failure. Acceptable.
2. **[LOW] `usd()` is an unused public export** (lib/format.ts) — dead but harmless; FE-D
   chose not to remove it (out of "bugs only" scope). Fine.
3. **[LOW] initial-load editRef gap** — see focus area 7. Cosmetic.

### Quality scan results
- No `console.log` / `print(` / `debugger` introduced.
- No `except: pass` / silent `except Exception: pass` introduced (all bare-ish excepts carry
  `# noqa: BLE001` and route to a visible `failed` status + re-raise/log).
- No `.only`/`.skip` or disabled tests; no tautological tests — the new tests assert concrete
  values (e.g. exact split `5.0` monthly + `1` PAYG deducted; 400 vs 500 status; floor-at-0).
- The only `TODO` hits in the diff are inside the markdown rationale docs (referencing a
  pre-existing in-code TODO), not new shipped code.

---

## Prioritized list for the orchestrator

**Before calling the night done:** nothing required. The 7 focus areas are correct and the
touched suites are green (300 backend tests + tsc clean).

**Optional polish (low, can defer):**
1. Add `editRef.current = editData;` at ClipEditorScreen.tsx:197 to make the editRef invariant
   total (defense-in-depth; not a live bug).

**Track separately (pre-existing / handed off, NOT this diff's regressions):**
2. `UNIQUE(usage_events.job_id)` + idempotent upsert before billing goes live (BE-H residual).
3. Modal upload-path hang + chapters-cache-not-in-Postgres (BE-I HIGH-arch / MED, already
   routed to orchestrator).
