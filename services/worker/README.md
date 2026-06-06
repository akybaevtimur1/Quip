# clipflow-worker

FastAPI + чистый пайплайн нарезки (Phase 0 «тонкий пайплайн»).

## Зачем
Сквозной резак: source → транскрипт (word-level) → выбор моментов (LLM) →
reframe 9:16 → прожжённые субтитры → FFmpeg cut/encode → MP4. См.
`../../CLIPFLOW_DEV_PLAN.md` (план) и `../../CLAUDE.md` (правила).

## Запуск
```powershell
uv sync                                   # поставить зависимости в .venv
uv run uvicorn app.main:app --port 8000   # REST (Phase 0: только /healthz)
# проверка: curl http://localhost:8000/healthz  -> {"ok":true,"version":"..."}
```

## Ключевые файлы
- `app/main.py` — FastAPI (Phase 0: `/healthz`; `/jobs` — этап J).
- `app/models.py` — Pydantic-контракты, ЕДИНЫЙ источник типов (этап A6).
- `app/export_schema.py` — codegen `models.py → packages/shared/contract.json` (A6).
- `app/pipeline/stageN_*.py` — чистые стадии (вход-файл → выход-файл, без HTTP/DB).
- `app/run.py` / `app/tasks.py` — склейка стадий (CLI / FastAPI BackgroundTask).

## Границы
`pipeline/*` — pure-функции (тестируются без сети). Склейка и запись статуса —
только в `run.py`/`tasks.py`. Типы НЕ дублируем: правим только `app/models.py`,
TS-контракт генерим через `just types`.
