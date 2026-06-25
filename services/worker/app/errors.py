"""Доменные ошибки пайплайна.

Правило №8: никаких тихих фолбэков. Любой провал стадии → ``JobError(stage, reason)``;
оркестратор (run.py/tasks.py) ловит его, пишет статус job=failed и текст в error.
"""

from __future__ import annotations


class JobError(Exception):
    """Явная ошибка стадии пайплайна.

    Вход: ``stage`` (имя стадии, напр. "import") и ``reason`` (человекочитаемая причина).

    ⚠️ КРОСС-КОНТЕЙНЕРНАЯ (де)сериализация (Modal): дочерний клип-контейнер пиклит
    исключение, координатор его РАСПИКЛИВАЕТ. ``BaseException`` восстанавливается как
    ``cls(*self.args)`` — поэтому в ``args`` ОБЯЗАНЫ лежать РОВНО ``(stage, reason)``,
    иначе приёмная сторона зовёт ``JobError(<один-собранный-стринг>)`` и падает на
    «missing 1 required positional argument (reason)» (Modal: «Could not deserialize
    remote exception»). Держим оба позиционных в ``args`` (``super().__init__(stage,
    reason)``) и фиксируем reduce явно. ``str()`` остаётся ``"[stage] reason"`` (см. ниже).
    """

    def __init__(self, stage: str, reason: str) -> None:
        self.stage = stage
        self.reason = reason
        # ОБА позиционных идут в ``self.args`` → round-trip через pickle/cloudpickle цел
        # (приёмник зовёт JobError(stage, reason), не JobError("[stage] reason")).
        super().__init__(stage, reason)

    def __str__(self) -> str:
        # Публичный текст НЕ меняем (user-facing reason'ы, set_failed(str(e))): "[stage] reason".
        return f"[{self.stage}] {self.reason}"

    def __reduce__(self) -> tuple[type[JobError], tuple[str, str]]:
        # Явный reduce: гарантирует реконструкцию ``JobError(stage, reason)`` независимо от
        # того, как пиклер читает ``args`` (страховка к super().__init__ выше).
        return (self.__class__, (self.stage, self.reason))
