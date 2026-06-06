"""FastAPI-входная точка воркера ClipFlow.

Phase 0: пока только health-check. Эндпоинты задач (POST /jobs, GET /jobs/{id})
появятся на этапе J. Логика пайплайна живёт в app/pipeline/* и сюда не протекает.
"""

from fastapi import FastAPI

from app import __version__

app = FastAPI(title="clipflow-worker", version=__version__)


@app.get("/healthz")
def healthz() -> dict[str, bool | str]:
    """Liveness-проба.

    Вход: нет. Выход: ``{"ok": True, "version": "<версия пакета>"}``.
    Без auth (см. план §4.3). Не кидает исключений.
    """
    return {"ok": True, "version": __version__}
