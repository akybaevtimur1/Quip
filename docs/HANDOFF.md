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

### V2 Continuous Reframe — ✅ СДЕЛАН (2026-06-09, коммиты `5b59f2e`)

**Полная замена R1 (ShotPlan/PySceneDetect) на непрерывное слежение за лицом.**

Суть: вместо per-shot «кроп держим на плане, прыгаем на склейке» → **exponential smoothing
покадровой позиции лица** (0.15 коэф.). Режим fill/fit решается независимо на каждый сэмпл
по геометрии ВСЕХ лиц кадра (широко vs тайт). Два движка рендера за одним интерфейсом
для A/B бенчмарка.

**Что убрано:** PySceneDetect, `detect_scene_cuts`, `build_shot_plan`, `stabilize_plan`,
`merge_shot_plan` (как основной путь). ShotPlan + `build_shots` + `detect_cuts` СОХРАНЕНЫ
в stage3_reframe.py — ASD speaker-путь их ещё использует.

**Что добавлено:**
- `TrackPoint(t, mode, cx)` + `TrackRegion(t0, t1, mode, points)` — новый контракт данных
- `smooth_centers(samples, smoothing=0.15)` — EMA сглаживание cx (PURE, тестировано)
- `classify_frame(all_faces, crop_w_frac)` — per-frame fit/fill по геометрии (PURE)
- `build_trajectory(raw_samples, ...)` — траектория TrackPoint-ов (PURE)
- `merge_short_regions(regions, min_hold_sec)` — анти-флеш V2: короткий регион поглощается предыдущим (PURE)
- `build_regions(trajectory, ...)` — группировка в TrackRegion (PURE)
- `shot_plan_to_regions(plan)` — адаптер ASD → TrackRegion (PURE)
- **Engine A** (`build_smooth_filter`): ffmpeg filter_complex с piecewise `if(lt(t\,T)\,x0\,x1)`
  для fill-кропа + split→trim→concat. Быстрый (~4–8с/клип).
- **Engine B** (`render_frame_by_frame`): cv2 VideoCapture покадрово → raw BGR pipe → ffmpeg stdin.
  Медленный (~20–27с/клип), но frame-exact.

**Первый успешный прогон (test01, 2026-06-09):**
- Видео 193с 1280×720, 504 слова, $0.006
- 2 клипа: clip_01 (5 регионов, 2 fit, A=7.7с / B=27.1с), clip_02 (4 региона, 1 fit, A=6.8с / B=21.4с)

**⚠️ Качество V2 на оценке фаундера** — Engine A запущен, визуально «ломано двигалась камера».
Engine B переключён для сравнения. Вердикт ожидается.

### Другие улучшения (ранее):
- **K3 авто-язык** — Deepgram `detect_language` (lang=None), RU работает.
- **Больше клипов** — `max_clips=8` (config) + промпт расширен.
- **eval-харнесс** — `app/eval.py` (рубрика C1–C8, Q).
- **C** — clean-start: клип не начинается с хвоста предложения.
- **B** — курирование в UI: степпер клипов + чекбоксы + «скачать выбранные».
- **Active-speaker (ASD)** — за флагом `REFRAME_SPEAKER`. Default = off.

**Отложено:** K1 (RQ+Redis очередь) — план в `docs/superpowers/plans/...k1-queue.md`, не начат.

## 3. КАК ЗАПУСТИТЬ (Windows, PowerShell-инструмент)

**⚠️ ОБЯЗАТЕЛЬНО: обновлять PATH в каждом PowerShell-вызове:**
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
```

**⚠️ ПОСЛЕ ЛЮБОЙ ПРАВКИ КОДА ВОРКЕРА — ПЕРЕЗАПУСТИ ВОРКЕР.**
uvicorn запущен БЕЗ `--reload` → старый код остаётся в памяти.

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

**Убить зомби-серверы по порту:**
```powershell
foreach ($p in 3000,8000){ Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue | Select -Expand OwningProcess -Unique | %{ Stop-Process -Id $_ -Force } }
```

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
| `test01` | EN короткое видео (193с, 504 слова) | source + transcript + segments + clips (V2) |

`comedy01` — основной для теста reframe без оплаты. `test01` — лёгкий для быстрой итерации.

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
      stage3_reframe.py      — V2 Continuous Reframe (см. §6). TrackPoint/TrackRegion.
      stage4_captions.py     — ASS субтитры (Montserrat 90, upper, group_words)
      stage5_render.py       — V2 Engine A (ffmpeg expr) / Engine B (cv2 pipe)

    asd/                     — Active-speaker detection (LR-ASD вендоринг, MIT)
      _vendor/               — вендоренное ядро (torch-зависимости, gitignored)
      scorer.py              — ленивый torch, optional asd-экстра
    pipeline/asd_reframe.py  — I/O: MediaPipe@25fps → tracks → окна говорящего (нужен asd-экстра)

  prompts/
    select_moments.v1.txt    — промпт Gemini (крутить без перекодировки)

  tests/unit/                — 167 тестов (pytest), все зелёные
```

## 6. V2 Reframe в деталях

### Поток данных `reframe_segment` (V2)

```
source.mp4 + (start, end)
  │
  ├─ sample_faces_continuous(video, start, end, fps=5.0)
  │    └─ ffmpeg: кадры каждые 1/fps сек → PNG в temp-dir
  │    └─ MediaPipe Tasks API FaceDetector → (t, [(cx, w_frac), …])
  │         bbox в ПИКСЕЛЯХ / ширина кадра = доли [0..1]
  │         t — клип-relative (0-based от -ss seek)
  │         возвращает ВСЕ лица кадра (нужны для classify_frame)
  │
  ├─ build_trajectory(raw_samples, smoothing=0.15, crop_w_frac, mode_setting="auto")
  │    └─ PURE. На каждый сэмпл:
  │         classify_frame(faces, crop_w_frac) → "fill" | "fit"
  │           нет лиц → fit
  │           2+ лица с span > ширины 9:16 → fit (оба видны)
  │           одно/кластер → fill (наводим на крупнейшее)
  │         smooth_centers(cx_raws, alpha=0.15) → сглаженный cx (EMA)
  │           last = last + alpha*(cx - last)  ← exponential smoothing
  │           None (нет лица) → держим last
  │    └→ list[TrackPoint(t, mode, cx)]
  │
  ├─ build_regions(trajectory, min_hold_sec=1.5)
  │    └─ PURE. Группирует consecutive-mode точки → TrackRegion
  │    └─ merge_short_regions: регион < min_hold_sec поглощается ПРЕДЫДУЩИМ
  │         → анти-флеш: нет мигания fill↔fit на коротких шотах
  │    └→ list[TrackRegion(t0, t1, mode, points)]
  │         fill: points = tuple[TrackPoint] с cx-траекторией
  │         fit:  points = () (пустой кортеж)
  │
  ├─ [speaker=True] windows_to_shot_plan() → shot_plan_to_regions()
  │         ASD-путь: поверх V2, конвертирует ShotPlan → TrackRegion
  │
  └─ _write_reframe_json: {regions:[{t0,t1,mode,points:[{t,mode,cx},...]},...]}
```

### Поток данных `render_clip` (Engine A / B)

**Engine A** (default, `REFRAME_ENGINE=A`, ~4–8с/клип):
```
regions + source.mp4
  │
  ├─ build_smooth_filter(regions, src_w, src_h, fps, ass_name)
  │    └─ PURE. filter_complex строка:
  │         [0:v]setpts=PTS-STARTPTS,split=N[a0][a1]…
  │         fill-регион → [ai]trim=start_frame=F0:end_frame=F1,setpts=…
  │                         crop=W:H:{build_fill_crop_expr(...)}:0,scale=…,setsar=1[si]
  │         fit-регион  → blur-bg + letterbox overlay (уникальные лейблы [bg{i}][fg{i}])
  │         …concat=n=N:v=1[cv];[cv]subtitles={ass}[outv]
  │
  ├─ build_fill_crop_expr(points, t0_offset, src_w, src_h)
  │    └─ PURE. piecewise-constant if() для crop X:
  │         if(lt(t\,0.200)\,312\,if(lt(t\,0.400)\,315\,...\,320))
  │         запятые экранированы \, (filtergraph-синтаксис)
  │         t = клип-время (0-based), t0_offset = регион-старт
  │
  └─ build_single_pass_cmd + _run_ffmpeg → clips/<id>.mp4
       -ss {aligned_start} -i source -t {dur}   ← aligned_start = round(t*fps)/fps
       -filter_complex {fc} -map [outv] -map 0:a  ← аудио НЕПРЕРЫВНЫМ
       -c:v libx264 -crf 20 -c:a aac -b:a 128k -movflags +faststart
```

**Engine B** (`REFRAME_ENGINE=B`, ~20–27с/клип):
```
source.mp4
  │
  ├─ cv2.VideoCapture → покадрово:
  │    _get_region_at(t) → текущий TrackRegion
  │    fill: compute_crop_window(cx, src_w, src_h) → crop numpy array
  │    fit:  resize + blur-bg + letterbox
  │    └→ raw BGR frame → ffmpeg stdin (pipe)
  │
  └─ ffmpeg: -f rawvideo stdin → libx264 + aac (из source) → mp4
```

**Ключевые инварианты:**
- `aligned_start = round(seg_start * fps) / fps` → trim-кадры = реальные склейки
- fit-лейблы уникальны `[bg{i}]`, `[fg{i}]` (глобальные имена → коллизия на 2+ fit)
- `setsar=1` на КАЖДОМ сегменте (fill и fit дают разный SAR → concat без него падает)
- `smooth_centers(alpha=0)` = camera frozen; `alpha=1` = instantaneous jump (нет сглаживания)

### TrackPoint / TrackRegion (frozen dataclasses)

```python
@dataclass(frozen=True)
class TrackPoint:
    t: float           # клип-relative время (секунды)
    mode: str          # "fill" | "fit"
    cx: float | None   # центр лица [0..1]; None = нет лица / fit

@dataclass(frozen=True)
class TrackRegion:
    t0: float
    t1: float
    mode: str          # "fill" | "fit"
    points: tuple[TrackPoint, ...]  # fill: траектория; fit: ()
```

`reframe_<clip_id>.json` → `{regions:[{t0,t1,mode,points:[{t,mode,cx},...]},...] }`

## 7. Кнобы качества (`.env` / `config.py`)

| Переменная | Дефолт | Описание |
|------------|--------|----------|
| `REFRAME_ENGINE` | `A` | `A` = ffmpeg expr (быстро); `B` = cv2 pipe (медленно, frame-exact) |
| `REFRAME_FACE_FPS` | `5.0` | Кол-во сэмплов лиц в сек (выше = точнее / медленнее) |
| `REFRAME_SMOOTHING` | `0.15` | EMA коэф. (0=frozen; 1=нет сглаживания; 0.15=прототип) |
| `REFRAME_MIN_HOLD_SEC` | `1.5` | Анти-флеш: регион короче → поглощается предыдущим |
| `REFRAME_DEAD_ZONE` | `0.12` | Tolerance слияния (ASD speaker-путь) |
| `REFRAME_CUT_THRESHOLD` | `0.4` | ffmpeg-порог для ASD speaker-пути |
| `REFRAME_MODE` | `auto` | `auto` / `fill` / `fit` глобально |
| `REFRAME_SPEAKER` | `false` | Наведение на говорящего (ASD, нужен `--extra asd`) |
| `REFRAME_SPEAKER_CROP_SCALE` | `0.55` | Ширина кропа вокруг лица (ASD-путь) |
| `YTDLP_COOKIES_FILE` | `` | Путь к Netscape cookies.txt (приоритет над browser) |
| `YTDLP_COOKIES_BROWSER` | `edge` | `edge`/`firefox`/`chrome`/`""`. Chrome 127+ = DPAPI-баг |
| `LLM_MODEL` | `gemini-flash-latest` | ⚠️ gemini-2.5-pro = квота 0 на free tier |
| `MAX_CLIPS` | `8` | Макс. кандидатов от Gemini |

**Тюнинг без оплаты:**
```powershell
# comedy01 или test01 — кэш, $0
uv run python -m app.run comedy01
# Посмотреть регионы clip_01:
cat data\comedy01\reframe_clip_01.json
# Ожидаемо: {regions:[{t0,t1,mode,points:[...]},...]}
```

## 8. YouTube куки (ВАЖНО для скачивания)

Chrome 127+ и Edge сломали DPAPI-расшифровку кук (`--cookies-from-browser` падает).

**Надёжный путь (cookies.txt):**
1. Установить расширение **"Get cookies.txt LOCALLY"** в Chrome
2. Открыть youtube.com (залогиниться)
3. Нажать расширение → Export → сохранить `.txt` (Netscape-формат, не JSON!)
4. В `.env`: `YTDLP_COOKIES_FILE=C:\Users\user\Desktop\ClipClow\www.youtube.com_cookies.txt`

Файл `.txt` начинается с `# Netscape HTTP Cookie File` — это правильный формат.
JSON-экспорт (`.json`) yt-dlp не принимает.

## 9. Известные проблемы и грабли

### Критичные грабли инструментов

| Грабля | Правило |
|--------|---------|
| PowerShell держит cwd между вызовами | Всегда абсолютные пути или `Set-Location` в начале |
| Bash-инструмент не видит ffmpeg/just (winget PATH) | Прогоны пайплайна — через PowerShell с PATH-refresh |
| Коммит из Bash → кириллица `?????` + BOM | Коммитить ТОЛЬКО из PowerShell; сообщение через файл + `-F` |
| pre-commit ruff-format переформатирует → хук падает | После `reformatted N files` → `git add` + повторный коммит |
| `!` bash-команда: URL с `&` или перенос строки | URL в PowerShell в кавычках; `&` в URL → `%26` или обрезать `&t=...` |
| opencv-python-headless + opencv-contrib-python → битый cv2 | Держать ОДИН opencv-пакет. Сейчас: contrib (mediapipe его тянет) |
| uv sync без `--extra asd` удаляет torch → mypy падает | В dev: `uv sync --extra asd` |

### Известные баги

| Баг | Описание | Приоритет |
|-----|----------|-----------|
| Камера «ломано» двигается (Engine A) | EMA 0.15 даёт плавный пан — на быстром монтаже выглядит неестественно. Engine B та же логика, но точнее. Возможно нужен иной подход к smoothing | ⚠️ АКТИВНЫЙ |
| Двойные субтитры | Видео с вшитыми субтитрами → наши прожигаются поверх | R2 |
| Deepgram 408 SLOW_UPLOAD | >19 мин (37 МБ wav) → таймаут | R2 |
| shot_is_wide не срабатывает | Второй человек в профиль/затылком → MediaPipe видит 1 лицо | physics |
| Speaker-путь на ffmpeg cuts | ASD speaker-путь не перешёл на V2 траектории | Phase 1 |

## 10. БЛИЖАЙШЕЕ (что делать в новой сессии)

> 🎯 **V2 вердикт** — фаундер тестирует Engine A vs Engine B на своих видео.
> Ключевой вопрос: Engine B (frame-exact) убирает «ломаность» или проблема в EMA-модели?

**Возможные направления после вердикта:**

**Если проблема в EMA-модели («ломаность» = неправильный smoothing):**
- Попробовать `REFRAME_SMOOTHING=0.05` (медленнее реагирует) или `0.3` (быстрее)
- Или сменить модель: median вместо EMA (нечувствителен к выбросам)
- Или держать center НЕПОДВИЖНЫМ внутри короткого окна (dead-zone на изменение)

**Если проблема в fit/fill переключениях:**
- Поднять `REFRAME_MIN_HOLD_SEC=2.5–3.0` (дольше держать режим)
- Или добавить гистерезис: fit→fill только если лицо устойчиво N сэмплов подряд

**Следующие функции (после стабильного reframe):**
1. **Кэш транскрипции по hash(source)** — UI-джоб каждый раз платит Deepgram
2. **R2** — Gemini для не-подкастов (визуальные хуки, экшен) + мягкий empty-state
3. **«Тот человек»** — детект тела (не только лица), фронтальный = главный
4. **K1** — RQ+Redis очередь (план в `docs/superpowers/plans/...k1-queue.md`)

---
- Ключи в `.env` (корень): `DEEPGRAM_API_KEY`, `GEMINI_API_KEY`, `LLM_MODEL=gemini-flash-latest`
- Экономика: ~$0.16/видео (33 мин), доминанта — транскрипция ($0.14). Бенчмарки → `docs/BENCHMARKS.md`
- 167 unit-тестов, `just check` зелёный (2026-06-09)
