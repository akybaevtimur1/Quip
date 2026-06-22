# Quip — Documentation Index (START HERE)

> **This is the single entry point.** Docs were written session-by-session and got scattered —
> this file is the map: what's TRUE right now, what to read (and in what order), what's just
> history, and what you must NOT break. If a doc contradicts this file, **this file wins** for
> "current reality"; the older doc is kept only for the *why*/history.
>
> Last reality check: **2026-06-22.**

---

## 🚨 NEXT SESSION — pending / how to resume (READ FIRST, impossible to miss)

> End of session **2026-06-22**. Work landed on branch **`editor-snapping`** (NOT merged to `main`)
> and was deployed to PROD **via CLI**, bypassing GitHub (the GitHub account `Varenik-vkusny` is
> **suspended** → `git push` = 403). Full detail → `docs/JOURNAL.md` (top three 2026-06-22 entries).

**Pending tasks (do these as they unblock):**
1. **⚠️⚠️ Merge `editor-snapping` → `main` THE MOMENT GitHub is unsuspended** — otherwise the next
   push-to-`main` Vercel build rebuilds from OLD code and **REVERTS all 8 of this session's commits**
   (prod is currently running CLI deploys of `editor-snapping`, not `main`).
2. **Verify + deploy the "Shots" tab** (per-shot framing, commit `7c4508f`) — committed + gate-green
   but NOT deployed; verify on **localhost:3000** (worker CORS only allows :3000, not :3007), then deploy.
3. **Set the Modal `LLM_MODEL` secret to `gemini-2.5-flash`** (belt-and-suspenders for the Gemini-3
   cost guard — the `config.pin_llm_model` validator already coerces it, but fix the secret too).
4. **Wire the demo `<video>` into the landing hero** — assets ready in `apps/web/public/demo/`
   (`quip-demo-pipeline.{mp4,webm}` + `-poster.jpg`); snippet exists, not yet wired.
5. **GitHub account reinstatement** — founder action (support contacted, waiting).

**How to deploy WHILE GitHub is suspended** (push-to-main is dead):
- Frontend: `vercel deploy --prod --scope timurkas-projects` (needs `.vercelignore`, already committed —
  a bare CLI deploy uploads 1.9 GB and hits Vercel's 100 MB/file limit).
- Worker: `modal deploy deploy/modal/worker.py` (unchanged; set `$env:PYTHONIOENCODING="utf-8"` first).

---

## 🟢 Current reality (the baseline — many older docs predate this)

- **It's LIVE in production.** Not a local prototype anymore.
- **Frontend:** Vercel project **`quip-app`** — **auto-deploys on every push to `main`**.
  (The old note "apps/web isn't deployed / the `quip` Vercel project is the landing repo" is
  **OUTDATED**. `quip` = old landing; `quip-app` = the real app.)
- **Worker:** Modal app **`quip-worker`** — `https://akybaevtimur7--quip-worker-web.modal.run`
  (functions `web` / `run_job` / `upload_job` / `render_job` / **`reframe_render_clip`** (per-clip
  fan-out) / **`preview_job`**; `/healthz` → 200). Redeploy = `modal deploy deploy/modal/worker.py`
  (on Windows set `PYTHONIOENCODING=utf-8` first).
- **Латентность фронта воркера (perf, 2026-06-18):** функция `web` (FastAPI) теперь
  **`min_containers=1` (всегда тёплая) + `@modal.concurrent(max_inputs=100)`**. Раньше была
  scale-to-zero без concurrency → холодный старт **~5с перед стартом загрузки** (замер: cold 4.9s
  vs warm 0.35s) и под нагрузкой (десятки юзеров) рой холодных контейнеров → тормозило у всех.
  Теперь один тёплый контейнер тянет сотни параллельных upload-url/status/upload-complete.
  Pipeline-функции (`run_job`/`render_job`/…) ОСТАЮТСЯ scale-to-zero (warm там дорого — тяжёлый
  образ torch/mediapipe). Цена: 1 лёгкий web-контейнер 24/7. Источник: `deploy/modal/worker.py`.
- **Клипы стримятся по готовности (UX, 2026-06-19).** После Select воркер сразу персистит ВСЕ
  клипы с метаданными (хук/причина/скор), но ПУСТЫМ `video_url`, статус `rendering`; каждый
  параллельный фан-аут-контейнер атомарно вписывает свой `video_url` по готовности (Postgres-RPC
  `set_clip_video_url` = server-side `jsonb_set`, миграция **0010**, без гонок). `GET /jobs/{id}`
  отдаёт готовые клипы, пока статус ещё `rendering`. Фронт показывает клипы по одному: готовые сразу
  играбельны/редактируемы, ещё рендерящиеся — со скелетоном «Rendering…» + строка «N of M ready»
  (`ClipGrid`/`ClipCard`). Контракт не менялся: пустой `video_url` = «ещё рендерится». Источник:
  `run.py` (`set_clips_pending`/`set_clip_ready`) + `db.py`/`cloud_state.py`.
- **Live Clip Feed — карточки до рендера (UX, 2026-06-20).** `set_clips_pending` теперь зовётся
  СРАЗУ после select (status=`selecting`, progress 60), а не на границе рендера → богатые карточки
  (хук/why/score) встают на ~60%, за минуты до видео. `JobProgress` в окне 0–60% показывает
  live-счётчики (`source_minutes/transcript_words/moments_found`, миграция 0011,
  `db.set_progress_detail` best-effort). `ClipCard`: `PendingThumb` (client frame-grab из
  preview-прокси, БЕЗ crossOrigin — CDN без CORS) + всплытие карточки + счёт скора. Спека/план:
  `docs/superpowers/{specs,plans}/2026-06-20-live-clip-feed*`.
- **Качество рендера по плану (2026-06-20).** Энкод клипа больше не захардкожен `veryfast/crf20`
  для всех: серверная `RenderPolicy` несёт `video_crf/video_preset` (free 20/veryfast, платные
  **18/medium** — чётче на 1080). Протянут через `render_clip`+`render_timeline`. Только энкод,
  кадровая сетка Δ=0 цела. Источник: `billing.py` + `stage5_render._video_out_args`.
- **Co-watch / live moment discovery (UX, 2026-06-20, LIVE).** Во время обработки загруженное видео
  играет СРАЗУ из локального File (object URL — без раунд-трипа/CORS), а найденные «моменты» всплывают
  как чипы-цитаты ПОВЕРХ видео (реальная фраза + тег), затем — graceful handoff на грид клипов. ⚠️
  **ЧИСТО КОСМЕТИЧЕСКИ:** маркеры из отдельной pure-эвристики (`pipeline/preview_moments.py`:
  транскрипт-сигналы + аудио-энергия) и **НИКОГДА не идут в `select_segments`** → качество AI-нарезки
  не меняется. Персист в `job_artifacts.preview_moments` (миграция **0012**), эндпоинт
  `GET /jobs/{id}/preview-moments`. Фронт: `CoWatch.tsx`/`CoWatchPanel.tsx` (+ `/dev/cowatch` харнесс).
- **Фикс: правки хука/субтитров не применялись на ре-рендере (2026-06-20).** НЕ ASS-слой — **CDN
  edge-cache**: `upload_clip` перезаписывал ТОТ ЖЕ R2-ключ, а `cdn.quip.ink` (Cloudflare) кэшировал mp4
  без `Cache-Control` → Download тянул старый рендер (било ЛЮБУЮ правку после первого рендера). Фикс:
  `Cache-Control: no-cache` на заливке + cache-buster `?v=<clip_edit.version>` на render-URL
  (`storage.clip_upload_extra_args` + `storage.with_cache_bust` в `get_render`). Только экспорт/кэш.
- **Редактор «Fixed Studio» (WS-A) — ветка `editor-fixed-studio`, не смёрджена.** Новый shell:
  левый icon-rail (Agent/Captions/Hook/Style/Frame) + стабильный canvas + contextual inspector.
  P0-баг «Frame-панель уменьшает видео» закрыт (canvas отвязан от высоты контента панели). Preview
  aspect-contain fix (9:16 в широком canvas). In-page переключение клипов без ремаунта + prefetch.
  Live Frame mode (без Apply). De-overload Hook + grouped Style + preset grids. English preset names.
  Spec/plan: `docs/superpowers/specs/2026-06-20-editor-fixed-studio-design.md`.
- **Редактор: правки сессии 2026-06-22 (ветка `editor-snapping`, в проде через CLI, не в `main`).**
  (1) **Субтитры авто-фитятся в рамку** — один стабильный кегль на клип, каждая страница влезает в рамку
  (ширина блока × вертикальный бюджет); ручной Size = ПОТОЛОК, реальный контроль = ширина рамки.
  Фронт-only, пишется в `style.size` (рендер и так чтит) — `lib/captionFit.ts` (pure+TDD) +
  `captionFitBrowser.ts`. (2) **Safe-area UI удалён**, выравнивание/snapping = жёсткий дефолт без тумблера
  (удалены `SafeAreaOverlay`/`SnapControls`/`lib/safeAreas.*`/`lib/editorPrefs.*`; `SnapGuides` остались).
  (3) **Он-видео драг/ресайз:** libass-текст едет 1:1 с рамкой во время жеста (`LibassLayer` тегает канвасы
  `data-libass-part`, `OverlaySelectionBox` накладывает translate/scale, хэндофф по предикату libass-bbox).
  (4) **Шрифт хука теперь попадает в рендер** — НЕ кэш/воркер, а фронт-гонка: `handleRender` не делал
  `await flushPending()` (правки на ~300мс дебаунсе) + `ExportMenu` отдавал stale baked CDN-рендер →
  `captionedDownloadUrl(...,dirty)` роутит грязные скачивания в on-demand `export/captioned.mp4`.
  (5) **Poppins прожигается** — нормализована name-таблица TTF (ID 1) → «Poppins» в ОБОИХ каталогах
  (`services/worker/fonts` + `apps/web/public/libass/fonts`) + гард `test_fonts.py` (нужен был деплой
  воркера). (6) Карточки клипов не прыгают (`ClipCard` flex/line-clamp/mt-auto) + float-время убрано
  (общий `mmss()`). (7) Скачивание = fetch+спиннер «Preparing your clip…» (`ExportMenu`).
  JOURNAL: записи 2026-06-22.
- **Рендер клипов = параллельный фан-аут (perf, 2026-06-17).** `run_job` делает import→
  transcribe→select, грузит source в R2, затем фанит per-clip reframe+render по контейнерам
  `reframe_render_clip` (`starmap`) вместо последовательного цикла. **preview-прокси** (полный
  транскод source→720p) снят с критического пути — отдельная `preview_job` строит его ПАРАЛЛЕЛЬНО
  с клипами (редактор фолбэчит на source, пока не готов). Локально (dev) — старый цикл + inline
  preview. Не трогает stage3/stage5 (инвариант кадровой сетки цел). См. JOURNAL 2026-06-17.
- **State:** Supabase Postgres project **`qiagetbnsssvbiowuxpp`**, migrations **0001–0012 applied**
  (0009 = RLS на agent_runs; 0010 = RPC `set_clip_video_url` для incremental-выдачи клипов;
  0011 = `jobs.source_minutes/transcript_words/moments_found` для live-narration счётчиков;
  0012 = `job_artifacts.preview_moments` для co-watch-маркеров)
  (billing, credits, usage-idempotency, feedback, promo codes, job-cancel, agent-runs, **video-map**). Clips in **Cloudflare R2**
  (`cdn.quip.ink`).
- **Billing is ON** (`BILLING_ENABLED`). Payments via **Polar** (NOT Lemon Squeezy). Webhook live
  and verified. Pricing = **credit model** (Free $0 / 2 · Starter $15 / 10 · Pro $35 / 30 · PAYG $3);
  source of truth = `services/worker/app/billing.py`, mirrored by `apps/web/lib/plans.ts`.
- **AI-модели:** транскрипция — Deepgram **`nova-3`**; отбор/хуки/агент — **Gemini**, запинено на
  **`gemini-2.5-flash`** (⚠️ 2026-06-22: `gemini-flash-latest` уехал на `gemini-3.5-flash` = ~×10 цена;
  `config.pin_llm_model` коэрсит любой `*-latest`/`gemini-3*` → `gemini-2.5-flash` с логом, поэтому даже
  Modal-секрет `LLM_MODEL=gemini-flash-latest` безопасен — но рекомендуется обновить секрет на
  `gemini-2.5-flash`). Фолбэк: select/хуки → `-flash-lite`; **чат-агент** — цепочка
  `gemini-2.5-flash → 2.5-flash-lite` (раньше начиналась с `-latest`; убрано тем же гардом). Гард-тест
  `test_config_llm_guard.py`. Видео в LLM не уходит — только индексированный текст транскрипта.
- **Язык чат-агента (2026-06-18):** ЧАТ — на языке юзера; ON-SCREEN хук — ВСЕГДА на языке
  ТРАНСКРИПЦИИ клипа (язык видео), даже если юзер пишет на другом (`set_hook_text` переводит).
  Источник: `prompts/agent_clip_editor.v1.txt` (LANGUAGE POLICY).
- **Объяснимость + Карта видео (2026-06-18, LIVE — дифференциатор):** после select воркер фоном строит
  **VideoMap** (Gemini: связный нарратив + главы + цветные «моменты» tension/quote/emotional/insight/funny
  + привязка к клипам). Хранится в `job_artifacts.video_map` (jsonb, кросс-контейнерно — Postgres-first
  read). Эндпоинт `GET /jobs/{id}/video-map` (?retry). Фронт: **«Карта видео»** над гридом на странице
  результатов (`VideoMap.tsx`) + **строка тем** в редакторе (`TopicStrip.tsx`, «Подвинуть клип сюда»,
  ≥20с). Агент знает контекст всего видео (тул `get_video_map`). **Мин. длина клипа = 20с** (везде).
  «Сделать новый клип» из карты — ОТЛОЖЕНО (нет endpoint create-clip; пока только «подвинуть»). Источник
  правды генерации: `app/editor/video_map.py` + `prompts/video_map.v1.txt`.
- **Auth:** Supabase (Google OAuth + email). The `(app)` route group is gated.
- **Язык интерфейса (2026-06-18):** курс на **консистентный английский** — раньше был хаотичный
  микс RU/EN. Весь user-facing текст (UI + user-facing `JobError`) приводится к английскому; русский —
  только в комментариях/доках. **Правило:** новые строки — по-английски, без хардкода смеси (см.
  `CLAUDE.md`). Полноценный мультиязык (next-intl, тумблер RU+EN) — отложенная фаза.
- **Анти-абьюз free (2026-06-18):** free-джоба требует **подтверждённого email** (серверный gate
  во всех точках создания, проверка `email_confirmed_at` через Supabase Admin API) + **блок
  одноразовых email-доменов** (`billing.is_disposable_email` + зеркало `lib/disposableEmail.ts`).
  Google OAuth = уже verified. ⚠️ Требует Supabase «Confirm email» = ON (см. `SUPABASE_SETUP §6`).
- **Вотермарк free (2026-06-18):** план берётся СЕРВЕРНО от владельца джобы; для free прожигается
  вотермарка в КАЖДЫЙ клип + кап 720p (обход через экспорт из редактора закрыт). Источник:
  `billing.resolve_render_policy` + `stage5_render`.
- **Uploads = direct browser→R2** (presigned PUT), NOT through the worker. `POST /jobs/upload-url`
  → browser PUTs straight to R2 → `POST /jobs/{id}/upload-complete` spawns processing. Needs an R2
  **CORS rule** on the bucket (set in Cloudflare dashboard — done; JSON in `deploy/modal/r2_setup.py`).
  Local dev still uses the old multipart `POST /jobs/upload`. (Old single-POST path broke on big files.)
  Files **>100 MB use R2 multipart** (parallel resumable parts: `/jobs/upload-url` returns a
  presigned URL per part → `upload-complete` assembles → `/jobs/{id}/upload-abort` cleans up).
  **Cap = 10 GB** (`SourceForm.MAX_UPLOAD_MB`, just a guard); real limit is **3 h**
  (`billing.MAX_VIDEO_MINUTES`). Modal pipeline funcs (`run_job`/`upload_job`) run **`timeout=10800`
  (3 h)** + **`cpu=4, memory=4096`** so a long/heavy source (preview transcode + reframe/render)
  isn't killed and isn't starved. R2 CORS must allow the web origin + **expose `ETag`** (multipart).
- **R2 retention:** daily Modal Cron `cleanup_stale_sources` deletes `source.mp4`/`preview.mp4`
  older than **60 days** (clips kept forever) — source is 70–90 % of storage; without this R2 grows
  unbounded (one-time payment, perpetual storage). Egress is free; only GB-month bills (>10 GB tier).
- **Clips: up to 30** (`resolve_max_clips hi=30`) with an **Auto** mode ("as many as found, ≤30") vs
  Custom 1–30 in `SourceForm`.
- **Editor preview video = a lightweight `preview.mp4` proxy** (≤720p H.264 faststart, made per job),
  served via CDN (`cdn.quip.ink`); source also CDN now. Render still uses the full source. Old jobs
  fall back to source. (Editor video used to load the full 50–160 MB source → slow.)
- **Vercel Analytics** is wired (`<Analytics/>`), invisible. ⚠️ Must be **enabled once** in the Vercel
  project dashboard (Analytics tab) for data to flow.
- **Pipeline needs audio:** a video with no audio track fails early with a clear message (Quip cuts on speech).
- **Stop/cancel:** a job can be cancelled during the FREE phase (download/probe, before transcription) via
  `POST /jobs/{id}/cancel` → **charges nothing** (`_meter` runs only after `set_done`; Modal
  `FunctionCall.cancel` raises `InputCancellation`/BaseException → never reaches `set_done`). The Stop
  button shows only while `Job.cancellable` (flag flips false at the paid boundary). Closing the tab does
  NOT cancel (job runs on in Modal; shows in recent). Migration `0006` applied (`cancellable`/`function_call_id`).

### Shipped (this is "all of it" up to 2026-06-18)
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
error → **Stop/cancel джоба** (FREE-фаза, $0) → **selection-end quality** (W1: snap `.?!`/пауза +
tail-pad, реальный max в промпт) → **emotion-driven styled hooks** (W2: tone→style→text + few-shot,
`hook_style`) → **hook regeneration for re-cut clips** (W4: `/hook/regenerate`, узкий Gemini-вызов)
→ **no charge on our errors** (биллинг: ошибка/0 клипов → минуты НЕ списываются) → **agent clip
editor** (W3: чат-агент правит интервал/хук тулзами, Gemini function-calling, фон+Stop, $0;
НЕ трогает субтитры/кадр) → **объяснимость + карта видео + умная нарезка** (2026-06-18: VideoMap
нарратив/главы/моменты на результатах + строка тем в редакторе с клик-обрезкой, агент с контекстом
всего видео, мин. длина клипа 20с; миграция 0008; боевой тест на реальном видео пройден).
Founder account = Pro + 1000 credits (for testing).

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
that exact feature) · `docs/ADMIN_PANEL_RESEARCH.md` (monitoring spend/usage) ·
`docs/SESSION_2026-06-20.md` (the most recent big session: editor overhaul, render quality, Live Clip
Feed, co-watch, hook-cache fix — read if touching any of those).

> **Starting a new session? Paste `docs/NEXT_SESSION_BOOTSTRAP.md` as your first message** — it tells
> the agent exactly what to read (this file → CLAUDE.md → task-specific docs) before doing anything.

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
| Editor (timeline/captions/preview) | `docs/superpowers/specs/2026-06-12-editor-v3-design.md` + `…wysiwyg-libass-preview…` · **layout/shell (WS-A):** `docs/superpowers/specs/2026-06-20-editor-fixed-studio-design.md` |
| Billing / Polar / credits | `app/billing.py`, `app/polar.py`, this file's "Money paths" |
| UI / design | `DESIGN.md` + `apps/web/AGENTS.md` |
| Deploy / infra | "Deploy & infra map" below (ignore `apps/web/DEPLOY.md` step 1) |
| Cost / model choice | `docs/BENCHMARKS.md` |

---

## 🏗️ Deploy & infra map

> ⚠️ **2026-06-22: push-to-`main` auto-deploy is currently DEAD** — the GitHub account `Varenik-vkusny`
> is suspended (`git push` → 403). Until reinstated, deploy the frontend with the **Vercel CLI**
> (`vercel deploy --prod --scope timurkas-projects`, needs the committed `.vercelignore`). Prod is
> running CLI deploys of branch **`editor-snapping`**, NOT `main` — **merge `editor-snapping` → `main`
> the moment GitHub is back**, or push-to-main rebuilds old code and reverts the session. See the
> "🚨 NEXT SESSION" banner at the top.

| Piece | Where | How it deploys | Dashboard |
|-------|-------|----------------|-----------|
| Frontend (`apps/web`) | Vercel **`quip-app`** | **normally auto on push to `main`** — ⚠️ TEMPORARILY via CLI `vercel deploy --prod --scope timurkas-projects` (GitHub suspended) | vercel.com/timurkas-projects/quip-app |
| Worker (`services/worker`) | Modal **`quip-worker`** | `modal deploy deploy/modal/worker.py` | modal.com (workspace akybaevtimur7) |
| State / auth / billing data | Supabase **`qiagetbnsssvbiowuxpp`** | SQL Editor / migrations `0001–0012` | supabase.com dashboard |
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
