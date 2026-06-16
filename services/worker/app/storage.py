"""Хранилище готовых клипов: локальный диск (dev) или Cloudflare R2 (prod / boevoy).

``storage_backend=local`` → клип остаётся на диске, ``video_url`` = относительный путь
(раздаётся воркером на ``/media``, как в Phase 0). ``storage_backend=r2`` → клип льётся в
R2 через S3-совместимый API (boto3), возвращается:
  • публичный CDN-URL, если задан ``R2_PUBLIC_URL`` (r2.dev managed-домен / кастомный) — вечный;
  • иначе **presigned GET URL** (подписанный, TTL=``SIGNED_URL_TTL``) — работает на голых
    R2-ключах БЕЗ публичного бакета, чтобы e2e жил до того, как фаундер включит public-домен.

Pure-билдеры покрыты unit-тестами; R2 upload/presign — I/O, проверяется интеграционно (на Modal).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.errors import JobError

# D6: долговечный маркер ссылки на объект R2. Вместо протухающего presigned URL
# (TTL ≤ 7 дней → клип отдаёт 403, когда юзер вернётся) храним в БД r2://<key> и
# заново подписываем на КАЖДОМ чтении (как уже делает /jobs/{job}/source.mp4).
R2_KEY_SCHEME = "r2://"


def key_ref(key: str) -> str:
    """Долговечная ссылка на R2-объект по ключу (не presigned). PURE."""
    return f"{R2_KEY_SCHEME}{key}"


def is_r2_key_ref(value: str) -> bool:
    """value — это маркер R2-ключа (r2://<key>)? PURE."""
    return value.startswith(R2_KEY_SCHEME)


def key_from_ref(ref: str) -> str:
    """Достать R2-ключ из маркера r2://<key>. PURE."""
    return ref[len(R2_KEY_SCHEME) :]


def _clip_name(clip_id: str, variant: str) -> str:
    """Имя файла клипа: ``clip_01`` (clean) или ``clip_01_captioned`` (вариант). PURE.

    ``variant`` разводит АРТЕФАКТЫ одного клипа по разным ключам: чистый reframe-клип
    (база WYSIWYG, никогда не перетирается) vs прожжённый экспорт. Один ключ ≠ два смысла.
    """
    return f"{clip_id}_{variant}" if variant else clip_id


def storage_object_key(job_id: str, clip_id: str, *, variant: str = "") -> str:
    """Ключ объекта клипа в R2-бакете. PURE. ``variant`` → отдельный ключ (см. _clip_name)."""
    return f"{job_id}/{_clip_name(clip_id, variant)}.mp4"


def public_url(public_base: str, key: str) -> str:
    """Публичный CDN-URL объекта (R2 public bucket / custom domain). PURE."""
    return f"{public_base.rstrip('/')}/{key}"


def local_url(clip_id: str, *, variant: str = "") -> str:
    """Относительный путь клипа для локальной раздачи (/media). PURE."""
    return f"clips/{_clip_name(clip_id, variant)}.mp4"


@lru_cache(maxsize=1)
def _r2_client() -> Any:
    """Ленивый S3-клиент к R2 (boto3 импортится только в r2-режиме)."""
    import boto3
    from botocore.config import Config

    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.r2_endpoint,
        aws_access_key_id=s.r2_access_key_id,
        aws_secret_access_key=s.r2_secret_access_key,
        region_name="auto",
        # SigV4 + path-style: R2 ждёт path-addressing и подпись s3v4 для presign.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@lru_cache(maxsize=1)
def _transfer_config() -> Any:
    """boto3 TransferConfig для крупных source-трансферов (R2↔Modal). Дефолт 8 МБ/10 потоков узок
    для 5 ГБ; 64 МБ-части + 20 потоков насыщают канал (Modal и R2 рядом, Cloudflare)."""
    from boto3.s3.transfer import TransferConfig

    return TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=64 * 1024 * 1024,
        max_concurrency=20,
        use_threads=True,
    )


def _presigned_get(client: Any, bucket: str, key: str, ttl: int) -> str:
    """Подписанный GET-URL объекта (работает без публичного бакета). TTL в секундах."""
    url: str = client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=ttl
    )
    return url


def source_object_key(job_id: str) -> str:
    """Ключ исходного видео в R2 (приватный, скачивает только воркер для редактор-рендера). PURE."""
    return f"{job_id}/source.mp4"


def upload_source(local_path: Path, job_id: str) -> None:
    """Залить source.mp4 в R2 (cloud) — чтобы редактор мог пере-рендерить на другом контейнере.

    local-режим: no-op (исходник остаётся на диске). JobError при сбое (правило №8).
    """
    s = get_settings()
    if s.storage_backend != "r2":
        return
    try:
        # upload_file СТРИМИТ с диска + авто-multipart — НЕ read_bytes() (он держал ВЕСЬ
        # исходник в RAM → большие загрузки = OOM/медленно прямо в web-запросе, который и так
        # упирался в 900s-таймаут web-функции). Стрим = низкая память + быстрее → меньше шанс
        # упереться в таймаут на стейджинге исходника в R2.
        _r2_client().upload_file(
            str(local_path),
            s.r2_bucket,
            source_object_key(job_id),
            ExtraArgs={"ContentType": "video/mp4"},
            Config=_transfer_config(),
        )
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 upload source {job_id} failed: {e}") from e


def presigned_source_url(job_id: str) -> str:
    """Presigned GET URL исходника в R2 (для live-превью source в редакторе на Modal)."""
    s = get_settings()
    key = source_object_key(job_id)
    try:
        return _presigned_get(_r2_client(), s.r2_bucket, key, s.signed_url_ttl)
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 presign source {job_id} failed: {e}") from e


def presigned_put_url(job_id: str) -> str:
    """Presigned PUT URL для ПРЯМОЙ загрузки исходника браузером в R2 (минуя Modal web-функцию).

    Большие видео через один долгий POST на Modal web рвались (truncated multipart → 400). Браузер
    PUT'ит файл прямо в R2 (Cloudflare edge, надёжнее) по этому URL; затем дёргает upload-complete →
    spawn. ContentType НЕ подписываем — иначе клиент обязан слать ровно тот же заголовок (хрупко);
    клиент сам ставит Content-Type, R2 хранит. JobError при сбое (правило №8).
    """
    s = get_settings()
    key = source_object_key(job_id)
    try:
        url: str = _r2_client().generate_presigned_url(
            "put_object",
            Params={"Bucket": s.r2_bucket, "Key": key},
            # 6h window: a multi-GB long-form upload on a slow uplink can take well over an
            # hour (5 GB @ ~10 Mbps ≈ 70 min) — a 1h TTL would expire mid-PUT → failed upload.
            ExpiresIn=21600,
        )
        return url
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 presign PUT {job_id} failed: {e}") from e


# ─────────────────────────── multipart upload (файлы > single-PUT) ───────────────────────────
# R2 single PUT макс 5 ГБ. Файлы крупнее (и ради скорости/resume — крупные вообще) браузер режет
# на части по MULTIPART_PART_SIZE и грузит ПАРАЛЛЕЛЬНО прямо в R2; R2 собирает их в один объект.
# 100 МБ/часть: R2 min part 5 МБ, max 10000 частей → до ~1 ТБ при 100 МБ (с запасом под 3h-видео).
MULTIPART_PART_SIZE = 100 * 1024 * 1024


def plan_part_count(size: int, part_size: int) -> int:
    """Сколько частей для файла ``size`` байт при ``part_size``. PURE.

    Минимум 1 (нулевой/битый size → одна часть, не ноль); кап 10000 (лимит S3/R2 на число частей).
    """
    if size <= 0:
        return 1
    return min(10000, math.ceil(size / part_size))


def create_multipart_upload(job_id: str) -> str:
    """Начать multipart-загрузку исходника в R2 → upload_id. JobError при сбое (правило №8)."""
    s = get_settings()
    try:
        resp = _r2_client().create_multipart_upload(
            Bucket=s.r2_bucket, Key=source_object_key(job_id), ContentType="video/mp4"
        )
        return str(resp["UploadId"])
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 create multipart {job_id} failed: {e}") from e


def presigned_upload_part_url(job_id: str, upload_id: str, part_number: int) -> str:
    """Presigned PUT для ОДНОЙ части (браузер PUT'ит кусок файла). JobError при сбое.

    ETag части R2 вернёт в заголовке ответа — браузер читает его (нужен ExposeHeaders: ETag
    в CORS бакета, уже задан) и отдаёт назад в upload-complete для сборки объекта.
    """
    s = get_settings()
    try:
        url: str = _r2_client().generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": s.r2_bucket,
                "Key": source_object_key(job_id),
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=21600,  # 6h — как single-PUT: крупная загрузка на медленном аплинке
        )
        return url
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 presign part {job_id}#{part_number} failed: {e}") from e


def complete_multipart_upload(job_id: str, upload_id: str, parts: list[dict[str, Any]]) -> None:
    """Собрать объект из частей. ``parts`` = [{"PartNumber": n, "ETag": "..."}]. JobError при сбое.

    Сортируем по PartNumber (R2 требует возрастающий порядок) — фронт может прислать вразнобой.
    """
    s = get_settings()
    ordered = sorted(parts, key=lambda p: int(p["PartNumber"]))
    try:
        _r2_client().complete_multipart_upload(
            Bucket=s.r2_bucket,
            Key=source_object_key(job_id),
            UploadId=upload_id,
            MultipartUpload={"Parts": ordered},
        )
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 complete multipart {job_id} failed: {e}") from e


def abort_multipart_upload(job_id: str, upload_id: str) -> None:
    """Отменить незавершённую multipart-загрузку → удалить залитые части (чтобы не копить мусор
    в R2 при сбое/отмене). JobError при сбое — вызыватель (endpoint) гасит в best-effort."""
    s = get_settings()
    try:
        _r2_client().abort_multipart_upload(
            Bucket=s.r2_bucket, Key=source_object_key(job_id), UploadId=upload_id
        )
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 abort multipart {job_id} failed: {e}") from e


def set_upload_cors() -> dict[str, object]:
    """Прописать R2-бакету CORS для браузерных PUT (presigned direct upload) с наших origin'ов.

    Запускается разово (Modal one-off). Без этого браузерный PUT в R2 блокируется CORS-политикой.
    Возвращает текущую конфигурацию (для проверки).
    """
    s = get_settings()
    cors = {
        "CORSRules": [
            {
                "AllowedOrigins": [
                    "https://quip.ink",
                    "https://www.quip.ink",
                    "https://app.quip.ink",
                    "http://localhost:3000",
                    "https://*.vercel.app",
                ],
                "AllowedMethods": ["PUT", "GET", "HEAD"],
                "AllowedHeaders": ["*"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3600,
            }
        ]
    }
    client = _r2_client()
    client.put_bucket_cors(Bucket=s.r2_bucket, CORSConfiguration=cors)
    result: dict[str, object] = client.get_bucket_cors(Bucket=s.r2_bucket)
    return result


def download_source(job_id: str, dest: Path) -> None:
    """Скачать source.mp4 из R2 в dest (для редактор-рендера). JobError при сбое."""
    s = get_settings()
    try:
        _r2_client().download_file(
            s.r2_bucket, source_object_key(job_id), str(dest), Config=_transfer_config()
        )
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 download source {job_id} failed: {e}") from e


def preview_object_key(job_id: str) -> str:
    """Ключ лёгкого preview-прокси (для быстрой загрузки в редакторе) в R2. PURE."""
    return f"{job_id}/preview.mp4"


def upload_preview(local_path: Path, job_id: str) -> None:
    """Залить preview.mp4 в R2 (cloud). local — no-op. Стрим (upload_file). JobError при сбое."""
    s = get_settings()
    if s.storage_backend != "r2":
        return
    try:
        _r2_client().upload_file(
            str(local_path),
            s.r2_bucket,
            preview_object_key(job_id),
            ExtraArgs={"ContentType": "video/mp4"},
        )
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 upload preview {job_id} failed: {e}") from e


def _r2_read_url(key: str) -> str:
    """Живой URL R2-объекта для чтения браузером: публичный CDN (если задан R2_PUBLIC_URL),
    ИНАЧЕ presigned GET. CDN = кэш на краю + нет presigned-протухания → быстрее source/preview.
    """
    s = get_settings()
    if s.r2_public_url:
        return public_url(s.r2_public_url, key)
    return _presigned_get(_r2_client(), s.r2_bucket, key, s.signed_url_ttl)


def source_read_url(job_id: str) -> str:
    """URL source.mp4 для редактора — CDN (если есть) иначе presigned (быстрее presigned-origin)."""
    return _r2_read_url(source_object_key(job_id))


def preview_read_url(job_id: str) -> str:
    """URL preview-прокси, если он есть в R2; ИНАЧЕ — source (фолбэк для старых джоб без прокси).

    head_object — дешёвая проверка наличия. Любой сбой/404 → отдаём source: прокси = ОПТИМИЗАЦИЯ,
    source = источник правды, видео в редакторе всё равно загрузится (деградация, не поломка).
    """
    s = get_settings()
    key = preview_object_key(job_id)
    try:
        _r2_client().head_object(Bucket=s.r2_bucket, Key=key)
    except Exception:  # noqa: BLE001 — нет прокси (старый джоб) / R2-блип → фолбэк на source
        return source_read_url(job_id)
    return _r2_read_url(key)


def upload_clip(local_path: Path, job_id: str, clip_id: str, *, variant: str = "") -> str:
    """Сохранить готовый клип → вернуть ДОЛГОВЕЧНЫЙ ``video_url``.

    ``variant`` (например ``"captioned"``) пишет в ОТДЕЛЬНЫЙ ключ/файл — чистый reframe-клип
    (``variant=""``) никогда не перетирается прожжённым экспортом (D1: один ключ ≠ два смысла).
    local-режим: клип уже на диске, возвращаем относительный путь (раздаётся на ``/media``).
    r2-режим: льём mp4 в R2 (upsert) и возвращаем:
      • публичный CDN-URL, если задан R2_PUBLIC_URL — он вечный;
      • иначе ДОЛГОВЕЧНЫЙ маркер ключа ``r2://<key>`` (D6) — НЕ presigned URL. Presign минтится
        заново на КАЖДОМ чтении (resolve_media_url), иначе TTL≤7д протухает → клип отдаёт 403,
        когда юзер вернётся к своим клипам спустя час/день. JobError при сбое (правило №8).
    """
    s = get_settings()
    if s.storage_backend != "r2":
        return local_url(clip_id, variant=variant)
    key = storage_object_key(job_id, clip_id, variant=variant)
    client = _r2_client()
    try:
        # upload_file СТРИМИТ с диска (+ авто-multipart) — НЕ read_bytes() (тот держал весь клип
        # в RAM). Как upload_source/upload_preview → консистентно и без RAM-спайка.
        client.upload_file(
            str(local_path),
            s.r2_bucket,
            key,
            ExtraArgs={"ContentType": "video/mp4"},
            Config=_transfer_config(),
        )
    except Exception as e:  # noqa: BLE001 — оборачиваем в JobError, не глотаем
        raise JobError("storage", f"R2 upload {clip_id} failed: {e}") from e
    if s.r2_public_url:
        return public_url(s.r2_public_url, key)
    return key_ref(key)


# ─────────────────────── ретеншн (бюджет R2: source = 70-90% хранилища) ───────────────────────
# source.mp4/preview.mp4 нужны лишь редактору; клипы (продукт) — крошечные и вечны. Чистим
# editor-only артефакты старше окна → R2 не растёт безлимитно (разовая оплата → вечное хранение).
_EDITOR_ARTIFACT_SUFFIXES = ("/source.mp4", "/preview.mp4")
DEFAULT_SOURCE_RETENTION_DAYS = 60


def is_stale_editor_artifact(
    key: str, last_modified: datetime, *, now: datetime, max_age_days: int
) -> bool:
    """True ⇔ ``key`` — editor-only артефакт (source/preview) старше ``max_age_days``. PURE.

    Любой другой ключ (клип = продукт) → False: клипы не удаляем НИКОГДА.
    """
    if not key.endswith(_EDITOR_ARTIFACT_SUFFIXES):
        return False
    return last_modified <= now - timedelta(days=max_age_days)


def delete_stale_editor_artifacts(max_age_days: int = DEFAULT_SOURCE_RETENTION_DAYS) -> int:
    """Удалить source.mp4/preview.mp4 старше ``max_age_days`` из R2. Клипы НЕ трогаем.

    Возвращает число удалённых объектов. Только r2-режим (local → 0). Зовётся по расписанию
    (Modal Cron). JobError при сбое (правило №8). Снижает безлимитный рост хранилища.
    """
    s = get_settings()
    if s.storage_backend != "r2":
        return 0
    now = datetime.now(UTC)
    client = _r2_client()
    to_delete: list[dict[str, str]] = []
    try:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=s.r2_bucket):
            for obj in page.get("Contents", []):
                if is_stale_editor_artifact(
                    obj["Key"], obj["LastModified"], now=now, max_age_days=max_age_days
                ):
                    to_delete.append({"Key": obj["Key"]})
        deleted = 0
        # delete_objects — батчами по 1000 (лимит S3/R2 на один запрос).
        for i in range(0, len(to_delete), 1000):
            batch = to_delete[i : i + 1000]
            client.delete_objects(Bucket=s.r2_bucket, Delete={"Objects": batch, "Quiet": True})
            deleted += len(batch)
        return deleted
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 retention cleanup failed: {e}") from e


def resolve_media_url(stored: str) -> str:
    """Резолв сохранённого ``video_url``/``render_url`` в живой URL на ЧТЕНИИ (I/O, cloud).

    D6: маркер ключа ``r2://<key>`` → СВЕЖИЙ presigned GET (не протухает между чтениями).
    Публичный/presigned http-URL и относительный путь — отдаём как есть (резолвит вызыватель/
    фронт). Единая точка ре-подписи: и для клипов грида (row_to_wire), и для render_url.
    """
    if not is_r2_key_ref(stored):
        return stored
    s = get_settings()
    key = key_from_ref(stored)
    try:
        return _presigned_get(_r2_client(), s.r2_bucket, key, s.signed_url_ttl)
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 presign {key} failed: {e}") from e
