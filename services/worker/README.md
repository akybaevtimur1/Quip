# clipflow-worker

FastAPI + чистый пайплайн нарезки (полный API, задеплоен на Modal `quip-worker`).

## Зачем
Сквозной резак: source → транскрипт (word-level) → выбор моментов (LLM) →
reframe 9:16 → прожжённые субтитры → FFmpeg cut/encode → MP4. Реальность
(деплой/биллинг/инфра, источник правды) → `../../docs/README.md`; правила →
`../../CLAUDE.md`.

## Деплой
Прод — Modal app `quip-worker` (функция `web` всегда тёплая, `min_containers=1`).
Локальный `uvicorn :8000` — только для дев-разработки. Редеплой воркера →
`modal deploy deploy/modal/worker.py` (на Windows сначала
`$env:PYTHONIOENCODING="utf-8"`). Карта деплоя → `../../docs/README.md`.

## Запуск (локально, дев)
```powershell
uv sync                                   # поставить зависимости в .venv
uv run uvicorn app.main:app --port 8000   # поднять REST API локально
# проверка: curl http://localhost:8000/healthz  -> {"ok":true,"version":"..."}
```

## Ключевые файлы
- `app/main.py` — FastAPI, ПОЛНЫЙ API: `/jobs` (+ `/upload`, `/upload-url`,
  `/upload-complete`), редактор (`edit` trim/extend/crop/aspect/set-interval,
  `/render`, `/reframe`, пресеты, agent), `/usage`, `/webhooks/polar`, `/healthz`.
- `app/models.py` — Pydantic-контракты, ЕДИНЫЙ источник типов (этап A6).
- `app/export_schema.py` — codegen `models.py → packages/shared/contract.json` (A6).
- `app/pipeline/stageN_*.py` — чистые стадии (вход-файл → выход-файл, без HTTP/DB).
- `app/run.py` / `app/tasks.py` — склейка стадий (CLI / FastAPI BackgroundTask).

## Границы
`pipeline/*` — pure-функции (тестируются без сети). Склейка и запись статуса —
только в `run.py`/`tasks.py`. Типы НЕ дублируем: правим только `app/models.py`,
TS-контракт генерим через `just types`.
