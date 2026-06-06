"""Доменные ошибки пайплайна.

Правило №8: никаких тихих фолбэков. Любой провал стадии → ``JobError(stage, reason)``;
оркестратор (run.py/tasks.py) ловит его, пишет статус job=failed и текст в error.
"""


class JobError(Exception):
    """Явная ошибка стадии пайплайна.

    Вход: ``stage`` (имя стадии, напр. "import") и ``reason`` (человекочитаемая причина).
    """

    def __init__(self, stage: str, reason: str) -> None:
        self.stage = stage
        self.reason = reason
        super().__init__(f"[{stage}] {reason}")
