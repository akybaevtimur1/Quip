"""Диспатч тяжёлых задач: Modal ``.spawn()`` (prod) или FastAPI BackgroundTask (local/dev).

⚠️ На Modal POST-эндпоинт ОБЯЗАН делать ``run_job.spawn(...)``, а НЕ BackgroundTask: web —
scale-to-zero ASGI-контейнер, после ответа он гаснет и фон-таск умирает на полпути нарезки.
``.spawn()`` ставит работу в ОТДЕЛЬНУЮ долгоживущую CPU-функцию, переживающую гашение web.

Гейт = ``MODAL_SPAWN=1`` (ставит образ Modal через секрет/env). Локально переменной нет →
BackgroundTask, как в Phase 0. Имя приложения Modal = ``quip-worker`` (см. deploy/modal/worker.py).
"""

from __future__ import annotations

import os
from typing import Any

_MODAL_APP = "quip-worker"


def modal_spawn_enabled() -> bool:
    """Спавнить ли через Modal (vs BackgroundTask). True только внутри Modal-образа."""
    return os.environ.get("MODAL_SPAWN", "").strip() == "1"


def spawn(fn_name: str, *args: Any) -> str | None:
    """Запустить именованную Modal-функцию приложения ``quip-worker``.

    Возвращает ``object_id`` запущенного ``FunctionCall`` (id для последующей отмены джоба
    через ``modal.FunctionCall.from_id(id).cancel()``). На local/dev (нет Modal) — ``None``.
    """
    import modal

    fn = modal.Function.from_name(_MODAL_APP, fn_name)
    fc = fn.spawn(*args)
    return str(fc.object_id)
