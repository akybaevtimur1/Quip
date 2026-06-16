"""R2-ретеншн: чистим только крупные editor-only артефакты (source/preview) старше окна.

Клипы — это ПРОДУКТ, их не трогаем никогда (любой другой ключ → False). Чистая классификация
(``is_stale_editor_artifact``) покрыта тут; сам list+delete — I/O (интеграционно на Modal).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.storage import DEFAULT_SOURCE_RETENTION_DAYS, is_stale_editor_artifact

NOW = datetime(2026, 6, 16, tzinfo=UTC)


def test_old_source_and_preview_are_stale() -> None:
    old = NOW - timedelta(days=DEFAULT_SOURCE_RETENTION_DAYS + 1)
    assert is_stale_editor_artifact("job_x/source.mp4", old, now=NOW, max_age_days=60)
    assert is_stale_editor_artifact("job_x/preview.mp4", old, now=NOW, max_age_days=60)


def test_recent_source_is_kept() -> None:
    recent = NOW - timedelta(days=10)
    assert not is_stale_editor_artifact("job_x/source.mp4", recent, now=NOW, max_age_days=60)


def test_clip_is_never_stale() -> None:
    # Клип сколь угодно старый — это продукт, удалять нельзя.
    ancient = NOW - timedelta(days=999)
    assert not is_stale_editor_artifact("job_x/clip_01.mp4", ancient, now=NOW, max_age_days=60)
    assert not is_stale_editor_artifact(
        "job_x/clip_01_captioned.mp4", ancient, now=NOW, max_age_days=60
    )
