# Инфра-деплой ClipFlow: Modal + Vercel + Supabase — ДИЗАЙН (spec)

> **Статус:** дизайн/spec, одобрено направление фаундером (2026-06-12). НЕ исполнялось.
> Следующий шаг — implementation plan (writing-plans), затем исполнение по фазам.
>
> **Этот документ ФИКСИРУЕТ платформенный выбор**, который в
> `2026-06-13-infra-scaling-cloud-worker.md` был открытым (там перебирались Fly/Render/Hetzner/
> Cloud Run + Redis/RQ). **Решение: Modal** (serverless, встроенная очередь — Redis НЕ нужен).
> Диагностика и auth-логика из того документа и из `2026-06-13-auth-analytics-plan.md` остаются
> валидными; здесь — конкретная целевая архитектура, миграция стейта и роадмап.

---

## 0. TL;DR — что решили и почему

**Цель (ответ фаундера):** реальные юзеры скоро → нужна настоящая прод-инфра с очередью и
изоляцией. Бюджет **<$50/мес** (жёстко). Стиль — **push-and-forget** (соло, запуск через недели,
ноль желания админить серверы). Латентность — **текущие ~60-75с/ролик ок**, главное «не падать
и не стоять в очереди час». **→ GPU НЕ нужен** (это убирает самую дорогую ветку).

**Стек:**

| Слой | Решение | Стоимость |
|---|---|---|
| Фронт (Next.js) | **Vercel Pro** | $20/мес (коммерция требует Pro; Hobby запрещён) |
| Auth + БД + Realtime + Storage/CDN | **Supabase Pro** | $25/мес (снимает 7-дневную паузу, бэкапы, 500 realtime-конн) |
| Тяжёлый воркер + лёгкий API | **Modal** (portable Docker-образ) | **$0** на старте ($30/мес free credits), растёт с трафиком |
| Очередь | **Встроена в Modal** (`spawn` + concurrency) | — (Redis НЕ нужен) |
| Медиа | Supabase Storage + CDN | в рамках Pro |

**Итого фикса: ~$45/мес на старте**, Modal $0 пока нет трафика → **влезает под <$50**.
Отдельно растут с использованием: Deepgram (~$0.0043/мин — **доминанта стоимости**) + Gemini.

**Почему Modal, а не Cloud Run/Fly/Render/Koyeb** (ресёрч 2026, источники §13):
- **Fly** — в 2026 умер free-tier + ручной автоскейлер + volume биллится остановленным → отпал.
- **Render** — always-on 2GB×2 ≈ $50-75/мес даже в простое → бьёт бюджет → отпал.
- **Railway** — платит за простой + серия аварий в 2026 → отпал.
- **Cloud Run** — отличен (нет лок-ина, free 100 vCPU-ч/мес, Cloud Run Jobs до 7 дней), но
  очередь = Cloud Tasks + IAM-обвязка = больше кода/настройки. **Близкий второй.**
- **Koyeb** — быстрейший cold-start (~250мс), нет лок-ина, но очередь строишь сам (Postgres/
  Celery) + меньше battle-tested. Третий.
- **Modal** — единственный, кто даёт **очередь + автоскейл + bounded-concurrency встроенными**
  (минимум инфры для соло-фаундера) + CPU cold-start <1с. Минус — лок-ин (средний), который
  **обезвреживаем** portable Docker-образом (см. §9).

---

## 1. Зафиксированные ограничения (входные данные дизайна)

1. **Масштаб:** реальные (возможно платящие) юзеры в ближайшие недели → прод-инфра, не игрушка.
2. **Бюджет:** <$50/мес на инфру (без Deepgram/Gemini — они usage-based).
3. **Ops:** push-and-forget. Готов переплатить за отсутствие админства. НЕ хочет VPS/SSH/compose.
4. **Латентность:** ~1-2 мин/ролик ок. Приоритет — не падать и не копить очередь под нагрузкой.
5. **Следствие:** GPU не нужен; пропускная способность (параллелизм/автоскейл) важнее скорости
   одного джоба; bursty-нагрузка → scale-to-zero выгоден.

---

## 2. Целевая архитектура

```
┌───────────────────────────── VERCEL PRO (Next.js) ─────────────────────────────┐
│  • Supabase Auth (getClaims — локальная верификация JWT, без сетевого хита)      │
│  • Читает СВОИ джобы ПРЯМО из Supabase (RLS) + Realtime-подписка (НЕ поллит!)    │
│  • Клипы грузятся с Supabase Storage CDN                                          │
│  • Зовёт Modal API ТОЛЬКО для: создать джоб, правки редактора, рендер, пресеты   │
└───────────┬─────────────────────────────────────────────────┬──────────────────┘
   создать/ │ правки (REST + Bearer JWT)        статус (push)  │ ▲ читать джобы/клипы
   рендер   ▼                                                  ▼ │
┌──────────────────────── MODAL (один репо, две роли) ──┐   ┌──────────────────────┐
│  ① API — лёгкий web-endpoint (БЕЗ torch, warm)        │   │  SUPABASE PRO         │
│    • POST /jobs → quota-check → INSERT row → spawn()   │──▶│  • Auth (RS256/JWKS)  │
│    • правки редактора (PURE ops на edit-state)         │   │  • Postgres: jobs,    │
│    • ASS-компиляция, пресеты, timeline, analysis       │◀──│    clip_edits,        │
│  ─────────────────────────────────────────────────    │   │    job_artifacts (RLS)│
│  ② WORKER — тяжёлая функция (Dockerfile-образ)         │──▶│  • Realtime (push)    │
│    • pipeline stage0-5 + рендер                        │   │  • Storage+CDN (mp4)  │
│    • bounded concurrency (max_containers)              │   │    (service_role)     │
│    • клипы → Storage, статус/cost/артефакты → Postgres │   └──────────────────────┘
│  ОЧЕРЕДЬ — встроена в Modal (spawn + concurrency). Нет Redis.                     │
└───────────────────────────────────────────────────────┘
```

**Границы компонентов (одна ответственность, тестируется отдельно):**

| Компонент | Ответственность | НЕ делает |
|---|---|---|
| **Frontend** (Vercel) | UI, auth, читает свои джобы/клипы из Supabase, Realtime-подписка | Не поллит воркер, нет тяжёлой логики |
| **Supabase** | Источник правды: auth + стейт джобов/правок/артефактов + Realtime + медиа-CDN | Не считает видео |
| **Modal API** (лёгкий образ, БЕЗ torch) | Создать джоб (enqueue), правки редактора (PURE), пресеты, ASS, timeline, analysis | Не крутит ffmpeg/torch |
| **Modal Worker** (тяжёлый Docker-образ) | Pipeline + рендер; пишет результат в Supabase | Не отвечает на запросы статуса (это Realtime) |

**Ключевой принцип:** тяжёлая работа НИКОГДА не в request-пути; клиент НИКОГДА не поллит воркер
(статус — Realtime push БД→клиент); медиа — через CDN. Это чинит «у кого-то грузится вечность»:
несколько ffmpeg-джобов больше не делят threadpool с лёгкими запросами и не блокируют статус/auth.

---

## 3. Потоки данных

### 3.1 Создать джоб (URL или upload)
1. Frontend → `POST /jobs` на Modal API (Bearer JWT + source).
2. API: верифицирует JWT (JWKS) → проверяет квоту (COUNT активных джобов юзера в Postgres) →
   `INSERT jobs(status=queued, user_id)` → `worker.spawn(job_id)` → возвращает `{id}`.
3. Frontend подписывается на свою строку через **Supabase Realtime** (`jobs:id=eq.<id>`).
4. Worker (по очереди Modal): `UPDATE status=downloading/transcribing/...` на границах стадий →
   каждый апдейт = Realtime push → UI обновляется живьём. По завершении: клипы → Storage,
   `job_artifacts` (transcript/segments/meta) → Postgres, `UPDATE jobs SET status=done, clips=…,
   cost=…`. Падение → `status=failed, error=…` (правило №8).
5. Frontend рендерит клипы с CDN-URL из строки.

### 3.2 Правка + ре-рендер (редактор)
1. Frontend → `GET /jobs/{id}/clips/{clip}/edit` (Modal API читает edit-state из Postgres; лениво
   создаёт дефолт из `job_artifacts`).
2. Правки → API-мутации (PURE ops на edit-state JSON; optimistic-lock через version; save в Postgres).
3. Рендер → `POST …/render` → API `worker.spawn(render_job)`. Worker ре-рендерит один клип из
   edit-state (нет Deepgram/Gemini → $0) → Storage → `UPDATE clip_edits SET render_url=…` →
   Realtime push.

### 3.3 Статус — Realtime вместо поллинга
- Realtime включён на таблице `jobs` (и `clip_edits` для render-статуса). Воркер делает UPDATE →
  Supabase бродкастит подписчику. **Воркер вообще не получает запросов статуса** (старый поллинг
  раз в 2.5с — главный источник нагрузки на воркер — исчезает).

---

## 4. Миграция стейта — инженерная часть

**Что НЕ меняется (нулевая зависимость от инфры — портируем как есть):** весь `pipeline/stage0-5`,
reframe v3 (`stage3_reframe`, `asd_reframe`, `reframe_cache`), `editor/*` (timemap, ops, captions_v2,
presets, defaults, chapters), `models.py`-контракты. Это сила архитектуры «pure + тонкая склейка».

**Что меняется:**

### 4.1 `db.py`: SQLite → Postgres
- Замена `sqlite3` на psycopg (через Supabase pooler-порт 6543 / pgBouncer — важно для множества
  коннектов из serverless) **или** supabase-py (service_role). Рекомендую psycopg к pooler.
- Pure-маппинг `row_to_wire` портируется почти как есть; **меняется только построение `video_url`**
  (см. неочевидное место C).
- `clips` → jsonb-колонка. `clip_edits.edit` → jsonb.
- Optimistic-lock `save_edit`: read-then-write → **атомарный** `UPDATE clip_edits SET edit=…,
  version=version+1 WHERE job_id=? AND clip_id=? AND version=? RETURNING version` (нет гонки).

### 4.2 `store.py`: локальный диск → Postgres/Storage  ← **центральная связка**
- `load_transcript_words`, `ensure_edit` читают `transcript.json`/`segments.json` **с диска**.
  → читать из `job_artifacts` (Postgres jsonb), т.к. лёгкий API и тяжёлый воркер на Modal — РАЗНЫЕ
  контейнеры без общего диска.
- `save_edit` пишет disk-mirror `edit.json` → **убрать** (Postgres = единственный источник правды).

### 4.3 `run.py` / `tasks.py`: эфемерный FS + явный persist
- `run_pipeline` пишет всё в `DATA_ROOT` (диск) и кэширует стадии **по наличию файла**.
  - within-job (одна инвокация, scratch `/tmp` или Modal-ephemeral) — ОК.
  - **cross-run + content-addressed transcript-кэш** (`_cache/transcripts`, бережёт Deepgram-деньги)
    → **Postgres-таблица `transcript_cache`** (durable, keyed by audio_sha; работает уже в Фазе A,
    до Modal, и не создаёт лок-ина). Иначе повторно платишь за транскрипцию.
    - (Опциональный reframe-analysis-кэш `out/analysis` — Modal Volume или просто пересчёт.)
- В конце склейки — **явный шаг persist**: клипы → Storage (upload), `job_artifacts`
  (transcript/segments/meta) + `jobs` (статус/cost/clips) → Postgres. Pure-стадии не трогаем.
- `runs.jsonl` (телеметрия экономики) → таблица `runs` в Postgres (или Storage-объект).

### 4.4 Медиа: `/media` StaticFiles → Supabase Storage + CDN
- Бакет `clips`, путь `clips/<job_id>/<clip_id>.mp4`. **Signed URL** (приватно, рекомендую) либо
  public-bucket с неугадываемыми путями (проще + CDN-кэш). URL пишется в строку джоба/клипа.
- Точки касания: `row_to_wire`, `get_render`, фронтовые `video_url ?? …`.

### Таблица «неочевидных мест» (свод)

| # | Место | Риск | Решение |
|---|---|---|---|
| A | `store.py` disk-reads + edit.json mirror | API-контейнер не видит файлы воркера | artifacts → Postgres; mirror убрать |
| B | `run.py` кэш по файлу + content-addr transcript-кэш | эфемерный FS → повторная оплата Deepgram | transcript-кэш → Postgres `transcript_cache` |
| C | `video_url = media/<job>/…` | локального пути нет в облаке | Storage CDN-URL |
| D | `run_pipeline` пишет в `DATA_ROOT` | scratch исчезает | явный upload+persist в конце |
| E | optimistic-lock read-then-write | гонка под конкуренцией | атомарный UPDATE … WHERE version=? |
| F | yt-dlp с DC-IP | YouTube блок | куки-файл (Modal Secret) + upload-fallback |

---

## 5. Схема БД (Supabase Postgres)

```sql
-- джобы (RLS по user_id; Realtime включён)
create table jobs (
  id text primary key,
  user_id uuid references auth.users not null,
  status text, stage text, progress int,
  source_type text, source_ref text, error text,
  clips jsonb, cost_usd numeric, duration_sec numeric, elapsed_sec numeric,
  created_at timestamptz default now(), updated_at timestamptz default now()
);
alter table jobs enable row level security;
create policy "own jobs" on jobs for select using (user_id = auth.uid());
-- INSERT/UPDATE — только service_role (воркер); фронт пишет джоб через Modal API, не напрямую.

-- правки клипов (optimistic-lock через version)
create table clip_edits (
  job_id text references jobs(id), clip_id text,
  version int, edit jsonb,
  render_status text, render_url text, render_error text,
  updated_at timestamptz default now(),
  primary key (job_id, clip_id)
);
alter table clip_edits enable row level security;
create policy "own edits" on clip_edits for select
  using (exists (select 1 from jobs j where j.id = job_id and j.user_id = auth.uid()));

-- артефакты пайплайна (читает лёгкий API; пишет воркер)
create table job_artifacts (
  job_id text primary key references jobs(id),
  meta jsonb, segments jsonb, transcript jsonb  -- transcript: если станет велик → Storage + ссылка
);
alter table job_artifacts enable row level security;
create policy "own artifacts" on job_artifacts for select
  using (exists (select 1 from jobs j where j.id = job_id and j.user_id = auth.uid()));

-- content-addressed transcript-кэш (общий, бережёт Deepgram; только service_role)
create table transcript_cache (
  audio_sha text, provider text, model text,
  transcript jsonb, created_at timestamptz default now(),
  primary key (audio_sha, provider, model)
);

-- телеметрия экономики (для /admin + маржи)
create table runs (
  run_id text, source_minutes numeric, stages jsonb,
  total_sec numeric, total_usd numeric, n_clips int,
  time_to_first_clip_sec numeric, created_at timestamptz default now()
);
```

> ⚠️ transcript для 90-мин видео может быть крупным (5446 слов ≈ сотни КБ; длиннее — больше).
> Postgres jsonb тянет, но если упрётся — `job_artifacts.transcript` → Storage-объект + ссылка.

---

## 6. Auth и изоляция

- **Supabase асимметричные signing keys (RS256/ES256):**
  - фронт: `getClaims()` — **локальная** верификация JWT (без сетевого хита Supabase);
  - воркер (`app/auth.py`): верификация через **JWKS** (`PyJWT` + `PyJWKClient`, кэш ключей).
    ⚠️ Это РАСХОДИТСЯ с auth-планом (там HS256 + shared secret) — переписать на JWKS.
- **CORS:** `allow_origin_regex=r"https://.*\.vercel\.app$"` (+ кастомный домен). НЕ wildcard в
  `allow_origins` (молча сломан в Starlette).
- **RLS** на `jobs`/`clip_edits`/`job_artifacts` (`user_id = auth.uid()` / join). Воркер — `service_role`
  (минует RLS). Фронт читает свои джобы напрямую (без round-trip к воркеру).
- **middleware** (Next): `getClaims()` (не `getUser()` — меньше латентности). ⚠️ остаёмся на Vercel
  именно потому, что cookie-auth-в-middleware ломается на Cloudflare Workers (Node-only `cookies()`).

---

## 7. Обработка ошибок, квоты, backpressure

- **Правило №8 (без тихих фолбэков):** падение джоба → `status=failed`+`error` в строке → Realtime →
  UI показывает причину. Твой `tasks.py` уже так устроен (try → set_failed) — портируем 1:1.
- **Per-user квоты** (анти-абьюз Deepgram-стоимости):
  - макс. 1-2 одновременных джоба / юзер;
  - дневной cap джобов / юзер;
  - макс. длина источника (минуты) по тарифу.
  Проверка в API **перед** `spawn` (COUNT в Postgres) → 429 + понятное сообщение при превышении.
- **Глобально:** Modal `max_containers` кап на воркере; лишние джобы ждут в очереди Modal.
- **UI:** статусы `queued/processing/done/failed`; при ожидании — «в очереди, ~N впереди»
  (COUNT queued-строк) + ETA. На масштабе джобы ЖДУТ — это норм, главное показать честно.

---

## 8. Стоимость (проверенные цифры 2026)

- **Modal CPU:** $0.0000131/core/сек ≈ **$0.047/core-час**; память $0.00000222/GiB/сек ≈
  $0.008/GiB-час; **$30/мес free credits** (Starter, без базовой платы).
- **Оценка джоба:** ~2 ядра × 75с + ~4 GiB × 75с ≈ $0.0026 компьюта; с запасом на torch/reframe
  → **~$0.005-0.01/джоб**.
- **На старте** (~2000 джобов/мес) → ~$10-20 → **в пределах free credits → $0 эффективно**.
- **Фикса:** Vercel Pro $20 + Supabase Pro $25 = **$45/мес**. Modal $0 пока нет трафика.
- **Usage (отдельно, растёт):** Deepgram ~$0.0043/мин = **доминанта**; Gemini ~$0.01-0.02/джоб.
  → масштаб компьюта = про латентность/параллелизм; деньги = про Deepgram → отсюда квоты на юзера
  и content-addressed transcript-кэш (бережёт повторы).

---

## 9. Риски и митигации

| Риск | Вероятность | Митигация |
|---|---|---|
| **yt-dlp с DC-IP блок** YouTube («not a bot») | Высокая | Куки-файл через Modal Secret; **upload-путь как первичный/fallback** (уже есть `/jobs/upload`); прокси для YT-пути (Фаза C, если нужно) |
| **Modal лок-ин** | Средняя | Воркер = **обычный Dockerfile-образ** (`Image.from_dockerfile`) → контейнер портируемый; Modal-специфичен только ~200-400 строк клея (spawn/queue/web-endpoint). Уход → ТОТ ЖЕ образ в Cloud Run + переписать клей = **дни** |
| **Cold-start редактора** | Низкая | API-образ БЕЗ torch → CPU cold-start <1с; держать 1 warm-контейнер (копейки) |
| **Supabase free-пауза / лимиты** | — | Pro $25 снимает паузу; 500 realtime-конн хватает на 100 юзеров |
| **transcript jsonb раздувается** | Низкая | Escape-hatch: transcript → Storage-объект + ссылка |
| **Рост Modal-стоимости при трафике** | — | Растёт ТОЛЬКО с реальным трафиком (есть выручка); квоты + кэш сдерживают |
| **Длинный джоб > таймаута функции** | Низкая | Modal function timeout конфигурируем; 90-мин лимит источника уже в `stage0` |

---

## 10. Фазовый роадмап (каждая фаза — отдельный под-план + DoD)

### Фаза A — Стейт в облако (БЕЗ смены платформы)
Мигрируем слой данных, пока воркер ещё **локальный и отлаживаемый** (не смешиваем миграцию данных
и платформы).
- A1. Supabase: проект Pro, асимметричные ключи, таблицы §5 + RLS-политики.
- A2. `db.py` → Postgres (psycopg к pooler-порту 6543). Порт `row_to_wire`.
- A3. `store.py` → читать artifacts из `job_artifacts`; убрать disk-mirror.
- A4. `run.py`/`tasks.py` → шаг persist (артефакты+статус в Postgres); transcript-кэш → Postgres
  `transcript_cache` (durable, бережёт Deepgram на повторах).
- A5. Медиа → Supabase Storage upload + CDN-URL.
- A6. `app/auth.py` → JWKS; фронт `getClaims()`; CORS regex.
- A7. Фронт: читать джобы из Supabase; Bearer JWT на вызовах Modal API.
- **DoD A:** локальный прогон воркера → строки в Supabase Postgres + клипы в Storage + фронт
  показывает джоб/клипы из Supabase. RLS: чужой юзер не видит. `just check` зелёный.

### Фаза B — Modal (платформа)
- B1. **Dockerfile** воркера (ffmpeg, torch CPU-колёса, mediapipe, scenedetect, yt-dlp) — multi-stage,
  кэш слоёв; модели (.tflite/ASD) в образ или Modal Volume.
- B2. Modal-приложение: ① лёгкий API (`@modal.asgi_app`, образ без torch, warm) + ② тяжёлый worker
  (`@app.function(image=dockerfile_image, max_containers=N)`).
- B3. `POST /jobs` → `worker.spawn`; bounded concurrency. (transcript-кэш уже в Postgres из Фазы A;
  Modal Volume — опц. под reframe-analysis-кэш / модели.)
- B4. Modal Secrets (Supabase service_role, Deepgram, Gemini, JWT/JWKS, yt-dlp cookies).
- B5. Vercel Pro деплой; `NEXT_PUBLIC_WORKER_URL` → Modal endpoint; env-vars.
- **DoD B:** реальный джоб через прод-URL (Vercel→Modal→Supabase), 3 клипа с CDN, без поллинга
  воркера, без локальной машины.

### Фаза C — Realtime + квоты + полиш
- C1. Поллинг → **Supabase Realtime**-подписка на свою jobs-строку.
- C2. Per-user квоты (параллелизм/дневной cap/длина) + 429-обработка в UI.
- C3. Queue-position + ETA в UI; backpressure при полной очереди.
- C4. `/admin` аналитика (поверх `runs`/`jobs`-агрегатов) + cost-трекинг.
- C5. yt-dlp прокси, если DC-IP блок мешает.
- **DoD C:** 0 запросов поллинга к воркеру (всё через Realtime); квоты срабатывают; /admin
  показывает юзеров/джобы/траты.

---

## 11. Что НЕ меняется (переиспользуем как есть)
- Чистый пайплайн `stage0-5`, reframe v3, editor (`app/editor/*`), `models.py`-контракты.
- Выбор моментов (Gemini), субтитры/караоке-анимации, пресеты, главы (chapters).
- Фронт-редактор (`/edit/[jobId]/[clipId]`), libass-превью (canvas-режим).
- Content-addressed transcript-кэш (логика; меняется только место хранения → Postgres `transcript_cache`).
- Дисциплина `just check`, TDD на pure-логике, conventional commits, codegen типов из `models.py`.

---

## 12. Открытые вопросы (решить при планировании/исполнении)
- Storage: signed URLs (приватно, безопаснее) vs public-bucket (проще + CDN-кэш) — выбрать.
- Postgres-доступ из воркера: psycopg к pooler (6543) vs supabase-py (service_role) — рекоменд. psycopg.
- transcript в Postgres jsonb vs Storage — старт jsonb, escape-hatch Storage если раздуется.
- Modal: где модели (.tflite/ASD) — в образе (просто, портируемо) vs Volume (меньше образ) — рекоменд. в образе.
- yt-dlp куки: чьи и как обновлять (протухают) — отдельный процесс; upload-путь снижает зависимость.
- Точные значения квот (макс. джобов/день, макс. минут источника) по тарифу — продуктовое решение.
- Кастомный домен (когда будет) → добавить в CORS regex + Supabase redirect URLs.

---

## 13. Источники (ресёрч 2026)
- Modal pricing (CPU $0.0000131/core/сек, $30/мес credits, web-endpoints, distributed queue):
  https://modal.com/pricing ; cold-start CPU <1с: https://modal.com/docs/guide/cold-start
- Vercel Hobby = non-commercial, Pro $20 для коммерции: https://vercel.com/docs/limits/fair-use-guidelines ;
  https://vercel.com/pricing
- Supabase free-пауза 7д + Pro $25 (8GB DB/100GB Storage/500 realtime): https://supabase.com/pricing
- Cloud Run free (360K vCPU-сек/мес, 2M req) + Jobs до 7д: https://cloud.google.com/run/pricing ;
  https://docs.cloud.google.com/run/docs/configuring/task-timeout
- Fly free-tier died / autostop-autostart: https://fly.io/pricing/ ; https://fly.io/docs/launch/autostop-autostart/
- Koyeb scale-to-zero ~250мс / Railway charges idle + 2026 outages: https://www.koyeb.com/pricing ;
  https://docs.railway.com/reference/pricing/plans
- Cloudflare Next 16 OpenNext middleware `cookies()` Node-only gotcha: https://opennext.js.org/cloudflare ;
  https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/

---

## 14. Ссылки (внутренние)
- Предыдущий инфра-дизайн (платформа была открыта): `2026-06-13-infra-scaling-cloud-worker.md`
- Auth-логика (валидна; деплой/HS256 устарели → JWKS): `2026-06-13-auth-analytics-plan.md`
- K1 RQ-очередь (НЕ нужна при Modal — встроенная очередь): `2026-06-07-phase1-reliability-design.md`
