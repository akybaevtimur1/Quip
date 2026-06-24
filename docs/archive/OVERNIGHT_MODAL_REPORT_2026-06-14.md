# Ночная сессия 2026-06-14 — Боевой воркер на Modal + фронт-полировка

Ветка `feat/modal-boevoy` → **смержена в `main` и запушена** (`63c6a0b..5b0b6a6`).
`just check` зелёный (459 тестов), `next build` зелёный.

---

## ЗАДАЧА 1 — Боевой воркер на Modal: КОД ГОТОВ + ffmpeg-риск ДОКАЗАН на Modal

### Что сделано (всё в коде, протестировано, закоммичено)

**Архитектура (как в брифе, 0 GPU):** dual-mode «disk-first, cloud-fallback».
Локально — SQLite + диск (Phase 0 не сломан). На Modal — Supabase Postgres (стейт) + R2 (клипы/исходник).
Один и тот же код корректен в `run_job`-контейнере, в отдельном web-контейнере и локально.

- `app/cloud_state.py` — PostgREST-слой (service_role bypass RLS) для `jobs` / `job_artifacts` /
  `clip_edits` / `transcript_cache`. Атомарный optimistic-lock = `PATCH ?version=eq.N` +
  `return=representation` (нет строки в ответе → конфликт). +7 PURE-тестов.
- `app/storage.py` — R2 (boto3): `upload_clip` (public URL если задан `R2_PUBLIC_URL`, иначе
  **presigned GET**), `upload_source`/`download_source`/`presigned_source_url`.
- `app/artifacts.py` — единое чтение meta/segments/transcript + source (disk-first / Postgres+R2).
- `app/db.py` — job-стейт/артефакты/edits/transcript-кэш роутятся cloud↔SQLite; `row_to_wire`
  отдаёт http-URL как есть, относительный → `media/`-префикс. +1 тест.
- `app/dispatch.py` — `POST /jobs` → `run_job.spawn` на Modal (НЕ BackgroundTask — scale-to-zero
  убил бы фон-нарезку). Гейт `MODAL_SPAWN=1`.
- `app/editor/store.py`, `run.py`, `tasks.py`, `main.py` — persist артефактов/исходника + upload
  клипов в R2; CORS `allow_origin_regex` (app.quip.ink / *.vercel.app / localhost); render-URL
  passthrough; `GET /jobs/{id}/source.mp4` (local файл / r2 302 presigned).
- `deploy/modal/worker.py` — Modal App **quip-worker**: `web` (asgi, scale-to-zero) + `run_job` +
  `render_job`; **СТАТИК-ffmpeg 7.0.2** (John Van Sickle, НЕ apt); cookies из репо запекаются в образ.

### ДОКАЗАНО на Modal (без секретов) — риск №1 побеждён
`modal run deploy/modal/proof_ffmpeg.py` (run `ap-vM71RIwLjviyC0R3kniQ3U`):
```
ffmpeg: 7.0.2-static (John Van Sickle)   render_ok: True
out: codec=h264, width=1080, height=1920, duration=5.04s, 220KB
```
Тот самый crop-граф (`crop=608:1080:656:0,scale=1080:1920,setsar=1` + frame-exact trim + concat),
что крашит debian-apt-ffmpeg («Parsed_crop_4: Failed to configure input pad»), на статик-ffmpeg
даёт валидный 9:16 mp4. **Образ для боевого деплоя ставит тот же статик-ffmpeg.**

### ⚠️ ОСТАЛОСЬ ФАУНДЕРУ (1 шаг — секреты; агент НЕ создаёт чужие креды)
Схема БД уже в проде (Supabase ref `qiagetbnsssvbiowuxpp` — проверено), R2/Deepgram/Gemini/Supabase
ключи есть в корневом `.env`, cookies-файл на месте. НЕ хватает только Modal-секрета.

```bash
# 1) Создать секрет из существующего .env + прод-оверрайды (креды НЕ инвентятся):
modal secret create quip-worker --from-dotenv .env \
    STORAGE_BACKEND=r2 BILLING_ENABLED=true LLM_PROVIDER=gemini TRANSCRIPTION_PROVIDER=deepgram --force
#   (опц. R2_PUBLIC_URL=https://pub-xxxx.r2.dev — иначе клипы отдаются presigned-URL, тоже играются)

# 2) Деплой (соберёт образ ~неск. мин, статик-ffmpeg уже доказан):
modal deploy deploy/modal/worker.py
#   → выдаст URL web-эндпоинта вида https://akybaevtimur7--quip-worker-web.modal.run

# 3) e2e: открыть app.quip.ink (залогиненным) → вставить YouTube-ссылку → клипы из R2.
```
Auth-цепочка проверена: JWKS ES256 на проекте включён; фронт шлёт `Authorization: Bearer`.
`BILLING_ENABLED=true` → free-план = 2 видео/мес (для теста хватит, дальше — апгрейд/PAYG).

---

## ЗАДАЧА 2 — Фронт: i18n ядра + прогон + фиксы

### Сделано
- **i18n: ядро редактора + грид + шелл → АНГЛИЙСКИЙ** (22 файла): SourceForm, EditorHeader,
  табы Captions/Hook/Style/Frame, PreviewPlayer, TimelineV2, ClipEditorScreen; ClipCard/ClipGrid/
  JobProgress/StatusBadge/ErrorPanel/ExportMenu/CaptionOverlay; dashboard/AppHeader/UsageMeter/
  RecentProjects; user-facing ошибки в api.ts/useJob.ts. Логика/WYSIWYG не тронуты. Осталась только
  Кириллица в КОММЕНТАХ кода (не user-facing). `tsc` + `eslint` + `next build` зелёные.
- **Playwright-прогон app.quip.ink:** landing, /pricing, /login, /terms — всё рендерится чисто,
  английское, контраст ок (скрины `sweep_*.jpeg` в корне). /terms /privacy НЕ 404 (старый 404 был
  устаревший билд). Пустой «средний блок» лендинга на full-page-скрине = артефакт scroll-reveal
  (IntersectionObserver не триггерится в full-page-capture); при реальном скролле секции на месте
  (проверено evaluate: все 8 секций opacity:1/visible).
- **Фикс /pricing:** `prefetch={false}` на Polar-checkout-ссылках → ушли 6 CORS-ошибок в консоли
  (Next RSC-prefetch следовал redirect `/checkout`→polar.sh). Клик работал и так.

### ⚠️ ВАЖНО ПРО ДЕПЛОЙ ФРОНТА (находка через Vercel MCP)
Единственный Vercel-проект в команде «Timurka's projects» — **`quip`** — собирается из репозитория
**`Shorts-Automatizator`** (это ЛЕНДИНГ, CLAUDE.md правило #10 «не трогать»), НЕ из `clipflow/apps/web`.
То есть пуш в `clipflow` сам по себе НЕ деплоит на app.quip.ink, а app.quip.ink (Next-инструмент)
деплоится отдельным путём, который этому MCP-токену не виден.

**Поэтому я НЕ трогал Vercel-env** (чтобы не залезть в чужой лендинг-проект) и НЕ могу подтвердить,
что i18n-правки уже на проде. Фаундеру:
1. Подтвердить, какой Vercel-проект обслуживает app.quip.ink из `clipflow/apps/web`, и задеплоить
   ветку `main` (i18n + фиксы там).
2. После `modal deploy` — прописать на ЭТОМ проекте `NEXT_PUBLIC_WORKER_URL = <Modal web URL>` → redeploy.
   (Клип-URL: `resolveUrl` уже отдаёт http-URL как есть; для относительных префиксит worker URL —
   правка не нужна.)

---

## Открытое / follow-up
- Live e2e (YouTube→R2→Supabase→фронт) не прогнан — ждёт Modal-секрет (1 шаг выше).
- Editor re-render на Modal: source качается из R2 (`render_job`) — реализовано, но вживую не
  прогнано (нужен секрет).
- chapters-кэш (`chapters.json`) пока на scratch-диске контейнера → на холодном web-контейнере
  может перегенериться (Gemini). Перенос в Postgres — Phase C.
- upload-файл путь на Modal идёт BackgroundTask'ом (файл на web-контейнере) — основной поток YouTube
  через spawn; для serverless-надёжности upload'а нужен R2-промежуток (follow-up).
- Кириллица в комментах кода фронта оставлена (не user-facing).
