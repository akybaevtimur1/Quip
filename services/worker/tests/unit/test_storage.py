"""Тесты pure-билдеров хранилища (app.storage). I/O (R2 upload) — интеграционно, не здесь."""

from app.storage import local_url, public_url, storage_object_key


def test_storage_object_key() -> None:
    assert storage_object_key("job_abc", "clip_01") == "job_abc/clip_01.mp4"


def test_public_url_joins_base_and_key() -> None:
    url = public_url("https://pub-x.r2.dev", "job_abc/clip_01.mp4")
    assert url == "https://pub-x.r2.dev/job_abc/clip_01.mp4"


def test_public_url_strips_trailing_slash_on_base() -> None:
    assert public_url("https://pub-x.r2.dev/", "p.mp4") == "https://pub-x.r2.dev/p.mp4"


def test_local_url_is_relative_clips_path() -> None:
    assert local_url("clip_03") == "clips/clip_03.mp4"


def test_variant_gives_separate_keys() -> None:
    # D1: прожжённый экспорт = ОТДЕЛЬНЫЙ ключ/файл, не перетирает чистый клип.
    assert storage_object_key("job_abc", "clip_01", variant="captioned") == (
        "job_abc/clip_01_captioned.mp4"
    )
    assert local_url("clip_03", variant="captioned") == "clips/clip_03_captioned.mp4"
    # пустой variant = прежнее поведение (обратная совместимость)
    assert storage_object_key("j", "clip_01", variant="") == "j/clip_01.mp4"
