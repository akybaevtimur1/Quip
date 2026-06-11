# ClipFlow — HANDOFF (читать ПЕРВЫМ в новой сессии, вместе с CLAUDE.md)

> Это операционная «правда» проекта на **2026-06-11**. Новый агент за 2 минуты понимает
> состояние, умеет запустить и продолжить — без перечитывания всей истории.
> Детальный журнал — `CLAUDE.md`. План — `CLIPFLOW_DEV_PLAN.md`. Бенчмарки — `docs/BENCHMARKS.md`.

> ⛔ **ПЕРЕД ЛЮБЫМИ ПРАВКАМИ REFRAME/RENDER — читай `docs/REFRAME_FPS_GRID_INVARIANT.md`.**
> Там зафиксирован инвариант кадровой сетки, который убирает «флеши» на переходах. Сломаешь —
> флеши вернутся, и видно это ТОЛЬКО на видео ≠ 25 fps (тесты будут зелёные). Коммит `742b3e1`.

---

## ⚠️ DEMO PREP — читай если завтра демо (70 человек)

### Что сделать ДО демо (чеклист)

**1. Поставь пароль (auth gate, уже в коде):**
```powershell
# В apps/web/.env.local (или в переменных хостинга):
DEMO_PASSCODE=clipflow2026
```
Без этой строки — приложение открытое (нет пароля). С ней — все страницы требуют вход.
Расскажи участникам пароль перед демо.

**2. Убедись что воркер запущен и доступен:**
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Воркер должен быть доступен по сети (не только localhost) если юзеры приходят с разных машин.
IP твоей машины: `(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" } | Select-Object -First 1).IPAddress`

**3. Укажи URL воркера во фронте:**
```
# apps/web/.env.local
NEXT_PUBLIC_WORKER_URL=http://<IP_ТВОЕЙ_МАШИНЫ>:8000
```
Без этого — фронт идёт в мок-роут `/api/mock` (не реальный пайплайн).

**4. Проверь API-ключи в `.env` (корень):**
```
DEEPGRAM_API_KEY=...          ← транскрипция
GEMINI_API_KEY=...            ← выбор моментов
LLM_MODEL=gemini-flash-latest ← НЕ менять на 2.5-pro
YTDLP_COOKIES_FILE=...        ← для приватных видео
```

**5. Протести один прогон вручную перед демо:**
- YouTube URL короткого EN/RU видео (5–10 мин)
- Должно появиться 3–8 клипов за 1–3 минуты
- Проверь что субтитры есть, видео 9:16

### Сколько это стоит при 70 участниках
| Сценарий | Стоимость |
|---|---|
| Каждый запускает 1 видео (10 мин) | 70 × $0.05 = ~$3.50 |
| Каждый запускает 1 видео (33 мин) | 70 × $0.16 = ~$11.20 |
| 10 запускают (остальные смотрят) | ~$1.60 |

Deepgram + Gemini суммарно. Терпимо для MVP-демо.

### Что ТОЧНО работает для MVP
✅ YouTube URL → 3–10 вертикальных 9:16-клипов с субтитрами (EN/RU авто-язык)
✅ Загрузка файла с компа (POST /jobs/upload, multipart) → тот же пайплайн (2026-06-11)
✅ Надёжное YouTube-скачивание: yt-dlp 2026.6.9 + PO-token провайдер (Docker :4416) — §8
✅ Редактор клипа = МОДАЛКА (✕/Esc/клик-вне): широкий таймлайн (двигать/resize шортс
   руками), галерея стилей субтитров A–D, вырезание слов, рендер (2026-06-12)
✅ Живое WYSIWYG-превью субтитров (libass.wasm, OSS): субтитры в превью = экспорт
   пиксель-в-пиксель; видео = источник на моменте (двигаешь блок → едет) (2026-06-12)
✅ Deep-link задачи: http://localhost:3000/?job=<id> (открыть готовую задачу)
✅ Прогресс-бар по стадиям (queued→downloading→transcribing→selecting→rendering→done)
✅ CC оверлей (TikTok-анимация, кнопка CC; покрывает burned-in субтитры)
✅ Полный экран с CC (fullscreen кнопка на карточке)
✅ Скачать клипы / выбрать несколько / скачать выбранные
✅ Редактор: вырезать слова, продлить клип, перерендерить
✅ Редактор субтитров: правка текста реплик inline, сохраняется в БД
✅ Степпер 1–10 клипов (выбор количества)

### Что НЕ работает / ограничения
⚠️ Видео без речи / очень короткое → 0 клипов (empty-state показывается)
⚠️ Параллельные джобы: воркер обрабатывает последовательно (очередь, не параллельно)
⚠️ Одно видео: ~1–3 минуты (транскрипция + reframe CPU)
⚠️ Русские субтитры: могут содержать опечатки (Deepgram, не идеально)
⚠️ ASD (наведение на говорящего): работает, но иногда выбирает не того (многоликие кадры)

---

## 0. ⚡ Editor v3 (ветка `feat/editor-v3`, 2026-06-13) — НОВОЕ, тестируй первым

Ночная автономная сессия: редактор доведён до «как в нормальных редакторах». Всё в ветке
`feat/editor-v3` (запушена). Спека `docs/superpowers/specs/2026-06-12-editor-v3-design.md`,
план `docs/superpowers/plans/2026-06-12-editor-v3.md` (там же итог исполнения).

**Что нового:**
- **Страница `/edit/<job>/<clip>`** вместо модалки. «← Все клипы» и браузерный Back →
  `/?job=` (грид восстанавливается, ничего не теряется). Прямой URL/F5 работает.
  ‹ › переключение клипов, Рендер/Скачать в хедере.
- **libass-превью ПОЧИНЕНО** (корень «Worker error: {}»): октопус падал на отсутствующем
  default.woff2 → ты всё время видел CSS-фолбэк! Теперь fallbackFont=Montserrat +
  canvas-режим (канвас = весь 9:16-кадр; видео-режим позиционировал по object-contain
  и рисовал мимо). Субтитры в превью теперь РЕАЛЬНО пиксель-в-пиксель как экспорт.
- **AI-карта видео**: `GET /jobs/{job}/chapters` — Gemini делит ВСЁ видео на главы
  с описаниями (кэш chapters.json, ~$0.01-0.03 один раз). Полоса глав на таймлайне:
  hover = title+summary, клик = прыжок шортса. comedy01 → 16 глав.
- **Таймлайн v2**: зум 1×–10× (кнопки + Ctrl/Cmd+колесо) + пан — для часовых видео.
- **Субтитры**: 12 пресетов (A–L: MrBeast/Неон/Подкаст/Караоке-грин/…), кастомизация
  поверх пресета (цвета/размер/шрифт/позиция/анимация/uppercase), правка текста КЛИКОМ
  ПО ВИДЕО (inline на месте, пауза), ДРАГ субтитров по вертикали (гайд-линия),
  анимации слов pop/bounce (ASS \t — одинаково в превью и экспорте).
- **Шрифты Montserrat/Unbounded/Rubik** — в ОБОИХ местах (public/libass/fonts +
  services/worker/fonts, ffmpeg fontsdir). Добавляешь шрифт → клади в оба.
- **Split-screen (2 спикера верх/низ, как OpusClip)**: авто в пайплайне (ровно 2
  устойчивых разнесённых лица → split вместо fit; 3+ лиц/пейзаж → fit ОСТАЁТСЯ) +
  вручную в табе «Кадр» (Авто/Тайт/Широко/Split + слайдеры позиций). Кноб
  `REFRAME_SPLIT_ENABLED=true`. Инвариант fps-grid цел (Δ=0.00000 проверено).
- **Кодген-фикс**: _strip_titles съедал поле модели с именем "title".

**Гейты**: just check зелёный (297 тестов), next build зелёный, e2e живьём: рендер со
стилем Hormozi (зелёное караоке в mp4), смена пресета live, возврат, AI-карта.
**⚠️ Не проверено глазами фаундера**: split через клик в табе «Кадр» (бэкенд+рендер
доказаны напрямую); общая полировка вида.
**⚠️ Безопасность**: в истории GitHub (старый коммит 59d07b4) лежали youtube-куки —
ПЕРЕВЫПУСТИ куки (logout/login + новый export cookies.txt).

---

## 1. Что это

Длинное YouTube-видео → 3–10 вертикальных 9:16-клипов с прожжёнными субтитрами.
Пайплайн: **download → transcribe → LLM выбирает моменты → reframe 9:16 → субтитры → render**.
Монорепо: `apps/web` (Next 16/React 19/TS/Tailwind v4), `services/worker` (Python 3.12 /
FastAPI / uv, пакет `app`), `packages/shared` (TS-типы, codegen из `app/models.py`).

---

## 2. Статус (что готово)

### ✅ Phase 0 (A→J) — сквозной пайплайн + web UI + worker REST/SQLite, e2e проверен

### ✅ Reframe v3 — единый ASD-путь, DoD Δ=0 (2026-06-10, коммиты `76e5132`…`a056e4b`)

**Проблема** (история R1→R1d→Flash Fix): флеши fill↔fit при переключении режима вне склеек.
Корни: (1) ffmpeg scene float-порог не frame-accurate; (2) два отдельных пути (largest-face / ASD) с независимыми багами; (3) xfade между fill/fit сам был zoom-вспышкой.

**Решение:**
- **Единый путь без форка** — `score_tracks_in_segment` всегда, ASD внутри, фолбэк на largest-face если score < порога.
- **PySceneDetect** (frame-accurate, threshold≈27) вместо ffmpeg float-порога.
- **Целые кадры на всём пути**: PySceneDetect → `build_shots_frames` → `plan_regions` → `trim=start_frame=` в ffmpeg. Нет float-to-int округлений.
- **`plan_regions` (PURE)** — единый планировщик: 2+ разнесённых лица → fit; 1 лицо/кластер → fill на говорящем (ASD); нет лиц → fit.
- **Жёсткий cut** вместо xfade: кроссфейд тайт↔широкий сам был zoom-вспышкой.
- **`merge_short_regions`** — регион < `min_hold_sec` (1.5с) поглощается предыдущим (анти-флеш рапид-монтажа).
- **face_fps=25.0** (было 5.0) — LR-ASD обучена на 25fps; при 5fps давала случайные scores.
- **torch/ASD → базовые зависимости** — `uv sync` без флагов = рабочий ASD. Больше не нужен `--extra asd`.

**DoD** (`tmp/dod_reframe_direct.py`, без Deepgram/Gemini):
- seg_A (60–180с): 30 склеек, 28 регионов, **27 границ — все Δ=0** ✅
- seg_B (300–420с): 15 склеек, 15 регионов, **14 границ — все Δ=0** ✅
- seg_C (600–720с): 26 склеек, 24 региона, **23 границы — все Δ=0** ✅
- **ИТОГО: 64 границы, max Δ = 0 кадров** → флеш физически невозможен.

### ✅ Загрузка файла с компа (2026-06-11)

Воркер раньше принимал только YouTube-URL. Добавлен путь upload (демо-видение фаундера
«грузишь видос»):
- `POST /jobs/upload` (multipart, FastAPI `UploadFile`) — стримит файл чанками в
  `data/<job_id>/upload.<ext>`, затем фон-таск `run_upload_job`.
- `stage0_import.import_upload` — remux/transcode в `source.mp4` (`-c copy`, фолбэк h264/aac) →
  `source.wav` → ffprobe → `meta.json`. Готовит ТЕ ЖЕ артефакты, что и YouTube-путь, поэтому
  `run_pipeline(source_url=None)` видит их как кэш Stage 0 → ноль изменений в стадиях 1-5.
- Фронт: `SourceForm` — drag&drop + выбор файла (≤500МБ, `video/*`); `createUploadJob` (FormData).
- `run.py`: `source_kind=meta.source` (был хардкод youtube). +`python-multipart` в депы.
- +2 unit-теста (endpoint через TestClient, фон-таск замокан). `just check` зелёный, 229 тестов.

### ✅ Editor v2 — модалка + таймлайн + пресеты + libass-превью (2026-06-12)

Спеки: `docs/superpowers/specs/2026-06-11-editor-v2-design.md` (модалка/таймлайн/пресеты) +
`docs/superpowers/specs/2026-06-12-wysiwyg-libass-preview-design.md` (libass; §8 = Approach B Revideo).

**Бэкенд:**
- `GET /jobs/{job}/clips/{clip}/timeline` → `TimelineData` (длительность + ВСЕ ИИ-сегменты + слова).
- `POST .../edit/set-interval` → `set_interval` (двигать/resize шортс, optimistic-lock 409).
- `GET .../clips/{clip}/ass` → ASS текущего edit-state (тот же `captions_v2.compile_ass`, что экспорт).
- Сид-пресеты A–D (`app/editor/preset_seeds.py`), в `GET /presets`. Дефолт `preset_a`.
- Экспорт (`tasks.render_clip_edit_job`) теперь жжёт субтитры выбранного стиля (раньше НЕ жёг).

**Фронт (модалка `ClipEditorModal.tsx`):**
- Открывается по «Редактировать» (`ClipCard`), полноэкранная (✕/Esc/клик-вне). Старый инлайн-редактор удалён.
- ЛЕВО: видео = `media/{job}/source.mp4` (object-cover, перемотка на интервал + луп) + субтитры
  рисует **libass.wasm** (`LibassLayer.tsx`, SubtitlesOctopus, MIT) из `/ass` (timeOffset=-sourceStart).
  Правка субтитра кликом по активной реплике → PATCH → refetch ASS. Галерея пресетов `PresetStrip`.
  Фолбэк на CSS-`CaptionOverlay`, если libass не поднялся.
- ПРАВО: широкий `TimelineEditor` (drag/resize блока, ИИ-маркеры, hover-транскрипт) + вырезание слов + рендер.
- libass-ассеты: `apps/web/public/libass/` (worker+wasm+legacy+Montserrat.ttf). `eslint` игнорит `public/**`.

**Кнобы/грабли:**
- ⚠️ Видео в превью = ИСТОЧНИК (object-cover центр), кроп 9:16 приблизительный; ТОЧНЫЙ reframe-кроп —
  только на финальном рендере (ffmpeg). Точный live-кроп = Approach B (Revideo, отложен).
- ⚠️ Визуальную корректность libass (рисует/обновляется) проверяет фаундер глазами — автотестом не верифицируется.
- ⚠️ source.mp4 у comedy01 = 328МБ; seek через HTTP range (StaticFiles умеет). Большие источники грузятся дольше.
- Тест без Gemini: `http://localhost:3000/?job=comedy01` (посеяно `tmp/seed_cached_job.py`).

### ✅ Editor Core MVP (2026-06-09)

Не-деструктивный редактор поверх batch-пайплайна. `ClipEdit` = `SourceInterval[]` + `CaptionTrack` + `CropOverride[]`.

**`app/editor/`:** timemap, replies, defaults, ops, reframe_cache, captions_v2, store, presets.

**REST:** `GET/PATCH /edit`, trim/add-section/extend/crop/render/analysis, presets.

Optimistic-lock (version mismatch → 409). Правки = $0 (Deepgram/Gemini не вызываются).

E6 e2e: `comedy01/clip_01`, trim → 2 интервала, video=19.76s / audio=19.78s / render=9.88s.

### ✅ Другие улучшения (ранее)
- **K3 авто-язык** — Deepgram `detect_language` (lang=None), RU/EN автоматически.
- **Больше клипов** — `max_clips=8`, промпт расширен.
- **C — clean-start** — клип не начинается с середины предложения.
- **B — курирование в UI** — степпер клипов 1–10 + чекбоксы + «скачать выбранные».
- **R1b** — широко/тайт по геометрии лиц (2+ разнесённых лица → fit).
- **Deepgram WriteTimeout** — `write=None` в httpx.Timeout (WAV >80МБ больше не падает).

### ✅ UI — 2026-06-11
- **CC overlay тёмная плашка** — перекрывает burned-in ASS субтитры, позиция bottom:13.5% = ASS MarginV=260.
- **CC auto-on в edit-режиме** — при открытии редактора CC включается автоматически.
- **Редактор субтитров (шаг 1)** — inline правка текста всех caption-реплик. Сохранение через PATCH /edit (text_override). Оверлей синхронизируется в realtime через onRepliesChange. При рендере горит уже исправленный текст.
- **Fullscreen** — кнопка на карточке. Fullscreen на контейнере (не video) — CC overlay виден.
- **409 auto-reload** — версионный конфликт автоматически перезагружает edit-state.
- **DEMO_PASSCODE gate** — middleware.ts + /login + /api/auth; включается через env var.

### ⏸️ Отложено / не начато
- **K1** — RQ+Redis очередь: план в `docs/superpowers/plans/...k1-queue.md`, не начат.
- **Active-speaker за флагом** (`REFRAME_SPEAKER`) удалён из config в v3 — теперь ASD всегда.
- **Гейтованный Task 6** — плавный zoom-переход (~0.3с ease-in-out) для intra-shot wide-reveal. Только после визуального вердикта «флеши ушли».

---

## 3. Как запустить (Windows, PowerShell)

**⚠️ PATH refresh обязателен в каждом PowerShell-вызове:**
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
```

**⚠️ После любой правки кода воркера — перезапусти воркер** (uvicorn без --reload):
```powershell
foreach ($p in 3000,8000){ Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue | Select -Expand OwningProcess -Unique | %{ Stop-Process -Id $_ -Force } }
```

**Поднять стек (UI):**
```powershell
# Worker:
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Web (из корня):
Set-Location "C:\Users\user\Desktop\ClipClow"
pnpm --filter web dev
```
UI: **http://localhost:3000**

**CLI e2e (кэш, $0):** из `services/worker`:
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run python -m app.run comedy01
# стадии 0-2 кэшируются → повторный прогон не платит Deepgram/Gemini
# удали clips/ для перерендера без оплаты: Remove-Item -Recurse -Force data\comedy01\clips
```

**Гейт перед коммитом:**
```powershell
Set-Location "C:\Users\user\Desktop\ClipClow"
just check
```

---

## 4. Тестовые данные (`services/worker/data/`, gitignored)

| Датасет | Описание | Кэш |
|---------|----------|-----|
| `comedy01` | RU интервью «Звёзды против мошенников» (~33 мин, Щербаков) | source + transcript + segments + clips |
| `sample01` | EN «Mafia show» (мультиспикер, ~33 мин) | source + transcript + segments + clips |
| `test01` | EN короткое видео (193с, 504 слова) | source + transcript + segments + clips |
| `dod01` | Часовой подкаст (youtube.com/watch?v=37IEHFgTubk) | source.mp4 (скачан), транскрипция ещё не оплачена |

`comedy01` — основной для reframe без оплаты. `dod01` — для e2e проверки транскрипции длинного видео.

---

## 5. Архитектура (где что)

```
apps/web/
  app/page.tsx               — state-машина idle→tracking→done→error
  components/                — SourceForm (степпер 1–10), ClipGrid (чекбоксы), ClipCard,
                               JobProgress (степпер стадий + таймер + скелетоны), ErrorPanel…
  lib/                       — api (useJob polling 2.5с/3-фейла/effect-based), format
  app/api/mock/              — мок-воркер для dev

packages/shared/             — TS-типы (ТОЛЬКО codegen, не трогать руками!)
  contract.json              — JSON-схема из models.py
  src/types.ts               — TypeScript типы

services/worker/
  app/
    models.py                — ЕДИНЫЙ источник типов. Менять здесь → just types
    config.py                — pydantic-settings, fail-fast, lru_cache
    errors.py                — JobError (нет тихих фолбэков, правило №8)
    db.py                    — SQLite: jobs + clip_edits
    tasks.py                 — фоновый asyncio-worker, обновляет статус
    main.py                  — FastAPI: POST/GET /jobs, editor endpoints, /healthz, CORS :3000, /media
    run.py                   — СКЛЕЙКА стадий 0→5. job.json + runs.jsonl

    pipeline/
      stage0_import.py       — yt-dlp download + ffprobe meta (SourceMeta)
      stage1_transcribe.py   — Deepgram REST /v1/listen через httpx (НЕ SDK!)
                               write=None таймаут → WAV >100МБ без падения
      stage2_select.py       — Gemini structured output → сегменты. Промпт в prompts/
      stage3_reframe.py      — Reframe v3 (см. §6). SpeakerTrack / TrackRegion / plan_regions.
      stage4_captions.py     — ASS субтитры (Montserrat 90, upper, group_words)
      stage5_render.py       — Engine A (ffmpeg filter_complex, default) / Engine B (cv2 pipe)

    asd/
      _vendor/               — LR-ASD ядро (вендоринг, MIT, 0.84MB)
      scorer.py              — torch-based ASD scorer (ленивая загрузка)
    pipeline/asd_reframe.py  — score_tracks_in_segment: MediaPipe@25fps → SpeakerTrack[]

    editor/
      timemap.py, replies.py, defaults.py, ops.py
      reframe_cache.py       — analyze_source_range + resolve_regions (для editor)
      captions_v2.py         — compile_ass (с \k карао-ке)
      store.py               — ensure_edit / save_edit (optimistic-lock) / load_edit
      presets.py             — apply_preset, list/save/get

  prompts/
    select_moments.v1.txt    — промпт Gemini (крутить без перекодировки)

  tests/unit/                — 206 тестов, все зелёные
  tmp/
    dod_reframe_direct.py    — DoD-верификация Δ=0 на сегментах source.mp4
    verify_flash.py          — верификация reframe_*.json от полного пайплайна
```

---

## 6. Reframe v3 — поток данных

### `reframe_segment` (единый путь)

```
source.mp4 + (start, end, fps)
  │
  ├─ score_tracks_in_segment (asd_reframe.py)
  │    MediaPipe FaceDetector@25fps → лица (cx, width) по кадрам
  │    build_tracks (IOU) → дорожки лиц
  │    LR-ASD scorer (torch) → speak-score на дорожку
  │    → list[SpeakerTrack(f0, f1, cx_tuple, width, speak)]
  │
  ├─ detect_scene_cuts (PySceneDetect ContentDetector, threshold≈27)
  │    → list[int]  кадры-склейки (клип-relative, frame-accurate)
  │
  ├─ build_shots_frames(cuts, total_frames)
  │    PURE. → list[tuple[int,int]]  интервалы планов в КАДРАХ
  │
  ├─ plan_regions(shots, tracks, fps, crop_w_frac, speak_threshold, ...)
  │    PURE. На каждый шот:
  │      _is_wide_shot → 2+ разнесённых лица (spread > 9:16 ширина) → fit
  │      _pick_target  → говорящий (ASD score > threshold) или largest-face → fill
  │      нет лиц → fit
  │      cx per-frame → EMA smoothing внутри плана
  │    Граница региона = граница плана = реальный кадр-склейки → Δ=0 по конструкции
  │    → list[TrackRegion]
  │
  └─ merge_short_regions(regions, min_hold_sec=1.5)
       план < min_hold → поглощается предыдущим (нет рапид-мигания)
       → list[TrackRegion]  (записывается в reframe_<clip>.json)
```

### `render_clip` (Engine A, default)

```
regions + source.mp4
  │
  ├─ build_smooth_filter(regions, src_w, src_h, fps, ass_name)
  │    PURE. filter_complex:
  │      [0:v]setpts=PTS-STARTPTS, split=N
  │      fill-регион → trim(start_frame, end_frame) + crop(piecewise cx-expr) + scale + setsar=1
  │      fit-регион  → blur-bg + letterbox + setsar=1  (уникальные [bg{i}][fg{i}])
  │      concat=N → subtitles={ass} → [outv]
  │
  └─ build_single_pass_cmd → _run_ffmpeg → clips/<id>.mp4
       -ss {aligned_start} -t {dur}  (aligned = round(start*fps)/fps — граница кадра)
       -filter_complex {fc} -map [outv] -map 0:a  (аудио НЕПРЕРЫВНЫМ → нет priming-подлага)
       -c:v libx264 -crf 20 -c:a aac -b:a 128k -movflags +faststart
```

### Ключевые типы

```python
@dataclass(frozen=True)
class SpeakerTrack:
    f0: int; f1: int            # кадры клип-relative
    cx: tuple[float, ...]       # cx по кадрам (MediaPipe, нормализовано 0..1)
    width: float                # средняя ширина лица (для largest-face fallback)
    speak: float                # mean ASD score (выше = говорит)

@dataclass(frozen=True)
class TrackRegion:
    t0: float; t1: float        # секунды клип-relative
    mode: str                   # "fill" | "fit"
    points: tuple[TrackPoint, ...]  # fill: траектория cx; fit: ()
```

`reframe_<clip_id>.json` → `{regions:[{t0,t1,mode,points:[{t,mode,cx},...]},...] }`

---

## 7. Кнобы качества (`.env` / `config.py`)

| Переменная | Дефолт | Описание |
|------------|--------|----------|
| `REFRAME_MODE` | `auto` | `auto` / `fill` / `fit` глобально |
| `REFRAME_ENGINE` | `A` | `A` = ffmpeg piecewise (быстро ~4–8с/клип); `B` = cv2 pipe (медленно, точно) |
| `REFRAME_FACE_FPS` | `25.0` | Кадров лиц в сек (ASD требует 25; снижать только для скорости) |
| `REFRAME_SMOOTHING` | `0.15` | EMA коэф. сглаживания cx лица (0=frozen; 1=без сглаж.) |
| `REFRAME_MIN_HOLD_SEC` | `1.5` | Анти-флеш: план короче → поглощается предыдущим |
| `REFRAME_WIDE_RATIO` | `0.5` | Доля кадров с широкой геометрией для решения "fit" на план |
| `REFRAME_SCENE_THRESHOLD` | `27.0` | PySceneDetect ContentDetector порог (~27 = дефолт) |
| `REFRAME_SPEAK_THRESHOLD` | `0.0` | ASD score ниже порога → фолбэк на largest-face |
| `REFRAME_SPEAKER_CROP_SCALE` | `0.55` | Ширина кропа вокруг лица |
| `LLM_MODEL` | `gemini-flash-latest` | ⚠️ gemini-2.5-pro = квота 0 на free tier |
| `MAX_CLIPS` | `8` | Макс. кандидатов от Gemini (юзер выбирает из них в UI) |
| `YTDLP_COOKIES_FILE` | `` | Путь к Netscape cookies.txt (приоритет над browser) |
| `YTDLP_COOKIES_BROWSER` | `edge` | `edge`/`firefox`/`chrome`/`""`. Chrome 127+ = DPAPI-баг |

**Тюнинг без оплаты (comedy01 или test01 кэш):**
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
Remove-Item -Recurse -Force data\comedy01\clips -EA SilentlyContinue
uv run python -m app.run comedy01
# Проверить регионы clip_01:
Get-Content data\comedy01\reframe_clip_01.json | python -m json.tool | Select-Object -First 30
```

---

## 8. YouTube скачивание: PO-токены + куки (ВАЖНО)

### PO-токен провайдер (главный рычаг надёжности, 2026)

YouTube требует **PO-токены** (Proof-of-Origin) для многих форматов — без них «Sign in to
confirm you're not a bot» / HTTP 403. Решение поставлено (2026-06-11):
- **yt-dlp** обновлён до 2026.6.9 (обновлять часто: `uv lock --upgrade-package yt-dlp; uv sync`).
- Плагин **`bgutil-ytdlp-pot-provider`** (в депах воркера) — yt-dlp подхватывает автоматически.
- Бэкенд-провайдер — **Docker-контейнер** на :4416 (генерит токены под каждое видео):
  ```powershell
  # один раз (демон Docker Desktop должен быть запущен):
  docker run --name bgutil-provider -d --init --restart unless-stopped -p 4416:4416 brainicism/bgutil-ytdlp-pot-provider
  # проверка: должно вернуть {"version":"1.3.1"}
  (Invoke-WebRequest http://127.0.0.1:4416/ping -UseBasicParsing).Content
  ```
  `--restart unless-stopped` → контейнер сам поднимается при старте Docker Desktop.
- ⚠️ **ПЕРЕД ДЕМО:** запусти Docker Desktop (демон) → провайдер поднимется сам. Проверка
  цепочки: `uv run yt-dlp -v --simulate <url>` → в логе `[pot] PO Token Providers: bgutil:http`.
- Альтернатива без Docker: нативный Node-сервер провайдера (Node 22 стоит) — см. репо
  Brainicism/bgutil-ytdlp-pot-provider (`server/`, npm i + build + `node build/main.js`).

### Куки (дополнение к PO-токенам)

Chrome 127+ и Edge сломали DPAPI-расшифровку кук — `--cookies-from-browser` падает.

**Надёжный путь (cookies.txt):**
1. Расширение **"Get cookies.txt LOCALLY"** в Chrome
2. Открыть youtube.com (залогиниться) → Export → сохранить `.txt` (Netscape, не JSON)
3. `.env`: `YTDLP_COOKIES_FILE=C:\Users\user\Desktop\ClipClow\www.youtube.com_cookies.txt`

Файл начинается с `# Netscape HTTP Cookie File`.

---

## 9. Известные проблемы и грабли

### Критичные грабли инструментов агента

| Грабля | Правило |
|--------|---------|
| PowerShell держит cwd между вызовами | Всегда абсолютные пути или `Set-Location` в начале |
| Bash-инструмент не видит ffmpeg/just (winget PATH) | Прогоны пайплайна — через PowerShell с PATH-refresh |
| Коммит из Bash → кириллица `?????` + BOM | Коммитить ТОЛЬКО из PowerShell; сообщение в файл + `-F` |
| pre-commit ruff-format переформатирует → хук падает | После `reformatted N files` → `git add` + повторный коммит |
| opencv-python-headless + opencv-contrib-python → битый cv2 | Держать ОДИН opencv-пакет |

### Известные ограничения

| Баг / ограничение | Описание | Приоритет |
|-------------------|----------|-----------|
| Двойные субтитры | Видео с вшитыми субтитрами → наши прожигаются поверх | R2 |
| shot_is_wide не срабатывает | Второй человек в профиль/затылком → MediaPipe видит 1 лицо → fit не включается | physics |
| REFRAME_SCENE_THRESHOLD=27 | Иногда пропускает мягкие склейки (аниме, студийные переходы); снизить до 20–25 | тюнинг |
| Кэш транскрипции | Каждый новый UI-джоб платит Deepgram заново (нет hash(source) кэша) | Phase 1 |
| Дорогой reframe на CPU | ASD@25fps + PySceneDetect: ~2× длительности клипа на CPU | Phase 1 |

### ✅ Устранённые баги (для справки)
- **Флеш fill↔fit** — Δ=0 по конструкции (reframe v3, 2026-06-10)
- **ASD молча не работал** — torch был в optional extras, `uv sync` удалял (2026-06-10)
- **face_fps=5 → случайный ASD** — исправлено на 25.0 (модель обучена на 25fps)
- **Deepgram WriteTimeout** — `write=None` в httpx.Timeout (2026-06-10)
- **EMA drift от центра** — init = первый реальный cx (не 0.5)
- **AAC priming подлаг** (R1c) — аудио непрерывным `-map 0:a`
- **Чёрный кадр на переходе** (R1c) — `aligned_start` = frame-boundary

---

## 10. Что делать дальше (для следующей сессии)

> 🎯 **Контекст:** Phase 0 полностью готов. Качество reframe доведено до Δ=0 флешей.
> Следующий приоритет — довести до состояния «можно показать инвесторам / пользователям» (MVP ship).

### Открытые задачи (примерный приоритет)

| # | Задача | Стоимость | Примечания |
|---|--------|-----------|------------|
| 1 | **E2E тест dod01 через UI** (часовой подкаст) | ~$0.25 | Deepgram timeout теперь починен; нужен реальный run |
| 2 | **Кэш транскрипции по hash(source)** | $0 | Повторные прогоны не платят Deepgram |
| 3 | **K1 — RQ+Redis очередь** | — | Для продакшна; план в `docs/superpowers/plans/...k1-queue.md` |
| 4 | **Деплой** | — | Нет плана. Воркер с torch/MediaPipe тяжёлый (1+ ГБ RAM). VPS или облако. |
| 5 | **Task 6 — zoom-переход** | $0 | GATED: только после «флеши ушли» от фаундера |
| 6 | **Двойные субтитры** | $0 | Детект вшитых субтитров и пропуск stage4 |
| 7 | **UI полировка** | — | Превью клипа прямо в браузере (video element), мобильная вёрстка |

### Ключевые ключи в `.env` (корень репо)
```
DEEPGRAM_API_KEY=...
GEMINI_API_KEY=...
LLM_MODEL=gemini-flash-latest   # ⚠️ не менять на 2.5-pro — квота 0 на free tier
YTDLP_COOKIES_FILE=C:\Users\user\Desktop\ClipClow\www.youtube.com_cookies.txt
```

### Экономика (33 мин видео)
- Транскрипция (Deepgram Nova): ~$0.14
- LLM (Gemini Flash): ~$0.016
- Итого: **~$0.16/прогон**

---

---

## 11. Файлы плана — для следующего агента

| Файл | Что читать | Порядок |
|------|----------|---------|
| `docs/HANDOFF.md` | **Этот файл** — состояние, как запустить, что работает | 1 |
| `CLAUDE.md` | Правила + полный журнал прогресса | 2 |
| `CLIPFLOW_DEV_PLAN.md` | Подробный план фаз (A→J + Phase 1) | 3 (если нужно) |
| `docs/BENCHMARKS.md` | Скорость/стоимость/качество по модели | по запросу |
| `docs/EXTERNAL_SERVICES.md` | Deepgram/Gemini/yt-dlp — что/где/чем свапнуть | по запросу |

**222 unit-тестов, `just check` зелёный (2026-06-11, коммит `365145e`)**
