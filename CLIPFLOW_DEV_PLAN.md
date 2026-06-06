# ClipFlow — План разработки Phase 0 «THIN PIPELINE»

## TL;DR

Строим **тонкий, но корректный сквозной пайплайн**, который за несколько дней доказывает одно: **нарезка реально хорошая**. Поток: source (YouTube via yt-dlp ИЛИ upload) → word-level транскрипция → LLM выбирает моменты со структурой `{start,end,reason,score,type}` → 9:16 reframe для одного спикера → прожжённые субтитры из word-timestamps → FFmpeg cut/encode → скачиваемый MP4. UI минимальный — инструмент контроля качества для самого фаундера, не «продукт». «Магия» (transcript-trim редактор, why-panel, fly-out) отложена. Метрика выхода: `Q = (usable+fixable)/total ≥ 60%` при `cost ≤ $2/видео` и `time-to-first-clip ≤ 5 мин`. Не проходим gate — не строим Phase 1, а крутим конкретный «винтик» (промпт → модель → провайдер → ICP) или разворачиваемся.

---

## 1. Зафиксированные решения (не релитигируем)

- **Milestone = тонкий пайплайн.** Цель Phase 0 — валидация КАЧЕСТВА нарезки, а не фичи/полировка. Сначала надёжный резак + плоский список клипов + экспорт.
- **Build mode = соло-фаундер + AI-агент.** План — это исполняемый сверху-вниз чеклист: крошечные задачи, точные команды, точные пути, «Готово когда» (DoD) на каждом шаге, частые стоп-гейты.
- **Infra = managed + serverless.** Транскрипция через Deepgram/AssemblyAI (word-level обязателен), LLM через Anthropic Claude (structured output, swappable), рендер FFmpeg, async на Railway (Phase 0) → Modal позже, storage Cloudflare R2 (подключаем после валидации). Чистый путь на self-host (WhisperX + MediaPipe) ради маржи — позже.
- **Магия потом.** Interactive transcript-trim, «why these not others», fly-out cards, clip↔source linkage — Phase 2. Но **word-level timestamps держим уже сейчас** (фундамент под trim).
- **Новый репозиторий `clipflow` (монорепо).** `apps/web` + `services/worker` + `packages/shared`. Лендинг `Varenik-vkusny/Shorts-Automatizator` (Vercel `shorts-automatizator`) **не трогаем вообще**.
- **Экономика с дня 1.** Cost/latency пишем по стадиям в `runs.jsonl`/`job.json`. `time-to-first-clip` — первоклассная метрика.

### Разрешённые конфликты между секциями (решения архитектора)

| Конфликт в драфтах | Решение |
|---|---|
| Имя/место репо: `clipflow` (монорепо на Desktop) vs `clipflow-app` (отдельный, web-only) | **`clipflow` монорепо**, корень `C:\Users\user\Desktop\clipflow\`. Один источник правды контрактов. |
| Транскрипция MVP: Deepgram vs AssemblyAI | **Deepgram Nova по умолчанию** (быстрее/дешевле для скорости итерации), AssemblyAI — swap через тот же интерфейс. Обе дают word-level. |
| Reframe Phase 0: MediaPipe-трекинг vs статичный center-crop | **MediaPipe face-detect → ОДИН static crop на сегмент** (усреднённый центр лица, dead-zone). Center-crop — fallback при отсутствии лица. Per-frame панорамирование — позже. |
| Субтитры: ASS vs drawtext | **ASS** (полный контроль стиля, путь к brand-шаблонам, нет ада escaping). |
| Хранилище Phase 0: local-fs vs R2 сразу | **Local-fs `data/<job_id>/`** на этапе валидации качества (скорость итерации). R2 — одной заменой `storage.py` после прохождения GO-gate. Интерфейс `put/get/url` изолируем сразу. |
| Web↔worker: прямой fetch из браузера vs прокси через Next route handlers | **Phase 0: прямой fetch** браузер→worker (нет БД/auth, нужен только CORS). Server-side прокси с `X-API-Key` — когда появятся секреты/Stripe (Phase 3). |
| Оркестрация: BackgroundTasks+SQLite vs CLI `run.py` | **Оба, на двух стадиях.** Сначала `run.py` (CLI, локально, склеивает стадии — это и есть валидация качества). Затем оборачиваем в FastAPI `POST /jobs` + SQLite + polling для web. |
| Python-менеджер: uv vs poetry | **uv** (скорость, ставит Python+venv+deps одной командой, детерминированный lock). |
| Оркестратор команд: justfile vs Makefile vs npm scripts | **justfile** (кроссплатформенный; `make` на Windows нет). На Windows `just web`/`just worker` в двух терминалах. |

---

## 2. Стек

| Слой | Выбор (Phase 0) | Зачем | Чем заменим позже |
|---|---|---|---|
| Web | Next.js (App Router) + React + Tailwind | Тонкий UI: ввод → статус → грид клипов → download | + Remotion Player для preview/рендера (Phase 2) |
| Worker/pipeline | FastAPI (Python 3.12) | ML-экосистема Python; pure-функции стадий | Celery+Redis при >1 worker/ретраях (Phase 1) |
| Import | yt-dlp + file upload | YouTube + локальный файл; upload — всегда-доступный путь | — |
| Транскрипция | **Deepgram Nova** (word-level) | Быстрее/дешевле (~$0.26/час), word start/end/confidence из коробки | AssemblyAI (swap); self-host WhisperX (forced alignment) ради маржи |
| Moment selection | **Anthropic `claude-opus-4-8`**, structured output | Лучшее качество отбора на этапе валидации; 1M контекст (часовой транскрипт целиком) | A/B → `claude-haiku-4-5` ($1/$5) для прода/объёма; swap на GPT-4o/Gemini через `LLM_MODEL` |
| Reframe 9:16 | MediaPipe Face Detection (CPU) + static crop | Дёшево (2 fps sample), чисто для говорящей головы | Kalman/optical-flow трекинг; Pyannote-диаризация для 2+ спикеров (Phase 4) |
| Субтитры | ASS subtitle + FFmpeg `subtitles=` | Полный контроль стиля, путь к brand-шаблонам | Караоке-подсветка `{\k}`, brand-templates (Phase 1/2) |
| Cut/encode | FFmpeg (libx264, CRF 20) | Стандарт, дёшево на CPU | Remotion render (Phase 2) |
| Storage | Local-fs `data/<job_id>/` | Скорость итерации при валидации | Cloudflare R2 (дешёвый egress), presigned URLs |
| БД/состояние | SQLite (`jobs.db`) | 0 инфраструктуры, переживает рестарт | Supabase Postgres при auth/оплате/multi-worker |
| Web hosting | Vercel (новый проект `clipflow-web`, root `apps/web`) | — | — |
| Worker hosting | Railway (persistent volume для `jobs.db`/`tmp`) | Долгоживущий REST + SQLite без cold-start | Modal + GPU при self-host WhisperX/MediaPipe |
| Auth/оплата | нет (Phase 0) | Не нужно для валидации | Supabase Auth + Stripe (Phase 3, per-video pricing) |

---

## 3. Архитектура Phase 0

### Поток стадий (data contract = файлы в `data/<job_id>/` + растущий `job.json`)

```
[0 Import]   URL|upload ──► source.mp4, source.wav (16k mono), meta.json
                 │
[1 Transcribe]   source.wav ──► transcript.json   (= Transcript, word-level, seconds)
                 │
[2 Select]       transcript.json ──► segments.json (= list[Segment], {start,end,reason,score,type})
                 │
[3 Reframe]      source.mp4 + segment ──► crop_<clip_id>.json (= list[CropWindow], 1 static window/clip)
                 │
[4 Captions]     transcript.json + segment ──► captions_<clip_id>.ass (times rel. to clip)
                 │
[5 Render]       всё выше ──► clips/<clip_id>.mp4 + обновлённый job.json (cost/latency)
```

Каждая стадия пишет файл → идемпотентность и перезапуск любой стадии отдельно (критично для отладки качества). `run.py` склеивает стадии локально; `tasks.py` оборачивает тот же pipeline в FastAPI BackgroundTask.

### Файловое дерево репозитория

```
clipflow/                                   # C:\Users\user\Desktop\clipflow\
├─ .gitignore  .editorconfig  README.md  justfile  .env.example
├─ pnpm-workspace.yaml  package.json
├─ apps/
│  └─ web/                                  # Next.js → Vercel (root dir = apps/web)
│     ├─ package.json  next.config.mjs  tailwind.config.ts  tsconfig.json
│     ├─ .env.local.example                 # NEXT_PUBLIC_WORKER_URL
│     ├─ app/
│     │  ├─ layout.tsx                       # шрифты Unbounded/Onest/IBM Plex Mono
│     │  ├─ page.tsx                         # ЕДИНСТВЕННАЯ страница: state-машина
│     │  └─ globals.css                      # Tailwind + :root токены (копия лендинга)
│     ├─ components/                         # SourceForm, JobProgress, ClipGrid, ClipCard,
│     │                                      # ReasonChip, StatusBadge, ErrorPanel, Studio
│     └─ lib/                                # types.ts, api.ts, useJob.ts, format.ts
│
├─ services/
│  └─ worker/                               # FastAPI + pipeline → Railway
│     ├─ pyproject.toml  uv.lock  Dockerfile  Makefile
│     ├─ .env.example
│     ├─ app/
│     │  ├─ main.py                          # FastAPI: POST /jobs, GET /jobs/{id}, GET /healthz
│     │  ├─ config.py                        # pydantic-settings (fail-fast на старте)
│     │  ├─ deps.py                          # (Phase 1) auth dependency
│     │  ├─ models.py                        # pydantic контракты — ЕДИНЫЙ ИСТОЧНИК ТИПОВ
│     │  ├─ export_schema.py                 # models.py → packages/shared/contract.json (codegen)
│     │  ├─ db.py                            # SQLite init/insert/get/update
│     │  ├─ storage.py                       # local (Phase 0) → R2 later (интерфейс put/get/url)
│     │  ├─ tasks.py                         # run_pipeline(job_id) — оркестрация + статус в БД
│     │  ├─ run.py                           # CLI entrypoint (валидация качества)
│     │  └─ pipeline/
│     │     ├─ stage0_import.py              # yt-dlp / upload / ffprobe
│     │     ├─ stage1_transcribe.py          # Deepgram → Transcript (swap AssemblyAI)
│     │     ├─ stage2_select.py              # Claude → list[Segment] + post-process
│     │     ├─ stage3_reframe.py             # MediaPipe → CropWindow (PURE math изолирована)
│     │     ├─ stage4_captions.py            # word grouping → .ass (PURE)
│     │     └─ stage5_render.py              # FFmpeg cut+crop+burn+encode
│     ├─ tests/
│     │  ├─ unit/                            # PURE функции: captions, crop math, segment validation
│     │  └─ fixtures/                        # golden JSON (видео в git НЕ коммитим)
│     ├─ data/                               # local артефакты Phase 0 (gitignored)
│     └─ tmp/                                # ephemeral (gitignored)
│
└─ packages/
   └─ shared/                               # контракт web↔worker — ГЕНЕРИРУЕТСЯ из models.py
      ├─ package.json                        # dev-dep: json-schema-to-typescript
      ├─ contract.json                       # JSON Schema (codegen из Pydantic) — НЕ править руками
      └─ src/types.ts                        # TS-типы (codegen из contract.json) — НЕ править руками
```

**Принцип границ:** `pipeline/*` — чистые функции (вход→выход, без HTTP/DB). `tasks.py` — единственное место склейки + запись статуса. Это даёт лёгкое тестирование и чистый путь к Celery (Phase 1).

---

## 4. Контракты данных

### 4.1 Нормализованный транскрипт + сегменты (`services/worker/app/models.py` — источник правды)

```python
from enum import Enum
from pydantic import BaseModel, Field

class Word(BaseModel):
    text: str                       # already punctuated/capitalized (for captions)
    start: float                    # seconds, float, absolute in source
    end: float                      # seconds
    confidence: float | None = None

class Transcript(BaseModel):
    language: str
    duration: float                 # source duration, seconds
    words: list[Word]               # word-level, sorted by start — backbone of everything

class ClipType(str, Enum):
    hook = "hook"
    emotional_peak = "emotional_peak"
    complete_thought = "complete_thought"
    strong_quote = "strong_quote"

class Segment(BaseModel):
    start: float                    # snapped to word boundary, seconds
    end: float                      # snapped to word boundary, seconds
    reason: str                     # WHY chosen (explainability), 1-2 sentences, concrete
    score: float = Field(ge=0, le=1)
    type: ClipType

class CropWindow(BaseModel):
    t: float                        # timestamp (s) at which this window applies
    x: int; y: int                  # top-left in SOURCE pixel coords
    w: int; h: int                  # crop size in source px (9:16)

class Clip(BaseModel):
    id: str
    segment: Segment
    crop: list[CropWindow]          # Phase 0: 1 static window
    captions_ass_path: str
    output_path: str                # final 9:16 mp4
    cost_usd: float
    latency_s: float
```

**Инварианты:** все времена в **секундах (float)**, абсолютные от начала source; `words` отсортированы по `start`; Deepgram отдаёт секунды, AssemblyAI — миллисекунды → нормализуем в секунды на входе провайдера.

### 4.2 JSON-схема ответа LLM по моментам (`output_config.format`, strict)

Модель возвращает **индексы слов**, не секунды (снимает класс ошибок «придуманный таймкод»). Точные секунды берём детерминированно: `start = words[start_word_index].start`, `end = words[end_word_index].end`.

```json
{
  "type": "object",
  "properties": {
    "segments": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "start_word_index": { "type": "integer" },
          "end_word_index":   { "type": "integer" },
          "reason": { "type": "string" },
          "score":  { "type": "number" },
          "type":   { "type": "string", "enum": ["hook","emotional_peak","complete_thought","strong_quote"] }
        },
        "required": ["start_word_index","end_word_index","reason","score","type"],
        "additionalProperties": false
      }
    }
  },
  "required": ["segments"],
  "additionalProperties": false
}
```

> JSON Schema structured outputs **не поддерживает** `minimum/maximum` → диапазон `score ∈ [0,1]` валидируем/клипуем в пост-обработке, не в схеме.

### 4.3 API web↔worker (источник правды — `packages/shared`)

Enums (общие на web и worker):
```ts
type JobStatus = "queued"|"downloading"|"transcribing"|"selecting"|"rendering"|"done"|"failed";
type ClipType  = "hook"|"emotional_peak"|"complete_thought"|"strong_quote";
```

Endpoints:

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| POST | `/jobs` | `{"source_type":"youtube","source_ref":"<url>"}` ИЛИ `multipart` с `file` | `202 {"id","status":"queued","stage":"queued","progress":0}` |
| GET | `/jobs/{id}` | — | `200 Job` (polling каждые 2.5s, пока статус не done/failed) |
| GET | `/healthz` | — (без auth) | `200 {"ok":true,"version":"0.1.0"}` |

`Job` (готово):
```json
{
  "id":"...", "status":"done", "stage":"done", "progress":100,
  "source_kind":"youtube", "error":null,
  "clips":[{
    "id":"clip_01","start":124.5,"end":152.8,"duration":28.3,
    "reason":"strong_quote","type":"strong_quote","score":0.91,
    "video_url":"http://.../clips/clip_01.mp4",
    "thumbnail_url":null,
    "transcript":"...snippet...",
    "words":[{"text":"So","start":124.5,"end":124.7}]
  }],
  "metrics":{"cost_usd":0.58,"duration_sec":750.0,"elapsed_sec":142.3}
}
```

**Правила:** один способ узнать прогресс — polling (SSE/WS → Phase 1, progressive output). `clip.words[]` присутствует уже в Phase 0 (фундамент под trim-редактор), UI его игнорирует. `clip.start/end` — в координатах исходника (фундамент под clip↔source linkage). **CORS:** worker отдаёт `Access-Control-Allow-Origin` для домена web (`http://localhost:3000` dev, prod-домен later) — иначе CORS-стена на первом запросе.

---

## 4А. Инженерная дисциплина (скорость = меньше мест, где можно ошибиться)

Цель раздела — прямо ответить на «чтобы не менять одно и то же в нескольких местах, всё на тестах, всё документировано, без тупых багов». Это **обязательные правила**, на которые ссылается каждый шаг чеклиста.

### A. Единый тип — через codegen, а не «следить руками»
- **Один источник правды: Pydantic-модели `services/worker/app/models.py`** (Transcript, Word, Segment, Clip, Job + все enums). Больше типы не дублируются нигде.
- **TypeScript НЕ пишем руками.** Цепочка codegen:
  `models.py → export_schema.py → packages/shared/contract.json (JSON Schema) → json-schema-to-typescript → packages/shared/src/types.ts`.
- Рецепт `just types`:
  ```bash
  cd services/worker && uv run python -m app.export_schema      # → ../../packages/shared/contract.json
  cd packages/shared && pnpm json2ts -i contract.json -o src/types.ts
  ```
- **Anti-drift гейт** в `just check`: `just types && git diff --exit-code packages/shared`. Поменял модель, забыл типы — билд красный. Рассинхрон физически нельзя протащить.
- Web импортирует **только** `@clipflow/shared`; worker валидирует вход/выход **теми же** Pydantic-моделями. Один источник → обе стороны.

### B. Тест-первый (TDD) — обязателен на багоопасных местах
Не «тесты когда-нибудь», а red→green→refactor там, где баги дорогие и тихие:
- **Тест ДО кода (pure, детерминированное):** пересчёт `t_clip = t_source − segment.start`; группировка слов в субтитры; математика 9:16 crop-окна; клип/валидация `score`; разрешение пересечений сегментов; маппинг офсетов LLM→таймкоды.
- **Golden snapshot на стадию:** фиксируем `transcript.json`/`segments.json` на эталонном сэмпле, тест сверяет инварианты (нет overlap, 15 ≤ len ≤ 60, end > start, words внутри клипа). JSON коммитим, видео — нет.
- **Контрактные тесты:** Pydantic-валидация реального ответа Deepgram/Claude на фикстуре — ловит смену формата API до прода.
- **Не юнит-тестим** визуальное качество reframe/субтитров — это глазами по рубрике (раздел 7). Сеть — мокаем на фикстурах.
- Рецепты: `just test-unit` (быстро, без сети), `just e2e` (один реальный сэмпл). **DoD шага с кодом = его тест написан первым и зелёный.**

### C. Статическая типизация и линт — везде, в одном гейте
- Python: `ruff` + **`mypy --strict`** на `app/`. TS: `"strict": true` + eslint.
- **`just check` = lint + типы (`mypy` + `tsc --noEmit`) + `test-unit` + anti-drift.** Ничего не коммитим, пока не зелёный.
- **pre-commit** автоматизирует это: `.pre-commit-config.yaml` (ruff, ruff-format + локальный hook `just check`), `pre-commit install` в Этапе A.

### D. Документация — встроенная, не отдельная задача
- **Docstring на каждой публичной функции** (что делает / вход / выход / что кидает), особенно pure-функции пайплайна. Каждый `stageN_*.py` начинается docstring-ом: «вход-файл(ы) → выход-файл, инварианты».
- **README.md в каждом пакете** (`apps/web`, `services/worker`, `packages/shared`): зачем, как запустить, ключевые файлы.
- **ADR** на значимые решения: `docs/adr/NNNN-title.md` (контекст → решение → последствия). Первые: Deepgram vs AssemblyAI, static-crop vs трекинг, codegen-контракт.
- `contract.json` — машиночитаемая канон-документация API; `CHANGELOG.md` ведём с Phase 0.

### E. Ошибки явные — без тихих провалов
- Никаких `except: pass`. Ловим конкретное, логируем, кидаем `JobError(stage, reason)`; статус job → `failed` + `error`.
- `config.py` (pydantic-settings) роняет старт при отсутствии ключа (fail-fast). Каждая стадия проверяет, что её входной файл существует и валиден (Pydantic), до работы.

### F. DRY и границы (повтор главного)
- Логика — в одном месте: контракты в `models.py`; тайминги/crop/captions — каждое в **одной** pure-функции, переиспользуемой и в `run.py`, и в `tasks.py`.
- `pipeline/*` чистые (вход→выход, без HTTP/DB); склейка только в `tasks.py`/`run.py` → тривиальное тестирование и чистый путь к Celery.

---

## 5. Phase 0 — пошаговый чеклист

> Все команды — **PowerShell на Windows** (среда фаундера), отличия для bash помечены. Абсолютные пути от `C:\Users\user\Desktop\clipflow\`. **Жёсткое правило агента:** не переходить к следующему шагу, пока DoD текущего не зелёный и его вывод не показан. После каждого зелёного гейта — маленький conventional-commit. Если DoD не сходится 2 раза подряд — СТОП, эскалация человеку, не «творить наугад». **Каждый шаг с кодом подчиняется разделу 4А: тест пишем первым на pure-логике, `just check` зелёный до коммита, типы только через codegen.**

### Этап A — Бутстрап репо и тулинг

**A1. Установить недостающие бинарники.** На машине НЕТ `ffmpeg`, `uv`, `just` (проверено) — иначе агент упадёт на E2E.
```powershell
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
winget install --id Casey.Just -e --accept-source-agreements --accept-package-agreements
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# перезапустить терминал (обновить PATH)
```
**Готово когда:** `ffmpeg -version`, `uv --version`, `just --version` печатают версии. Fallback при отсутствии winget: FFmpeg zip с gyan.dev + добавить `bin` в PATH; `just` через scoop.

**A2. Создать новый репо `clipflow`, лендинг не трогать.**
```powershell
cd C:\Users\user\Desktop
mkdir clipflow; cd clipflow
git init -b main
gh repo create Varenik-vkusny/clipflow --private --source . --remote origin
```
**Готово когда:** существует приватный `clipflow`; `gh repo view Varenik-vkusny/Shorts-Automatizator --json pushedAt -q .pushedAt` НЕ изменился относительно начала.

**A3. Создать `.gitignore` + структуру каталогов.** `.gitignore` блокирует `node_modules/`, `.next/`, `.venv/`, `__pycache__/`, `.env`, `.env.local`, `*.db`, `services/worker/data/`, `services/worker/tmp/`, и видео-фикстуры `tests/fixtures/**/*.{mp4,mkv,webm}` (golden JSON коммитим, видео — нет).
```powershell
mkdir apps,packages\shared\src,services\worker\app\pipeline -Force
mkdir services\worker	ests\unit,services\worker	ests\fixtures,services\worker\data -Force
```
**Готово когда:** дерево из §3 создано; `git status` чистый после первого коммита.

**A4. Init `apps/web` (Next.js + Tailwind).**
```powershell
cd C:\Users\user\Desktop\clipflow
pnpm create next-app@latest apps/web --ts --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-pnpm --no-turbopack
```
Создать `pnpm-workspace.yaml` (`packages: ["apps/*","packages/*"]`) и корневой `package.json` со скриптами `dev:web`, `lint:web`, `format`.
**Готово когда:** `pnpm --filter web dev` поднимает `http://localhost:3000`, дефолтная страница рендерится.

**A5. Init `services/worker` (FastAPI + uv).**
```powershell
cd C:\Users\user\Desktop\clipflow\services\worker
uv init --package --name clipflow-worker --python 3.12
uv add fastapi "uvicorn[standard]" pydantic pydantic-settings httpx anthropic deepgram-sdk yt-dlp mediapipe opencv-python-headless numpy
uv add --dev ruff mypy pytest pytest-asyncio pre-commit
```
Минимальный `app/main.py` с `GET /healthz` → `{"ok":true,"version":"0.1.0"}`. Добавить в `pyproject.toml` блок `[tool.ruff]` (`line-length=100`, `select=["E","F","I","UP","B","ASYNC"]`).
**Готово когда:** `uv run uvicorn app.main:app --reload --port 8000` поднимается, `curl http://localhost:8000/healthz` → `{"ok":true,...}`. **STOP-GATE: web (3000) и worker (8000) оба отвечают.**

**A6. `justfile` + `models.py` (единственный источник типов) + codegen контракта.** Написать `app/models.py` (§4.1, Pydantic — ИСТОЧНИК ПРАВДЫ) и `app/export_schema.py` (Pydantic → `packages/shared/contract.json`). В `packages/shared`: `pnpm add -D json-schema-to-typescript`. justfile с рецептами `install`, `web`, `worker`, `lint`, `format`, `types`, `test-unit`, `e2e`, `check` (детали по типам/тестам/линту — **раздел 4А**). `just types` генерит `contract.json` + `src/types.ts` (TS руками не пишем). Настроить `mypy --strict` (worker) и `tsconfig "strict": true` (web); `pre-commit install`.
**Готово когда:** `just --list` показывает рецепты; `just types` генерит файлы и `git diff --exit-code packages/shared` чистый (anti-drift); `just check` зелёный (lint + mypy + `tsc --noEmit` + test-unit + anti-drift); `pre-commit run -a` проходит.

### Этап B — Import (Stage 0)

**B1. yt-dlp скачивание (точные флаги).**
```bash
yt-dlp -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b" \
  --merge-output-format mp4 --no-playlist --max-filesize 2G \
  --write-info-json --restrict-filenames \
  -o "data/<job_id>/source.%(ext)s" "<YOUTUBE_URL>"
```
1080p потолок (для 9:16 шортов выше не нужно, экономит время/диск); `--restrict-filenames` спасёт от escaping в FFmpeg позже.

**B2. Извлечь аудио 16k mono WAV + ffprobe meta.**
```bash
ffmpeg -y -i "data/<job_id>/source.mp4" -vn -ac 1 -ar 16000 -c:a pcm_s16le "data/<job_id>/source.wav"
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,duration -of json "data/<job_id>/source.mp4"
```
Upload-путь: пользователь кладёт файл в `data/<job_id>/source.mp4`; если контейнер не mp4 → `ffmpeg -y -i source.<ext> -c copy source.mp4` (фолбэк `-c:v libx264 -c:a aac`). `stage0_import.py` пишет `meta.json` (`{job_id,source,url,title,duration,fps,width,height}`). Лимиты: ≤90 мин, ≤2 ГБ, один спикер.
**Готово когда:** есть `source.mp4` (играется), `source.wav` (`ffprobe` → `sample_rate=16000, channels=1`), `meta.json` с ненулевым `duration` и корректными `width/height/fps`. Залогированы байты и время скачивания. Cost $0.

### Этап C — Транскрипция (Stage 1)

**C1. Запрос к Deepgram (`stage1_transcribe.py`).** Функция `transcribe(wav_path) -> Transcript` с провайдерами `DeepgramProvider`/`AssemblyAIProvider` (swap не меняет downstream). Параметры Deepgram: `model="nova-3"`, `smart_format=true`, `punctuate=true`, `language="en"`, `diarize=false`. `word.text = punctuated_word`, времена в **секундах**.
> AssemblyAI отдаёт мс → делить на 1000. Единая единица внутри `Transcript` — секунды.

**Готово когда:** `transcript.json` существует; `len(words)>0`; `words[0].start>=0`; `words[-1].end <= duration+0.5`; спот-чек: `start: 12.34` (секунды), не `12340`. Залогированы: число слов, стоимость (минуты × тариф), латентность. Cost ~$0.26/час, латентность ~30–60 с/час.

### Этап D — Выбор моментов (Stage 2) — ГЛАВНЫЙ GATE КАЧЕСТВА

**D1. Промпт + structured output (`stage2_select.py`).** Подаём модели **пронумерованный по словам транскрипт, сгруппированный в строки** (каждые ~8–12 слов строка начинается с `[<index_of_first_word>]`). System-промпт описывает 4 типа (hook/emotional_peak/complete_thought/strong_quote) + жёсткие правила (complete thought, 15–60 с, no overlap, конкретный `reason`, quality over quantity). System держим неизменным → `cache_control: {"type":"ephemeral"}`.

Вызов (параметры именно для Opus 4.8 — НЕ Sonnet 3.x):
```python
import anthropic, json
from app.models import Segment, Transcript

MODEL_ID = "claude-opus-4-8"   # из env LLM_MODEL; swap → claude-haiku-4-5 для прода

def select_segments(transcript: Transcript, title: str) -> list[Segment]:
    client = anthropic.Anthropic()
    indexed = build_indexed_transcript(transcript.words)
    resp = client.messages.create(
        model=MODEL_ID,
        max_tokens=16000,
        thinking={"type": "adaptive"},                 # adaptive ONLY на 4.8
        output_config={
            "effort": "high",                          # отбор intelligence-sensitive
            "format": {"type": "json_schema", "schema": SEGMENTS_SCHEMA},
        },
        system=[{"type":"text","text":SYSTEM_PROMPT,"cache_control":{"type":"ephemeral"}}],
        messages=[{"role":"user","content": build_user_prompt(title, transcript, indexed)}],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    raw = json.loads(text)["segments"]
    return postprocess(raw, transcript.words)
```

> **Жёсткие правила Opus 4.8 (иначе 400):** НЕ передавать `temperature`/`top_p`/`top_k` (удалены); НЕ передавать `budget_tokens` (удалён — только adaptive); НЕ использовать assistant-prefill (400 на 4.x — используем `output_config.format`). Thinking-блоки по умолчанию пустые (`display:"omitted"`) — нам их текст не нужен, оставляем дефолт. Prompt caching на Opus требует префикс ≥4096 токенов (system-промпт + few-shot должны дотягивать).

**D2. Пост-обработка (наш код, детерминированно) → `segments.json`:**
1. `start = words[i].start`, `end = words[j].end`.
2. **Снэп к границам предложений:** расширяем `end` до ближайшего слова на `.?!` (в пределах +5 слов), при необходимости двигаем `start` к началу предложения. Бесплатно улучшает clean-start/clean-end.
3. **Длительность-гейт:** отбрасываем `<15s` или `>60s` (грубый обрез ломает complete thought — отбрасываем, не режем).
4. **Анти-overlap:** сортируем по `score` убыв., жадно берём непересекающиеся.
5. `score` клипуем в [0,1]; `reason` тримим; `type` валидируем по enum.

**Готово когда:** `segments.json` существует; каждый сегмент 15s ≤ (end−start) ≤ 60s; нет пересечений (ассерт в коде); `reason` непустой и КОНКРЕТНЫЙ (спот-чек глазами на 1 видео — не «this is a good clip»); `type ∈ enum`; `score ∈ [0,1]`. Залогированы: кандидатов от модели, после гейтов, input/output токены, стоимость, латентность. Cost ~$0.13/прогон на Opus (~$0.025 на Haiku), латентность ~10–40 с.

### Этап E — Reframe 9:16 (Stage 3)

**E1. Детект лица + static crop (`stage3_reframe.py`).** Для каждого сегмента сэмплируем кадры с шагом **0.5 с** (2 fps, не каждый кадр), MediaPipe Face Detection (`model_selection=1`), берём bbox самого крупного лица. **Сглаживание + dead-zone**, затем **ОДИН static crop на сегмент** по усреднённому центру: `w = round(H*9/16)`, `h = H`, `x = clamp(cx*W - w/2, 0, W-w)`, `y = 0`. **Fallback** (нет лица на сегменте): center crop `cx=0.5`. PURE-математика расчёта окна изолирована для unit-тестов.
**Готово когда:** `crop_<clip_id>.json` существует; `0 ≤ x`, `x+w ≤ W`, `w/h ≈ 9/16` (±1px); при наличии лица центр кропа на лице (спот-чек: рамка на 1 кадр — лицо в кадре, не обрезано); без лица сработал fallback (`face_found=false` в логе). Cost $0, ~1–3 с/клип.

### Этап F — Субтитры (Stage 4)

**F1. Группировка слов + ASS (`stage4_captions.py`).** Чанки: макс **3–5 слов**; разрыв при паузе `>0.4 с`, на `.?!`, или `>2.5 с` длины. Тайминг чанка `[first_word.start, last_word.end]`. **Времена пересчитываем относительно начала клипа:** `t_clip = t_source - segment.start` (это единая точка ошибок «± длина клипа» — изолируем в PURE-функцию под unit-тест). Стиль — один дефолтный brand-neutral (`Montserrat 90` на `PlayResX/Y=1080/1920`, толстый чёрный контур `Outline=6`+тень, `Alignment=2`, `MarginV=260`, `.upper()`). Группировка слов — PURE-функция.
**Готово когда:** `captions_<clip_id>.ass` существует; первый `Dialogue` стартует с `0:00:00.xx` (тайминг от клипа, не source); чанки 3–5 слов; времена монотонны и не выходят за длину клипа. Cost $0, миллисекунды.

### Этап G — Cut + Encode (Stage 5)

**G1. Один проход FFmpeg на клип (`stage5_render.py`).**
```bash
ffmpeg -y -ss <segment.start> -to <segment.end> -i "source.mp4" \
  -vf "crop=<w>:<h>:<x>:<y>,scale=1080:1920:flags=lanczos,subtitles=captions_<clip_id>.ass" \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -movflags +faststart \
  "clips/<clip_id>.mp4"
```
`-ss` ПОСЛЕ `-i` (точность по кадрам). **Escaping:** запускаем ffmpeg с `cwd = data/<job_id>` и относительным `subtitles=captions_<clip_id>.ass` (надёжнее экранирования абсолютных путей с `:`). После каждого клипа дописываем `Clip` в `job.json` (`output_path`, `cost_usd` = сумма по стадиям, `latency_s`).
**Готово когда:** для каждого сегмента есть `clips/<clip_id>.mp4`; `ffprobe` → `width=1080, height=1920`, codec `h264`, аудио `aac`; длительность ≈ (end−start) ±0.2 с; субтитры синхронны, лицо в кадре (спот-чек 2–3 клипа целиком). `job.json` содержит все клипы с cost/latency. Cost $0, libx264 veryfast ~5–15 с/клип.

### Этап H — Склейка `run.py` (CLI) + телеметрия

**H1. `run.py` склеивает Stage 0→5**, пишет `job.json` (массив clips + per-stage cost/latency) и строку в `runs.jsonl` (`run_id, source_minutes, stages{download,transcription,llm_select,reframe,render}, total_sec, total_usd, n_clips, time_to_first_clip_sec`). Это и есть E2E-ритуал валидации качества.
```powershell
just e2e tests/fixtures/sample_01
```
**Готово когда:** в `data/<job_id>/clips/` ≥1 9:16 mp4; рядом `segments.json`, `transcript.json`; в `runs.jsonl` дописана строка. **STOP-GATE 3 (главный):** пока E2E на 1 сэмпле не даёт визуально приличный клип — НЕ строить web/R2/Stripe.

### Этап I — Минимальный web

**I1. Скопировать токены лендинга + шрифты.** В `apps/web/app/globals.css` вставить блок `:root` из `C:\Users\user\Desktop\styles.css` (строки 1–27: `--accent #ff5a3d`, `--hook/--peak/--thought/--quote`, `--dark`, шрифты). Шрифты через `next/font/google` (Unbounded, Onest, IBM Plex Mono) в `layout.tsx`. В `tailwind.config.ts` мост: `colors:{accent:'var(--accent)',muted:'var(--muted)',dark:'var(--dark)',hook:'var(--hook)',peak:'var(--peak)',thought:'var(--thought)',quote:'var(--quote)'}`.
**Готово когда:** временный `<h1 className="text-accent font-[var(--display)]">` коралловый Unbounded, совпадает с лендингом.

**I2. Типы + API-слой + мок воркера.** `lib/types.ts` (§4.3), `lib/api.ts` (`createJob`/`getJob`, base из `NEXT_PUBLIC_WORKER_URL`), `lib/useJob.ts` (polling 2.5s, стоп на done/failed, 3 подряд сетевых сбоя = failed). Временный мок `app/api/mock/jobs/route.ts` отдаёт последовательность статусов + 2 фейковых клипа — разблокирует фронт без готового воркера.
**Готово когда:** `npm run build` без TS-ошибок; при моке весь UI-флоу проходится end-to-end (форма → прогресс → грид с 2 играющими карточками).

**I3. Компоненты + state-машина.** Единственная страница `page.tsx` держит union-стейт: `idle | submitting | tracking | done | error`. Компоненты:
- `SourceForm` — YouTube-input ИЛИ файл (`video/*` ≤ 500 MB), клиентская валидация, защита от двойного сабмита.
- `JobProgress` — степпер `downloading→transcribing→selecting→rendering`, таймер `elapsed` (метрика TTFC на виду), скелетоны.
- `ClipCard` (сердце Phase 0): `<video aspect-[9/16] controls preload="metadata" playsInline>` + `ReasonChip` (цвет по `type`) + таймкод + `score` + **`reason` (explainability в зачатке)** + сниппет + кнопка Download.
- `ClipGrid` — сортировка по `score` desc; строка-итог `N clips · src M:SS · Ks to first clip · $X.XX` (если `metrics` пришли); **empty-state** при `clips:[]` («No clips worth cutting from this one») — это НЕ ошибка.
- `ErrorPanel` — сырой `job.error` (инструмент для дебага) + «Try again» / «New video».

**Готово когда:** на моке полный цикл `idle→done→idle` без перезагрузки; `clips:[]` → empty-state; `status:"failed"` → ErrorPanel с сырым текстом.

### Этап J — End-to-end (worker REST + реальный прогон)

**J1. Обернуть pipeline в FastAPI + SQLite.** `main.py`: `POST /jobs` (BackgroundTask → `tasks.run_pipeline`), `GET /jobs/{id}` (читает SQLite), CORS на `localhost:3000`. SQLite-таблица `jobs(id,status,stage,progress,source_type,source_ref,error,clips_json,cost_usd,latency_ms,created_at,updated_at)` — переживает рестарт процесса. Состояния: `queued→downloading→transcribing→selecting→rendering→done | failed`.
**Готово когда:** `POST /jobs` → job переживает `Ctrl-C`+рестарт (статус из SQLite); `GET /jobs/{id}` доходит до `done` с ≥1 клипом; ключи ответа и enums совпадают с `packages/shared`.

**J2. Реальный прогон с web. ГЛАВНЫЙ ГЕЙТ UI.** Переключить `NEXT_PUBLIC_WORKER_URL` на реальный worker, прогнать одно настоящее YouTube-видео.
**Готово когда:** вставил ссылку → реальный прогресс по статусам → скачиваемые 9:16 MP4 с прожжёнными субтитрами → у каждого клипа читаемый `reason` и `type`; CORS не блокирует. **Если cut субъективно хорош — UI своё дело сделал.**

---

## 6. Переменные окружения

**Корень `clipflow/.env.example`** (реальный `.env` в `.gitignore`; worker валидирует обязательные на старте — fail-fast):
```bash
# ── TRANSCRIPTION (один провайдер; оба word-level) ──
TRANSCRIPTION_PROVIDER=deepgram        # deepgram | assemblyai
DEEPGRAM_API_KEY=                       # основной (быстрее/дешевле)
ASSEMBLYAI_API_KEY=                     # swap

# ── LLM (moment selection, structured output) ──
LLM_PROVIDER=anthropic                  # anthropic | openai | gemini (swappable)
ANTHROPIC_API_KEY=
LLM_MODEL=claude-opus-4-8               # валидация; swap → claude-haiku-4-5 для прода
LLM_MAX_OUTPUT_TOKENS=16000

# ── STORAGE (Phase 0 = local; R2 после GO-gate) ──
STORAGE_BACKEND=local                   # local | r2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=clipflow-dev
R2_ENDPOINT=                            # https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com
SIGNED_URL_TTL=3600

# ── PATHS / DB ──
DATA_DIR=./services/worker/data
DB_PATH=./services/worker/tmp/jobs.db   # /data/jobs.db на Railway
TMP_DIR=./services/worker/tmp

# ── PIPELINE TUNING ──
CLIP_MIN_SEC=15
CLIP_MAX_SEC=60
TARGET_ASPECT=9:16
CAPTION_MAX_WORDS_PER_GROUP=5
MAX_SOURCE_MINUTES=90

# ── TELEMETRY (с дня 1) ──
COST_LOG_PATH=./services/worker/data/runs.jsonl

# ── WEB (apps/web/.env.local) ──
NEXT_PUBLIC_WORKER_URL=http://localhost:8000

# ── DEFERRED (later phases — пусто) ──
# WORKER_API_KEY=                       # symmetric secret (Phase 1 прокси)
# DATABASE_URL=                         # Supabase Postgres (Phase 3)
# STRIPE_SECRET_KEY=                    # Phase 3
```

**Правила секретов:** в git только `*.example`; `.gitignore` блокирует `.env`/`.env.local`/`*.db`. `config.py` через `pydantic-settings` роняет старт при отсутствии обязательного ключа (например `DEEPGRAM_API_KEY` при `TRANSCRIPTION_PROVIDER=deepgram`) — fail-fast, не на середине рендера. Перед коммитом — `git diff` глазами на предмет ключей.

---

## 7. Качество: рубрика, харнесс, cost/latency, GO/NO-GO

### 7.1 Рубрика «годной нарезки» (поклиново, бинарно 0/1)

Сумма `clip_score = C1+...+C8` (макс 8). Сомнение = 0.

| # | Критерий | «1» когда |
|---|---|---|
| C1 | Standalone-understandable | Понятен без контекста исходника |
| C2 | Strong hook ≤2s | В первые 2с — вопрос/заявление/конфликт/число |
| C3 | Clean start | Старт на границе фразы, не с середины слова |
| C4 | Clean end | Конец на завершённой мысли |
| C5 | Face well-framed 9:16 | Лицо в кадре весь клип, не обрезано, не «уплыло» |
| C6 | Captions accurate | ≤1 ошибка на клип |
| C7 | Captions in sync | Рассинхрон < ~150ms |
| C8 | Length 15–60s | (sweet spot 20–45с) |

**Бакеты (с killers):**
- **REJECT** — любой killer: C1=0; C5=0 с грубо сломанным кадром; C6=0 при ≥3 ошибках подряд; или `clip_score ≤ 3`.
- **FIXABLE** — провалены только тримабельные (C2/C3/C4/C8), `clip_score ≥ 5`, нет killers (чинится сдвигом границ — ровно то, что закроет Phase 2 trim-редактор).
- **USABLE** — `clip_score ≥ 7`, нет killers.

Зачётная метрика: **`Q = (usable + fixable) / total`** (fixable = починка строго <1 мин). Форма оценки — одна CSV-строка на клип, включая `reason_label` и **`reason_agrees ∈ {0,1}`** (согласен ли человек с объяснением — валидация explainability, нашего моата).

### 7.2 Evaluation harness

**Golden set — 6 замороженных источников** (не меняем между итерациями промпта):

| # | Тип | Роль |
|---|---|---|
| S1 | Clean podcast, solo, EN | in-scope, должен работать |
| S2 | Expert vlog, 1 человек, EN | in-scope (beachhead) |
| S3 | Clean podcast, RU | in-scope, проверка языка |
| S4 | 2-person interview | контроль ICP (ожидаем провал C5 — это правильное сужение) |
| S5 | Длинный 60–120 мин | стресс cost/latency/таймаутов |
| S6 | Шумное/грязное аудио | стресс C6/C7 |

Объём: топ-6 клипов на каждый in-scope (S1/S2/S3) = **≥18 клипов/прогон**. S4/S5/S6 — диагностическая вкладка (S5/S6 влияют на cost/latency-таргеты). Оценщик = фаундер, смотрит клип **целиком, со звуком, на телефоне в вертикали**, заполняет C1–C8 ДО просмотра `score` (анти-bias). ~1–1.5 часа на прогон. **Кэшируем транскрипцию по `hash(source)`** — повторные прогоны (а их много при итерации промпта!) не платят за транскрипцию повторно (главный рычаг экономии Phase 0).

### 7.3 Cost/latency (с первого запроса)

Каждая стадия пишет `{sec, usd}` в `runs.jsonl`. Сводка на одно 60-мин видео:

| Stage | Cost | Latency |
|---|---|---|
| 0 Import | $0 | 15–60 с |
| 1 Transcribe (Deepgram) | ~$0.26 | 30–60 с |
| 2 Select (Opus 4.8) | ~$0.13 | 10–40 с |
| 3 Reframe | $0 | ~1–3 с × N |
| 4 Captions | $0 | <1 с |
| 5 Render | $0 | 5–15 с × N |
| **Итого** | **~$0.40/видео** | **~2–4 мин до первых клипов** |

На Haiku отбор → ~$0.025, итог ~$0.29. Таргеты: **cost/video ≤ $2** (ceiling $3), **TTFC ≤ 5 мин** для 30-мин источника (ceiling 10). После прогона — сводка `mean/p90 total_usd`, `mean/p90 TTFC`.

### 7.4 GO/NO-GO gate (Phase 0 → Phase 1)

**GO (всё одновременно, на одном чистом прогоне in-scope):**
1. `Q = (usable+fixable)/total ≥ 60%` (≥11/18).
2. `usable/total ≥ 25%` (есть «почти как есть»).
3. `mean(reason_agrees) ≥ 70%` (объяснения правдоподобны — моат жив).
4. Системные killers под контролем: доля C6-killer `< 15%`; C5 не проваливается на single-speaker S1/S2.
5. Экономика: `mean cost/video ≤ $2` (или понятный план до $2 через self-host = **conditional GO**); `p90 TTFC ≤ 10 мин`.

**NO-GO = диагностика, какой винтик крутить:**

| Провалено | Действие |
|---|---|
| `Q` низкий, `reason_agrees` ОК, провалы C2/C3/C4 | Итерация промпта + snap-to-sentence; не менять провайдеров |
| `Q` низкий И `reason_agrees` низкий | Переписать промпт (few-shot, явные критерии хука), попробовать другую модель (swap) |
| C6-killer >15% (S3/S6) | Swap провайдера транскрипции; если RU слаб везде — сузить ICP до EN |
| C5 проваливается на single-speaker | Инженерный баг reframe — чинить сглаживание/fallback |
| cost/TTFC за ceiling | Self-host WhisperX раньше; дешевле модель LLM; кэш |
| Хорошо на S2, плохо на S1 (или наоборот) | Сузить ICP до проходящего типа |

**Правило остановки итераций:** бюджет Phase 0 — **~10 прогонов golden set / ~5–7 рабочих дней**. Если даже на самом узком ICP `Q < 60%` и `reason_agrees < 70%` — это сильный сигнал, что подход не даёт качества: **не строим Phase 1, делаем стратегический разворот**. Лучше узнать сейчас.

---

## 8. Риски и митигейшн

| Риск | Уровень | Симптом | Митигейшн |
|---|---|---|---|
| R1 Reframe 9:16 | ВЫСОКИЙ | Лицо уезжает/обрезано, дрожание; катастрофа на 2 спикерах | **Single-speaker ONLY** (главный щит, S4 провал ожидаем); сглаживание+dead-zone; center-crop fallback; если C5 падает на S1/S2 — блокер, чинить до gate |
| R2 Отбор моментов LLM | ВЫСОКИЙ | Непонятны (C1), нет хука, `reason_agrees` низкий, score не калиброван | Версионируемый промпт `prompts/select_moments.vN.txt`, прогон по golden set; few-shot; structured output + валидация (невалид = retry); snap-to-sentence; A/B Opus vs Haiku |
| R3 Рассинхрон субтитров (C7) | СРЕДНИЙ/ВЫСОКИЙ | Субтитры плывут | Word-level дисциплина; `t_clip = t_source - segment.start` в одной PURE-функции (unit-тест); один источник таймингов; визуальная проверка на S6 |
| R4 Ошибки транскрипции (C6) | СРЕДНИЙ | Перевраны имена/термины (RU/шум) | Word-level провайдер обязателен; C6-killer >15% → swap провайдера на golden set, data-driven; RU проверить заранее |
| R5 Латентность | СРЕДНИЙ | TTFC >10 мин | Мерить с дня 1; параллельный рендер клипов (база progressive output); не оптимизировать преждевременно |
| R6 Runaway cost | СРЕДНИЙ | Прогон жрёт $5+ | Hard-ceiling алерт (прогноз по минутам > $3 → подтверждение); **кэш транскрипции по hash(source)** (главный рычаг при итерации); prompt caching |
| R7 yt-dlp/стабильность | НИЗКИЙ/СРЕДНИЙ | yt-dlp падает (гео/возраст/формат), таймауты на S5 | File-upload как всегда-доступный путь; ретраи с бэкоффом; таймаут на стадию с понятной ошибкой |
| R8 Railway redeploy в длинной джобе | НИЗКИЙ | Джоба прерывается при деплое | Короткие тестовые видео; деплой когда нет активных джоб; полное решение — Celery+Redis (Phase 1) |
| R9 Дрейф контрактов web↔worker | НИЗКИЙ | UI и worker разъехались | Монорепо + `packages/shared` как источник правды; DoD-проверка совпадения enums/ключей |

---

## 9. Дорожная карта после Phase 0

**Phase 1 — Usable MVP (надёжный продукт без «магии»).** Стабильный async-пайплайн (очередь/статусы/ретраи — Celery+Redis при триггере); подключить R2 (`storage.py` swap, presigned download, lifecycle: clips/transcript храним постоянно, upload-source ~60 дней, YouTube-import не храним); **progressive output** (клипы по мере готовности, polling→SSE/WS — меняется только `useJob`); 1–2 caption-стиля (зачаток brand templates); сохранять word-timestamps + clip↔source маппинг; cost/latency-дашборд из `runs.jsonl`.

**Phase 2 — «Магия» (отличие от Opus/2short).** Interactive **transcript-based trim editor** (`clip.words[]` уже в контракте); **«why these, not others» панель** (worker добавит `rejected_moments[]`; explainability валидирована в Phase 0 через `reason_agrees`); fly-out clip cards + clip↔source linkage (`clip.start/end` уже в координатах исходника); Remotion Player для preview/рендера. Всё это — новые компоненты вокруг тех же данных, не переделка пайплайна.

**Phase 3 — Деньги/аккаунты/персистентность.** Supabase Postgres + Auth (проекты никогда не авто-удаляются); per-video pricing (no credits) через Stripe ($5–15 при cost ≤$2); история проектов, повторное скачивание, биллинг по фактическому cost (логи уже умеют); опционально self-host WhisperX + MediaPipe/Pyannote ради маржи.

**Phase 4 — Дистрибуция/рост.** Шаринг/публикация, шаблоны под Shorts/Reels/TikTok; affiliate/referral; шире ICP (multi-speaker reframe через Pyannote-диаризацию + переключение кадра, новые языки); командные/агентские тарифы.
