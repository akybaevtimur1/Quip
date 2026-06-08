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
- **Phase 0 (A→J) ЗАВЕРШЁН**: сквозной пайплайн + web UI + worker REST/SQLite, проверен e2e.
- **Качество (фидбек фаундера), всё в коммитах:**
  - **D2** — cut-aware reframe: окно держит план, скачок на склейке (не плавает). `abd7760`.
  - **C** — clean-start: клип не начинается с хвоста предложения. `100693c`.
  - **B** — курирование в UI: степпер «сколько клипов» + чекбоксы выбора + «скачать выбранные». `0829bea`.
  - **Active-speaker reframe** — наведение на ГОВОРЯЩЕГО (LR-ASD), ЗА ФЛАГОМ `REFRAME_SPEAKER`.
    `5f1011f`/`70f02b1`/`7e1690b`. ⚠️ **ОТКРЫТО: ждём визуальный вердикт фаундера** (тот ли человек?
    кадр не тесный?) + тюнинг `reframe_speaker_crop_scale` (сейчас 0.55). Стоимость ~2× длительности
    видео на CPU → off по умолчанию (быстрый largest-face D2).
- **Отложено**: K1 (RQ+Redis очередь) — план в `docs/superpowers/plans/2026-06-07-phase1-k1-queue.md`,
  исполнение НЕ начато (выбрали «сначала качество»).

## 3. КАК ЗАПУСТИТЬ (Windows, PowerShell-инструмент)
Каждая команда — с обновлением PATH (бинарники winget видны только так):
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
```
- **Поднять стек для теста (UI):**
  ```powershell
  # worker (active-speaker ВКЛ): из services/worker
  $env:REFRAME_SPEAKER="true"; uv run --extra asd uvicorn app.main:app --host 0.0.0.0 --port 8000
  # worker БЫСТРЫЙ (largest-face, без torch): из services/worker
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
  # web: из корня
  pnpm --filter web dev
  ```
  Тестировать: **http://localhost:3000**. (web/.env.local → NEXT_PUBLIC_WORKER_URL=http://localhost:8000)
- **Убить зомби-серверы по порту** (Next/uvicorn TaskStop НЕ убивает):
  ```powershell
  foreach ($p in 3000,8000){ Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue | Select -Expand OwningProcess -Unique | %{ Stop-Process -Id $_ -Force } }
  ```
- **CLI e2e (дёшево, кэш):** из services/worker: `uv run python -m app.run comedy01`
  (стадии 0–2 кэшируются по наличию source.mp4/transcript.json/segments.json → не платим повторно).
  Удалить `data/comedy01/segments.json` → пересобрать выбор моментов (свежий Gemini ~$0.016).
- **Гейт перед коммитом (ОБЯЗАТЕЛЬНО зелёный):** из services/worker: `just check`.

## 4. Тестовые данные (в `services/worker/data/`, gitignored)
- **comedy01** — RU интервью «Звёзды против мошенников» (Щербаков). Полный кэш (source/transcript
  7949 слов/segments 5/клипы). Лучший для теста reframe без оплаты.
- **sample01** — EN «Mafia» (мультиспикер), кэш есть.

## 5. Архитектура (где что)
- `app/pipeline/stage0_import…stage5_render.py` — чистые стадии (pure-логика + тонкие I/O-обёртки).
- `app/run.py` — склейка стадий 0→5 + job.json + runs.jsonl (телеметрия). CLI и REST зовут её.
- `app/main.py` (POST/GET /jobs, /healthz, /media), `app/tasks.py` (фон), `app/db.py` (SQLite).
- `app/models.py` — ЕДИНЫЙ источник типов. Менять контракт ТОЛЬКО здесь → `just types` (codegen).
- **Reframe:** `stage3_reframe.py` (cut-aware largest-face D2: detect_cuts→build_shots→shot_centers);
  `stage3_speaker.py` (PURE: build_tracks IOU + pick_speaker_centers argmax); `asd_reframe.py`
  (I/O: MediaPipe@25fps→tracks→crop+ASD→центр говорящего); `app/asd/` (вендоренное ядро LR-ASD
  `_vendor/` MIT + `scorer.py` наш + `weights/`). Reframe-режимы: `REFRAME_MODE=auto|fill|fit`,
  `REFRAME_SPEAKER=true|false`, `REFRAME_SPEAKER_CROP_SCALE=0.55`.
- **Web:** `app/page.tsx` (state idle→tracking→done→error), `components/` (SourceForm со степпером,
  ClipGrid с чекбоксами, ClipCard, JobProgress…), `lib/` (api/useJob polling/format), `app/api/mock`.

## 6. ГРАБЛИ (критично — не наступать снова)
- **PowerShell-инструмент**: для Windows/uv/just/pnpm/ffmpeg + всегда PATH-refresh (см. §3).
  Держит cwd между вызовами → используй АБСОЛЮТНЫЕ пути. `2>&1` на нативных exe ломает exit-code.
- **Bash-инструмент**: настоящий bash; ffmpeg/just НЕ на его PATH; для python-однострочников ок,
  но Cyrillic в консоль бьётся → писать вывод в файл и читать Read-ом.
- **Коммит ТОЛЬКО из PowerShell** (pre-commit зовёт `just check`, нужен PATH). Сообщение —
  в файл `services/worker/tmp/COMMIT_MSG.txt` (UTF-8) + `git commit -F` (PS-пайп бьёт кириллицу/BOM).
- **pre-commit ruff-format переформатирует** под стиль → если хук «reformatted N files» и упал,
  просто `git add` заново + повторить коммит. Вендоренное (`app/asd/_vendor`) исключено в
  `.pre-commit-config.yaml` + `[tool.ruff] force-exclude`.
- **Типы — только `just types`** (из models.py); руками `packages/shared/*` НЕ трогать (anti-drift).
- **TDD на pure-логике обязателен** (правило плана). Тесты в `services/worker/tests/unit/`.
- **Спайк-окружение ASD** (torch CPU + LR-ASD клон) — в `services/worker/tmp/spike/` (gitignored, ~ГБ;
  можно удалить, если место надо). torch/scipy/psf поставлены в worker-venv (опц. группа `asd`).

## 7. БЛИЖАЙШЕЕ (что делать в новой сессии)
1. **Дождаться вердикта фаундера по active-speaker** (clip_01/clip_03 отправлены): на того ли
   человека наводит? кадр? → крутить `REFRAME_SPEAKER_CROP_SCALE` (0.45–0.8) и перегнать comedy01
   (`uv run --extra asd python -m app.run comedy01` c `$env:REFRAME_SPEAKER="true"`), сравнить кадры.
2. Если active-speaker принят → решить дефолт (флаг on/off) + деплой-нюанс (`--extra asd` ставит torch).
3. Возможные улучшения: кэш транскрипции по hash(source) (UI-джоб сейчас каждый раз платит Deepgram);
   тюнинг `detect_cuts(threshold)` (0.3 иногда пропускает склейку); K1-очередь (по плану, отложено).
- Ключи в `.env` (корень): DEEPGRAM_API_KEY, GEMINI_API_KEY, LLM_MODEL=gemini-flash-latest.
  Экономика: ~$0.16/видео (33 мин), доминанта — транскрипция (см. BENCHMARKS).
