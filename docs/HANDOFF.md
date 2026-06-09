# ClipFlow — HANDOFF (читать ПЕРВЫМ в новой сессии, вместе с CLAUDE.md)

> Это операционная «правда» проекта на 2026-06-09. Цель: новый агент за 2 минуты понимает
> состояние, умеет запустить и продолжить — без перечитывания всей истории. Детальный
> журнал и правила — в `CLAUDE.md`. План — `CLIPFLOW_DEV_PLAN.md`. Бенчмарки — `docs/BENCHMARKS.md`.

## 1. Что это
Длинное YouTube-видео → 3–10 вертикальных 9:16-клипов с прожжёнными субтитрами.
Пайплайн: **download → transcribe → LLM выбирает моменты → reframe 9:16 → субтитры → render**.
Монорепо: `apps/web` (Next 16/React 19/TS/Tailwind v4), `services/worker` (Python 3.12 /
FastAPI / uv, пакет `app`), `packages/shared` (TS-типы, codegen из `app/models.py`).

## 2. Статус (что готово)

### Phase 0 (A→J) ЗАВЕРШЁН
Сквозной пайплайн + web UI + worker REST/SQLite, проверен e2e.

### Flash Fix — Cut-Aligned Reframe ✅ СДЕЛАН (2026-06-09)

**Был баг:** режим fill↔fit переключался на сетке 5fps-сэмплирования (кратно 0.2с),
не совпадая с реальными склейками → флеш (1 кадр «обычного» видео) на КАЖДОМ переходе.

**Доказано диагностикой:** граница `fill→fit` в `comedy01/clip_01` стояла на t=11.6с,
ближайшая реальная склейка — t=10.44с, рассинхрон **29 кадров**. В окне ±1с склеек нет.

**Фикс (как у Google AutoFlip / OpusClip):**
1. `detect_cuts` (ffmpeg scene-detect, уже был) → frame-accurate склейки
2. `build_shots` (уже был) → интервалы планов
3. **`decide_shot_mode`** (NEW, PURE) — режим `fill`/`fit` решается **ОДИН РАЗ на план** (большинство кадров по `classify_frame`)
4. **`build_shot_trajectory`** (NEW, PURE) — EMA-пан ВНУТРИ плана; сбрасывается на каждом плане (инициализируется первым реальным cx лица, не 0.5)
5. **`build_regions_from_shots`** (NEW, PURE) — собирает `TrackRegion` по планам + `merge_short_regions` (анти-флеш рапид-монтажа)
6. `samples_in_shot` (NEW, PURE) — вспомогательная фильтрация сэмплов в окно плана

**Результат:** все 3 границы режима `comedy01/clip_01` — Δ **0 кадров** от реальных склеек.

Коммиты: `10d1900` (samples_in_shot) → `35e7f4d` → `bbf08bd` → `406e61d` → `a57d1a7`
(wire-in + config) → `e40fa2d` (docs) → `e044f2b` (EMA init fix) → `5659e5b`.

### Другие улучшения (ранее):
- **K3 авто-язык** — Deepgram `detect_language` (lang=None), RU работает.
- **Больше клипов** — `max_clips=8` (config) + промпт расширен.
- **eval-харнесс** — `app/eval.py` (рубрика C1–C8, Q).
- **C** — clean-start: клип не начинается с хвоста предложения.
- **B** — курирование в UI: степпер клипов + чекбоксы + «скачать выбранные».
- **Active-speaker (ASD)** — за флагом `REFRAME_SPEAKER`. Default = off.
- **R1b** — широко/тайт по геометрии лиц (1 человек → fill; 2+ разнесённых → fit).

**Отложено:** K1 (RQ+Redis очередь) — план в `docs/superpowers/plans/...k1-queue.md`, не начат.

**GATED (Task 6):** плавный zoom-переход (~0.3с ease-in-out) для intra-shot wide-reveal.
Делать ТОЛЬКО после того, как фаундер подтвердит, что основные флеши ушли.

## 3. КАК ЗАПУСТИТЬ (Windows, PowerShell-инструмент)

**⚠️ ОБЯЗАТЕЛЬНО: обновлять PATH в каждом PowerShell-вызове:**
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
```

**⚠️ ПОСЛЕ ЛЮБОЙ ПРАВКИ КОДА ВОРКЕРА — ПЕРЕЗАПУСТИ ВОРКЕР.**
uvicorn запущен БЕЗ `--reload` → старый код остаётся в памяти. Гасить по порту:
```powershell
foreach ($p in 3000,8000){ Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue | Select -Expand OwningProcess -Unique | %{ Stop-Process -Id $_ -Force } }
```

**Поднять стек для теста (UI):**
```powershell
# worker (из services/worker):
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# worker с active-speaker (ASD, torch, медленнее ~2×):
$env:REFRAME_SPEAKER="true"
uv run --extra asd uvicorn app.main:app --host 0.0.0.0 --port 8000

# web (из корня):
Set-Location "C:\Users\user\Desktop\ClipClow"
pnpm --filter web dev
```
Тестировать: **http://localhost:3000**

**CLI e2e (дёшево, кэш):** из `services/worker`:
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run python -m app.run comedy01
# стадии 0-2 кэшируются → повторный прогон не платит Deepgram/Gemini
```

**Гейт перед коммитом (ОБЯЗАТЕЛЬНО зелёный):**
```powershell
Set-Location "C:\Users\user\Desktop\ClipClow"
just check
```

## 4. Тестовые данные (`services/worker/data/`, gitignored)

| Датасет | Описание | Кэш |
|---------|----------|-----|
| `comedy01` | RU интервью «Звёзды против мошенников» (~33 мин, Щербаков) | source + transcript + segments + clips |
| `sample01` | EN «Mafia show» (мультиспикер, ~33 мин) | source + transcript + segments + clips |
| `test01` | EN короткое видео (193с, 504 слова) | source + transcript + segments + clips |

`comedy01` — основной для теста reframe без оплаты. `test01` — лёгкий для быстрой итерации.
Для перегенерации клипов (без повторной оплаты): **удали `data/<job>/clips/`** и запусти `app.run <job>`.

## 5. Архитектура (где что)

```
apps/web/                    — Next 16 фронт
  app/page.tsx               — state-машина idle→tracking→done→error
  components/                — SourceForm (степпер), ClipGrid (чекбоксы), ClipCard, JobProgress…
  lib/                       — api (useJob polling 2.5с/3-фейла), format утилиты
  app/api/mock/              — мок-воркер для dev без реального воркера

packages/shared/             — TS-типы (ТОЛЬКО codegen, не трогать руками)
  contract.json              — JSON-схема из models.py
  src/types.ts               — TypeScript типы

services/worker/
  app/
    models.py                — ЕДИНЫЙ источник типов (контракт). Менять здесь → just types
    config.py                — pydantic-settings, fail-fast при отсутствии ключа, lru_cache
    errors.py                — JobError (нет тихих фолбэков, правило №8)
    db.py                    — SQLite, row_to_wire
    tasks.py                 — фоновый worker (asyncio), обновляет статус
    main.py                  — FastAPI: POST/GET /jobs, /healthz, CORS :3000, StaticFiles /media
    run.py                   — СКЛЕЙКА стадий 0→5 (оркестрация, не логика). job.json + runs.jsonl

    pipeline/
      stage0_import.py       — yt-dlp download + ffprobe meta (SourceMeta)
                               yt-dlp куки: YTDLP_COOKIES_FILE (приоритет) или YTDLP_COOKIES_BROWSER
      stage1_transcribe.py   — Deepgram REST /v1/listen через httpx (НЕ SDK!)
      stage2_select.py       — Gemini structured output → сегменты. Промпт в prompts/
      stage3_reframe.py      — Cut-Aligned Reframe (см. §6). TrackPoint/TrackRegion.
      stage4_captions.py     — ASS субтитры (Montserrat 90, upper, group_words)
      stage5_render.py       — Engine A (ffmpeg filter_complex) / Engine B (cv2 pipe)

    asd/                     — Active-speaker detection (LR-ASD вендоринг, MIT)
      _vendor/               — вендоренное ядро (torch-зависимости, gitignored)
      scorer.py              — ленивый torch, optional asd-экстра
    pipeline/asd_reframe.py  — I/O: MediaPipe@25fps → tracks → окна говорящего (нужен asd-экстра)

  prompts/
    select_moments.v1.txt    — промпт Gemini (крутить без перекодировки)

  tests/unit/                — 180 тестов (pytest), все зелёные
```

## 6. Cut-Aligned Reframe в деталях

### Поток данных `reframe_segment` (основной путь, speaker=False)

```
source.mp4 + (start, end)
  │
  ├─ sample_faces_continuous(video, start, end, fps=5.0)
  │    └─ ffmpeg: кадры каждые 1/fps сек → PNG в temp-dir
  │    └─ MediaPipe Tasks API FaceDetector → (t, [(cx, w_frac), …])
  │         bbox в ПИКСЕЛЯХ / ширина кадра = доли [0..1]
  │         t — клип-relative (0-based), ВСЕ лица кадра
  │
  ├─ detect_cuts(video, start, end, threshold=0.3)
  │    └─ ffmpeg select='gt(scene,thr)',showinfo → pts_time список
  │    └→ list[float]  клип-relative времена склеек
  │
  ├─ build_shots(cuts, duration)
  │    └─ PURE. [0.0] + cuts + [duration] → [(t0,t1), …] интервалы планов
  │
  ├─ build_regions_from_shots(shots, raw_samples, crop_w_frac, smoothing, min_hold_sec, …)
  │    └─ PURE. Для каждого плана (t0, t1):
  │         samples_in_shot(raw_samples, t0, t1)   → сэмплы плана [t0,t1)
  │         decide_shot_mode(seg, crop_w_frac, wide_ratio=0.5)
  │           └─ majority-vote classify_frame → "fill" | "fit"
  │                нет сэмплов → fit
  │                mode_setting override ("fill"/"fit") уважается
  │         if fill:
  │           build_shot_trajectory(seg, smoothing)
  │             └─ cx крупнейшего лица, EMA (alpha=smoothing)
  │                  INIT = первый реальный cx (НЕ 0.5)  ← ключевой фикс бага пана
  │                  None (нет лица) → держим last
  │             └→ tuple[TrackPoint(t, "fill", cx)]
  │           fallback: (TrackPoint(t0, "fill", 0.5),) если нет ни одного лица
  │           → TrackRegion(t0, t1, "fill", points)
  │         else (fit):
  │           → TrackRegion(t0, t1, "fit", ())
  │    └─ merge_short_regions(regions, min_hold_sec=1.5)
  │         план < min_hold → поглощается предыдущим (анти-флеш на рапид-монтаже)
  │    └→ list[TrackRegion]
  │         ГРАНИЦА РЕЖИМА = ГРАНИЦА ПЛАНА = РЕАЛЬНАЯ СКЛЕЙКА → флеша нет
  │
  ├─ [speaker=True + face_found]:
  │    windows_to_shot_plan() → shot_plan_to_regions()
  │    ASD-путь: НЕ использует build_regions_from_shots; строит свои TrackRegion.
  │
  └─ _write_reframe_json: {regions:[{t0,t1,mode,points:[{t,mode,cx},...]},...]}
```

**Легаси-функции** `build_trajectory` / `build_regions` сохранены в коде для обратной совместимости
(в production не вызываются; ASD-адаптер использует `shot_plan_to_regions`).

### Поток данных `render_clip` (Engine A / B)

**Engine A** (default, `REFRAME_ENGINE=A`, ~4–8с/клип):
```
regions + source.mp4
  │
  ├─ build_smooth_filter(regions, src_w, src_h, fps, ass_name)
  │    └─ PURE. filter_complex строка:
  │         [0:v]setpts=PTS-STARTPTS,split=N[a0][a1]…
  │         fill-регион → trim(start_frame, end_frame), crop={piecewise x-expr}, scale, setsar=1
  │         fit-регион  → blur-bg + letterbox overlay (уникальные лейблы [bg{i}][fg{i}])
  │         concat=N → subtitles={ass} → [outv]
  │
  ├─ build_fill_crop_expr(points, t0_offset, src_w, src_h)
  │    └─ PURE. piecewise-constant if():
  │         if(lt(t\,0.200)\,312\,...) ← запятые \, для filtergraph
  │         t = клип-время, t0_offset = старт региона
  │
  └─ build_single_pass_cmd + _run_ffmpeg → clips/<id>.mp4
       -ss {aligned_start} -i source -t {dur}
       -filter_complex {fc} -map [outv] -map 0:a   ← аудио НЕПРЕРЫВНЫМ (нет подлага)
       -c:v libx264 -crf 20 -c:a aac -b:a 128k -movflags +faststart
       aligned_start = round(seg_start * fps) / fps  ← frame-boundary align
```

**Engine B** (`REFRAME_ENGINE=B`, ~20–27с/клип):
```
source.mp4
  │
  ├─ cv2.VideoCapture → покадрово:
  │    _get_region_at(t) → текущий TrackRegion
  │    _interp_cx(region, t) → cx (линейная интерполяция между TrackPoint-ами)
  │    fill: compute_crop_window(cx) → crop numpy array
  │    fit:  resize + blur-bg + letterbox
  │    └→ raw BGR frame → ffmpeg stdin (pipe)
  │
  └─ ffmpeg: -f rawvideo stdin → libx264 + aac (из source) → mp4
```

**Ключевые инварианты рендера:**
- `aligned_start = round(seg_start * fps) / fps` → trim-кадры точно на границе кадра
- fit-лейблы уникальны `[bg{i}]`, `[fg{i}]` (глобальные имена → коллизия на 2+ fit)
- `setsar=1` на каждом сегменте (fill/fit дают разный SAR → без него concat падает)
- Аудио из `0:a` непрерывным — не режется по сегментам (нет priming-подлага)

### TrackPoint / TrackRegion (frozen dataclasses)

```python
@dataclass(frozen=True)
class TrackPoint:
    t: float           # клип-relative время (секунды)
    mode: str          # "fill" | "fit"
    cx: float | None   # центр лица [0..1]; None = нет лица / fit-точка

@dataclass(frozen=True)
class TrackRegion:
    t0: float
    t1: float
    mode: str          # "fill" | "fit"
    points: tuple[TrackPoint, ...]  # fill: траектория cx; fit: ()
```

`reframe_<clip_id>.json` → `{regions:[{t0,t1,mode,points:[{t,mode,cx},...]},...] }`

## 7. Кнобы качества (`.env` / `config.py`)

| Переменная | Дефолт | Описание |
|------------|--------|----------|
| `REFRAME_ENGINE` | `A` | `A` = ffmpeg expr (быстро); `B` = cv2 pipe (медленно, frame-exact) |
| `REFRAME_FACE_FPS` | `5.0` | Кол-во сэмплов лиц в сек (выше = точнее / медленнее) |
| `REFRAME_SMOOTHING` | `0.15` | EMA коэф. (0=frozen; 1=без сглаживания; 0.15=дефолт) |
| `REFRAME_MIN_HOLD_SEC` | `1.5` | Анти-флеш: план короче → поглощается предыдущим |
| `REFRAME_WIDE_RATIO` | `0.5` | Доля кадров с широкой геометрией для решения "fit" на план |
| `REFRAME_DEAD_ZONE` | `0.12` | Tolerance слияния (ASD speaker-путь) |
| `REFRAME_CUT_THRESHOLD` | `0.4` | Порог scene-detect (выше = чувствительнее к мягким склейкам) |
| `REFRAME_MODE` | `auto` | `auto` / `fill` / `fit` глобально |
| `REFRAME_SPEAKER` | `false` | Наведение на говорящего (ASD, нужен `--extra asd`) |
| `REFRAME_SPEAKER_CROP_SCALE` | `0.55` | Ширина кропа вокруг лица (ASD-путь) |
| `YTDLP_COOKIES_FILE` | `` | Путь к Netscape cookies.txt (приоритет над browser) |
| `YTDLP_COOKIES_BROWSER` | `edge` | `edge`/`firefox`/`chrome`/`""`. Chrome 127+ = DPAPI-баг |
| `LLM_MODEL` | `gemini-flash-latest` | ⚠️ gemini-2.5-pro = квота 0 на free tier |
| `MAX_CLIPS` | `8` | Макс. кандидатов от Gemini |

**Тюнинг без оплаты:**
```powershell
# comedy01 или test01 — кэш, $0; удали clips/ для перерендера
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
Remove-Item -Recurse -Force data\comedy01\clips -EA SilentlyContinue
uv run python -m app.run comedy01
# Посмотреть регионы clip_01:
Get-Content data\comedy01\reframe_clip_01.json
# Ожидаемо: boundaries совпадают с реальными склейками (не кратны 0.2)
```

## 8. YouTube куки (ВАЖНО для скачивания)

Chrome 127+ и Edge сломали DPAPI-расшифровку кук (`--cookies-from-browser` падает).

**Надёжный путь (cookies.txt):**
1. Установить расширение **"Get cookies.txt LOCALLY"** в Chrome
2. Открыть youtube.com (залогиниться)
3. Нажать расширение → Export → сохранить `.txt` (Netscape-формат, не JSON!)
4. В `.env`: `YTDLP_COOKIES_FILE=C:\Users\user\Desktop\ClipClow\www.youtube.com_cookies.txt`

Файл `.txt` начинается с `# Netscape HTTP Cookie File` — это правильный формат.

## 9. Известные проблемы и грабли

### Критичные грабли инструментов

| Грабля | Правило |
|--------|---------|
| PowerShell держит cwd между вызовами | Всегда абсолютные пути или `Set-Location` в начале |
| Bash-инструмент не видит ffmpeg/just (winget PATH) | Прогоны пайплайна — через PowerShell с PATH-refresh |
| Коммит из Bash → кириллица `?????` + BOM | Коммитить ТОЛЬКО из PowerShell; сообщение через `-m "ascii"` или файл + `-F` |
| pre-commit ruff-format переформатирует → хук падает | После `reformatted N files` → `git add` + повторный коммит |
| `Out-File -Encoding utf8NoBOM` не работает в PS 5.1 | Использовать `-Encoding utf8` (PS 5.1 добавит BOM, но `git commit -F` его переживает) |
| opencv-python-headless + opencv-contrib-python → битый cv2 | Держать ОДИН opencv-пакет. Сейчас: contrib (mediapipe его тянет) |
| uv sync без `--extra asd` удаляет torch → mypy падает | В dev: `uv sync --extra asd` |

### Известные ограничения

| Баг / ограничение | Описание | Приоритет |
|-------------------|----------|-----------|
| ASD-путь на старых cuts | speaker-путь (`asd_reframe.py`) не использует cut-aligned `build_regions_from_shots`; строит регионы через `shot_plan_to_regions` (своя логика) | Phase 1 |
| Двойные субтитры | Видео с вшитыми субтитрами → наши прожигаются поверх | R2 |
| Deepgram 408 SLOW_UPLOAD | >19 мин (37 МБ wav) → таймаут загрузки | R2 |
| shot_is_wide не срабатывает | Второй человек в профиль/затылком → MediaPipe видит 1 лицо → fit не включается | physics |
| `REFRAME_CUT_THRESHOLD=0.4` может пропустить мягкие склейки | Понизить до 0.25–0.3 на видео с незаметными монтажными переходами | тюнинг |

### ✅ УСТРАНЁННЫЕ баги (для справки)
- **Флеш fill↔fit** — ключевой баг сессии 2026-06-09. Граница режима теперь = реальная склейка. Δ=0 кадров.
- **EMA drift от центра** — при reset EMA на каждом плане инициализировалась в 0.5, давая пан к реальному лицу. Исправлено: init = первый реальный cx.
- **AAC priming подлаг** (R1c) — per-shot рендер резал аудио. Исправлено: аудио непрерывным `-map 0:a`.
- **Чёрный кадр на переходе** (R1c) — дробный старт сегмента → 1 кадр с мимо. Исправлено: `aligned_start`.

## 10. БЛИЖАЙШЕЕ (что делать в новой сессии)

> 🎯 **Приоритет #1:** Фаундер тестирует клипы с новым cut-aligned reframe.
> Ключевой вопрос: основные флеши ушли? Если да → можно двигаться дальше.

**Task 6 (GATED):** плавный zoom-переход (~0.3с ease-in-out) для intra-shot wide-reveal.
- Разблокировать ТОЛЬКО после вердикта фаундера «флеши ушли».
- Plan in: `docs/superpowers/plans/2026-06-09-reframe-cut-snap-flash-fix.md` Task 6.
- Реализация: `transition_in: str = "hard"/"zoom"` поле в `TrackRegion`; Engine B анимирует.

**После стабильного reframe:**
1. **Кэш транскрипции по hash(source)** — UI-джоб каждый раз платит Deepgram заново.
2. **R2 — LLM на визуал** — Gemini для видео с экшеном (не только подкасты).
3. **«Тот человек»** — детект тела (не только лица), фронтальный = главный.
4. **K1** — RQ+Redis очередь (план в `docs/superpowers/plans/...k1-queue.md`).

---
- Ключи в `.env` (корень): `DEEPGRAM_API_KEY`, `GEMINI_API_KEY`, `LLM_MODEL=gemini-flash-latest`
- Экономика: ~$0.16/видео (33 мин), доминанта — транскрипция ($0.14). Бенчмарки → `docs/BENCHMARKS.md`
- **180 unit-тестов**, `just check` зелёный (2026-06-09)
