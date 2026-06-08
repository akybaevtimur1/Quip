# ClipFlow — HANDOFF (читать ПЕРВЫМ в новой сессии, вместе с CLAUDE.md)

> Это операционная «правда» проекта на 2026-06-08. Цель: новый агент за 2 минуты понимает
> состояние, умеет запустить и продолжить — без перечитывания всей истории. Детальный
> журнал и правила — в `CLAUDE.md`. План — `CLIPFLOW_DEV_PLAN.md`. Бенчмарки — `docs/BENCHMARKS.md`.

## 1. Что это
Длинное YouTube-видео → 3–10 вертикальных 9:16-клипов с прожжёнными субтитрами.
Пайплайн: **download → transcribe → LLM выбирает моменты → reframe 9:16 → субтитры → render**.
Монорепо: `apps/web` (Next 16/React 19/TS/Tailwind v4), `services/worker` (Python 3.12 /
FastAPI / uv, пакет `app`), `packages/shared` (TS-типы, codegen из `app/models.py`).

## 2. Статус (что готово)

### Phase 0 (A→J) ЗАВЕРШЁН
Сквозной пайплайн + web UI + worker REST/SQLite, проверен e2e. Детали — в CLAUDE.md журнале.

### Качество (итерации после Phase 0)

**R1 Reframe 2.0 — ✅ СДЕЛАН (2026-06-08, коммиты `352284c`→`f6bd15c`)**

Полная переработка reframe-стадии с нуля. Суть: **per-shot модель** — кроп постоянен внутри
плана источника, меняется РОВНО на склейке. Нет плавного пана, нет time-expression в ffmpeg.

Что изменилось от начала до конца R1:
- **R1.1** — PySceneDetect ContentDetector вместо сырого ffmpeg scene-порога (кадроточные склейки).
- **R1.2** — pure `build_shot_plan`: режим (`fill`/`fit`) решается НА ШОТ по геометрии лиц.
- **R1.3b** — per-shot рендер: каждый шот = отдельный сегмент → concat-демуксер + burn субтитров.
  ⛔ Этот подход УБРАН в R1c (он давал аудио-подлаги и чёрные кадры на стыках).
- **R1b** — геометрия лиц: 2+ разнесённых лица → fit широко; одно/кластер → fill full-bleed.
- **R1c** — ОДИН проход рендера (корневой фикс): аудио непрерывным `-map 0:a`, видео через
  `split→trim(frame-exact)→crop/fit→concat`-ФИЛЬТР. Старт выровнен на кадр. Подлаги ушли.
- **R1d** — `stabilize_plan`: короткий шот < `REFRAME_MIN_HOLD_SEC` поглощается предыдущим.
  Гасит рапидное чередование fill↔fit на коротких шотах (0.4–0.8с) = «мигающий» кроп.

**Текущее состояние R1: ждём вердикт фаундера** (флеши/аудио ушли? правильный человек?)

**Другие улучшения:**
- **K3 авто-язык** — Deepgram `detect_language` (lang=None), RU работает. `9af07ec`.
- **Больше клипов** — `max_clips=8` (config) + промпт расширен. `b8e078d`.
- **eval-харнесс** — `app/eval.py` (рубрика C1–C8, Q). `358054d`.
- **D2** — cut-aware reframe (заменён R1). `abd7760`.
- **C** — clean-start: клип не начинается с хвоста предложения. `100693c`.
- **B** — курирование в UI: степпер клипов + чекбоксы + «скачать выбранные». `0829bea`.
- **Active-speaker (ASD)** — наведение на ГОВОРЯЩЕГО, за флагом `REFRAME_SPEAKER`.
  ⚠️ Speaker-путь всё ещё на ffmpeg `detect_cuts` (НЕ PySceneDetect). Default = off.
  `5f1011f`/`70f02b1`/`7e1690b`.

**Отложено**: K1 (RQ+Redis очередь) — план в `docs/superpowers/plans/...k1-queue.md`, не начат.

## 3. КАК ЗАПУСТИТЬ (Windows, PowerShell-инструмент)

**⚠️⚠️ ОБЯЗАТЕЛЬНО: обновлять PATH в каждом PowerShell-вызове:**
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
```

**⚠️⚠️ ПОСЛЕ ЛЮБОЙ ПРАВКИ КОДА ВОРКЕРА — ПЕРЕЗАПУСТИ ВОРКЕР.**
uvicorn запущен БЕЗ `--reload` → старый код остаётся в памяти. Проверить через reframe_<clip>.json
формат: должен быть `{shots:[…]}`, а не `{mode,crop}`. Убить + запустить заново (ниже).

**Поднять стек для теста (UI):**
```powershell
# worker БЫСТРЫЙ (largest-face, без torch): из services/worker
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
cd C:\Users\user\Desktop\ClipClow\services\worker
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# worker с active-speaker (ASD, torch, медленнее ~2×):
$env:REFRAME_SPEAKER="true"
uv run --extra asd uvicorn app.main:app --host 0.0.0.0 --port 8000

# web: из корня
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
cd C:\Users\user\Desktop\ClipClow
pnpm --filter web dev
```
Тестировать: **http://localhost:3000**

**Убить зомби-серверы по порту:**
```powershell
foreach ($p in 3000,8000){ Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue | Select -Expand OwningProcess -Unique | %{ Stop-Process -Id $_ -Force } }
```

**CLI e2e (дёшево, кэш):** из `services/worker`:
```powershell
uv run python -m app.run comedy01
# стадии 0-2 кэшируются → повторный прогон не платит Deepgram/Gemini
# удалить data/comedy01/segments.json → пересобрать выбор (Gemini ~$0.016)
```

**Гейт перед коммитом (ОБЯЗАТЕЛЬНО зелёный):**
```powershell
cd C:\Users\user\Desktop\ClipClow\services\worker
just check
```

## 4. Тестовые данные (`services/worker/data/`, gitignored)

| Датасет | Описание | Кэш |
|---------|----------|-----|
| `comedy01` | RU интервью «Звёзды против мошенников» (Щербаков, ~33 мин) | source + transcript + segments + clips |
| `sample01` | EN «Mafia» (мультиспикер) | source + transcript + segments + clips |

`comedy01` — основной для теста reframe без оплаты. Все стадии 0–2 уже прогнаны.

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
      stage1_transcribe.py   — Deepgram REST /v1/listen через httpx (НЕ SDK!)
      stage2_select.py       — Gemini structured output → сегменты. Промпт в prompts/
      stage3_reframe.py      — Reframe per-shot: PySceneDetect + MediaPipe лица + ShotPlan
      stage4_captions.py     — ASS субтитры (Montserrat 90, upper, group_words)
      stage5_render.py       — Один проход ffmpeg: split→trim→crop/fit→concat→subtitles

    asd/                     — Active-speaker detection (LR-ASD вендоринг, MIT)
      _vendor/               — вендоренное ядро (~ГБ torch-зависимости, gitignored)
      scorer.py              — ленивый torch, optional asd-экстра
    pipeline/stage3_speaker.py — PURE IOU-трекинг лиц + выбор говорящей дорожки (без torch)
    pipeline/asd_reframe.py  — I/O: MediaPipe@25fps → tracks → окна говорящего (нужен asd-экстра)

  prompts/
    select_moments.v1.txt    — промпт Gemini (крутить без перекодировки)

  tests/unit/
    test_stage3_reframe.py   — ~60+ тестов: cuts, shots, plan, stabilize, merge, wide
    test_stage5_render.py    — ~10 тестов: filter_complex, single_pass_cmd
    …                        — остальные стадии аналогично
```

## 6. Reframe в деталях (для понимания кода)

### Поток данных `reframe_segment`

```
source.mp4 + (start, end)
  │
  ├─ detect_scene_cuts()  ← PySceneDetect ContentDetector, frame-accurate
  │    └→ list[float]  # клип-относительные склейки (секунды)
  │
  ├─ build_shots()  ← cuts → список интервалов [(t0, t1), …]
  │
  ├─ sample_faces()  ← ffmpeg кадры (2fps) + MediaPipe Tasks API
  │    └→ list[(t, [(cx, w_frac), …])]  # ВСЕ лица: центр X + ширина (доли кадра)
  │
  ├─ build_shot_plan()  ← face_frames + shots → логика per-shot:
  │    нет лиц → fit
  │    2+ разнесённых (span > 9:16-ширина) → fit широко (оба видны)
  │    одно/кластер → fill на крупнейшем (медиана)
  │    └→ list[ShotPlan]
  │
  ├─ [speaker=True] windows_to_shot_plan()  ← ASD-путь, заменяет fill-центры
  │
  ├─ merge_shot_plan(tolerance=dead_zone)   ← сливает смежные равные (статика → 1 кодировка)
  ├─ stabilize_plan(min_hold_sec)           ← короткие шоты поглощает → нет «мигания»
  └─ merge_shot_plan(tolerance=dead_zone)   ← второй проход после stabilize

Результат: list[ShotPlan] → пишется в reframe_<clip_id>.json
```

### Поток данных `render_clip` (один проход, R1c)

```
source.mp4 + aligned_start + shots
  │
  ├─ build_reframe_filter()  ← filter_complex строка:
  │    [0:v]setpts=PTS-STARTPTS,split=N[a0][a1]…
  │    [a{i}]trim=start_frame={f0}:end_frame={f1},setpts=PTS-STARTPTS,{crop_or_fit},setsar=1[s{i}]
  │    [s0][s1]…concat=n=N:v=1[cv];[cv]subtitles={ass}[outv]
  │
  ├─ build_single_pass_cmd()  ← ffmpeg -ss {aligned_start} -i source -t {dur}
  │    -filter_complex {fc} -map [outv] -map 0:a  ← аудио НЕПРЕРЫВНЫМ
  │    -c:v libx264 -crf 20 -c:a aac -b:a 128k
  │
  └─ _run_ffmpeg()  → clips/<clip_id>.mp4
```

**Ключевые инварианты:**
- `aligned_start = round(seg_start * fps) / fps` → trim-кадры совпадают с реальными склейками
- fit-шот использует уникальные лейблы `[bg{i}]`, `[fg{i}]` (глобальные → коллизия на 2+ fit)
- `setsar=1` на КАЖДОМ сегменте (fill и fit дают разный sample-aspect-ratio → concat без него падает)
- аудио `-map 0:a` — никогда не режем (непрерывный поток → ноль AAC-прайминга = ноль подлагов)

### ShotPlan (frozen dataclass)

```python
@dataclass(frozen=True)
class ShotPlan:
    t0: float       # старт шота (клип-relative, секунды)
    t1: float       # конец шота
    mode: str       # "fill" | "fit"
    center: float | None  # доля X кадра (только fill); fit → None
```

`reframe_<clip_id>.json` → `{shots: [{t0, t1, mode, center}, …]}`

## 7. Кнобы качества (`.env` / `config.py`)

| Переменная | Дефолт | Описание |
|------------|--------|----------|
| `REFRAME_SCENE_THRESHOLD` | 27.0 | ContentDetector порог (выше → меньше ложных склеек) |
| `REFRAME_MIN_SCENE_SEC` | 0.4 | Мин. длина плана (анти-дребезг коротких шотов) |
| `REFRAME_MIN_HOLD_SEC` | 1.5 | Анти-флеш: шот короче → поглощается предыдущим |
| `REFRAME_DEAD_ZONE` | 0.12 | Tolerance слияния fill-планов с близким центром |
| `REFRAME_SPEAKER` | false | Наведение на говорящего (ASD, нужен `--extra asd`) |
| `REFRAME_SPEAKER_CROP_SCALE` | 0.55 | Ширина кропа вокруг лица (ASD-путь) |
| `REFRAME_CUT_THRESHOLD` | 0.4 | ffmpeg-порог для SPEAKER-пути (ASD ещё на нём!) |
| `REFRAME_MODE` | auto | auto / fill / fit глобально |
| `LLM_MODEL` | gemini-flash-latest | ⚠️ gemini-2.5-pro = квота 0 на free tier |
| `MAX_CLIPS` | 8 | Макс. кандидатов от Gemini |

**Проверка эффекта без оплаты:**
```powershell
# Прогнать comedy01 (transcript+segments кэшированы)
uv run python -m app.run comedy01

# Посмотреть план шотов clip_01
cat data\comedy01\reframe_clip_01.json
# Ожидаемо: {shots:[{t0,t1,mode,center},...]} — несколько fit-шотов (b-roll широко)
```

## 8. Известные проблемы и грабли

### Критичные грабли инструментов

| Грабля | Правило |
|--------|---------|
| PowerShell держит cwd между вызовами | Всегда абсолютные пути или `Set-Location` в начале |
| Bash-инструмент не видит ffmpeg/just (winget PATH) | Любые прогоны пайплайна — через PowerShell с PATH-refresh |
| Коммит из Bash-инструмента → кириллица `?????` + BOM | Коммитить ТОЛЬКО из PowerShell; сообщение через файл + `-F` |
| pre-commit ruff-format переформатирует → хук падает | После `reformatted N files` → `git add` заново + повторный коммит |
| uv sync без `--extra asd` удаляет torch → mypy падает | В dev-среде: всегда `uv sync --extra asd` |

### Известные баги (не фиксим сейчас)

| Баг | Описание | Приоритет |
|-----|----------|-----------|
| Двойные субтитры | Видео с вшитыми субтитрами → наши прожигаются поверх | R1/R2 |
| Deepgram 408 SLOW_UPLOAD | >19 мин (37 МБ wav) → таймаут | R2-ish |
| shot_is_wide не срабатывает | Второй человек в профиль/затылком → MediaPipe видит 1 лицо | physics |
| Speaker-путь на старых cuts | ASD ещё на ffmpeg detect_cuts, не на PySceneDetect | Phase 1 |

### Deepgram SLOW_UPLOAD (временный обходной путь)
Если видео > 15 мин → может упасть на транскрипции. Варианты:
1. Сжать аудио: `ffmpeg -i source.wav -c:a libmp3lame -q:a 4 source.mp3` (~3× меньше)
2. Deepgram URL-ingest (не через upload, а через ссылку) — TODO в stage1

## 9. БЛИЖАЙШЕЕ (что делать в новой сессии)

> 🎯 **R1 вердикт** — ключевое: фаундер тестирует R1c+R1d. Флеши ушли? Аудио норм?
> Если да → закрыть R1 и двигаться на R2.

1. **R1 вердикт фаундера** — попросить прогнать его видео через UI (воркер на последнем коде).
   Кнобы при необходимости (§7): поднять `REFRAME_MIN_HOLD_SEC` (стабильнее), снизить
   `REFRAME_SCENE_THRESHOLD` (больше склеек) или поднять (меньше ложных).

2. **R2** — stage2 (Gemini) расширить на не-подкасты (визуальные хуки, экшен) + мягкий
   empty-state с диагностикой. См. `docs/ROADMAP.md` R2.

3. **«Тот человек»** — детект тел (не только лиц), фронтальный = главный. Brainstorm был:
   detect PEOPLE (body bbox), frontal-to-camera = main, Gemini hybrid для спорных шотов.
   НЕ реализовано — отложено за «сначала флеши».

4. **Кэш транскрипции по hash(source)** — UI-джоб каждый раз платит Deepgram. Дёшево сделать:
   hash(source.mp4) → ключ кэша; повторные прогоны бесплатны.

- Ключи в `.env` (корень): `DEEPGRAM_API_KEY`, `GEMINI_API_KEY`, `LLM_MODEL=gemini-flash-latest`
- Экономика: ~$0.16/видео (33 мин), доминанта — транскрипция ($0.14). Бенчмарки → `docs/BENCHMARKS.md`.
