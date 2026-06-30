"""Тесты pure-билдеров хранилища (app.storage). I/O (R2 upload) — интеграционно, не здесь."""

from app.storage import (
    MULTIPART_MAX_PARTS,
    MULTIPART_MIN_PART_SIZE,
    MULTIPART_THRESHOLD,
    R2_KEY_SCHEME,
    clip_upload_extra_args,
    is_r2_key_ref,
    key_from_ref,
    key_ref,
    local_url,
    plan_part_count,
    plan_part_size,
    preview_object_key,
    public_url,
    source_object_key,
    storage_object_key,
    with_cache_bust,
)


def test_storage_object_key() -> None:
    assert storage_object_key("job_abc", "clip_01") == "job_abc/clip_01.mp4"


def test_source_and_preview_keys_distinct() -> None:
    assert source_object_key("job_abc") == "job_abc/source.mp4"
    assert preview_object_key("job_abc") == "job_abc/preview.mp4"
    assert source_object_key("job_abc") != preview_object_key("job_abc")


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


# ─── CDN-протухание ре-рендера (хук-размер «не меняется» после Render) ───
# Корень бага: captioned-клип перезаписывается по ТОМУ ЖЕ R2-ключу и отдаётся со
# стабильного CDN-URL (cdn.quip.ink) → Cloudflare кэшировал первый рендер и продолжал
# отдавать его после правок. Две линии защиты: CacheControl=no-cache на загрузке +
# ?v=<version> на read-URL. Обе — pure, под тестом.


def test_clip_upload_sets_no_cache() -> None:
    # БЕЗ no-cache CDN отдаёт протухший mp4 после ре-рендера (хук-размер не меняется).
    args = clip_upload_extra_args("clip_01", "captioned")
    assert "no-cache" in args["CacheControl"]
    assert args["ContentType"] == "video/mp4"
    # attachment-заголовок сохранён (download реально сохраняет файл кросс-доменно)
    assert args["ContentDisposition"] == 'attachment; filename="clip_01_captioned.mp4"'


def test_clip_upload_extra_args_clean_variant() -> None:
    args = clip_upload_extra_args("clip_03", "")
    assert "no-cache" in args["CacheControl"]
    assert args["ContentDisposition"] == 'attachment; filename="clip_03.mp4"'


def test_cache_bust_appends_version_to_cdn_url() -> None:
    base = "https://cdn.quip.ink/job_x/clip_01_captioned.mp4"
    # каждый ре-рендер инкрементит version → новый URL → CDN-miss → свежий файл
    assert with_cache_bust(base, 1) == base + "?v=1"
    assert with_cache_bust(base, 5) == base + "?v=5"
    assert with_cache_bust(base, 5) != with_cache_bust(base, 1)


def test_cache_bust_keeps_existing_query() -> None:
    signed = "https://r2/clip.mp4?X-Amz-Signature=abc"
    assert with_cache_bust(signed, 2) == signed + "&v=2"


def test_cache_bust_noop_without_version_or_relative() -> None:
    # version=None или относительная (локалка /media) → не трогаем
    assert with_cache_bust("https://cdn/clip.mp4", None) == "https://cdn/clip.mp4"
    assert with_cache_bust("media/job/clip_01.mp4", 3) == "media/job/clip_01.mp4"


# ─────────────── D6: durable R2 key-ref (re-presign on read, не вечный presign) ───────────────


def test_key_ref_round_trips_the_object_key() -> None:
    # Вместо протухающего presigned URL храним ДОЛГОВЕЧНЫЙ маркер ключа r2://<key>.
    ref = key_ref("job_abc/clip_01.mp4")
    assert ref == f"{R2_KEY_SCHEME}job_abc/clip_01.mp4"
    assert is_r2_key_ref(ref)
    assert key_from_ref(ref) == "job_abc/clip_01.mp4"


def test_is_r2_key_ref_rejects_plain_urls_and_paths() -> None:
    assert not is_r2_key_ref("https://pub-x.r2.dev/job/clip.mp4")
    assert not is_r2_key_ref("clips/clip_01.mp4")
    assert not is_r2_key_ref("media/job/clips/clip_01.mp4")
    assert not is_r2_key_ref("")


# ─────────────── L1: multipart part-size/threshold tuning (browser direct upload) ───────────────
# Раньше ОДНА константа (100 МБ) была И порогом, И размером части → 30–100 МБ файлы НЕ резались.
# Теперь порог (32 МБ) и размер части (от 16 МБ) — разные ручки; число частей капится под лимит R2.

_MB = 1024 * 1024


def test_threshold_below_part_size_so_mid_files_go_multipart() -> None:
    # Порог МЕНЬШЕ старых 100 МБ → 30–100 МБ файлы теперь идут multipart (параллельно + resume).
    assert MULTIPART_THRESHOLD < 100 * _MB
    assert MULTIPART_THRESHOLD == 32 * _MB
    assert MULTIPART_MIN_PART_SIZE == 16 * _MB


def test_typical_phone_upload_uses_min_part_size() -> None:
    # 80 МБ телефонная загрузка → part_size = MIN (16 МБ), 5 частей (ceil(80/16)).
    size = 80 * _MB
    ps = plan_part_size(size)
    assert ps == MULTIPART_MIN_PART_SIZE
    assert plan_part_count(size, ps) == 5


def test_10gb_stays_well_under_part_limit() -> None:
    # 10 ГБ при 16 МБ/часть = 640 частей — далеко под лимитом R2 (10000).
    size = 10 * 1024 * _MB
    ps = plan_part_size(size)
    assert ps == MULTIPART_MIN_PART_SIZE
    assert plan_part_count(size, ps) == 640


def test_huge_file_grows_part_size_to_cap_count() -> None:
    # На гигантском файле part_size РАСТЁТ, чтобы число частей не пробило MAX_PARTS.
    size = 500 * 1024 * _MB  # 500 ГБ
    ps = plan_part_size(size)
    assert ps > MULTIPART_MIN_PART_SIZE  # вырос выше нижней границы
    n = plan_part_count(size, ps)
    assert n <= MULTIPART_MAX_PARTS  # число частей под капом-с-запасом
    assert n <= 10000  # и под жёстким лимитом R2


def test_part_count_invariant_holds_across_sizes() -> None:
    # Инвариант: при part_size из plan_part_size число частей всегда ≤ MAX_PARTS.
    for size in (1 * _MB, 33 * _MB, 200 * _MB, 5 * 1024 * _MB, 999 * 1024 * _MB):
        ps = plan_part_size(size)
        assert ps >= MULTIPART_MIN_PART_SIZE
        assert plan_part_count(size, ps) <= MULTIPART_MAX_PARTS


def test_plan_part_size_zero_is_min() -> None:
    assert plan_part_size(0) == MULTIPART_MIN_PART_SIZE
    assert plan_part_count(0, plan_part_size(0)) == 1
