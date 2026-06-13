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

from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.errors import JobError


def storage_object_key(job_id: str, clip_id: str) -> str:
    """Ключ объекта клипа в R2-бакете. PURE."""
    return f"{job_id}/{clip_id}.mp4"


def public_url(public_base: str, key: str) -> str:
    """Публичный CDN-URL объекта (R2 public bucket / custom domain). PURE."""
    return f"{public_base.rstrip('/')}/{key}"


def local_url(clip_id: str) -> str:
    """Относительный путь клипа для локальной раздачи (/media). PURE."""
    return f"clips/{clip_id}.mp4"


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
        _r2_client().put_object(
            Bucket=s.r2_bucket,
            Key=source_object_key(job_id),
            Body=local_path.read_bytes(),
            ContentType="video/mp4",
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


def download_source(job_id: str, dest: Path) -> None:
    """Скачать source.mp4 из R2 в dest (для редактор-рендера). JobError при сбое."""
    s = get_settings()
    try:
        _r2_client().download_file(s.r2_bucket, source_object_key(job_id), str(dest))
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 download source {job_id} failed: {e}") from e


def upload_clip(local_path: Path, job_id: str, clip_id: str) -> str:
    """Сохранить готовый клип → вернуть ``video_url``.

    local-режим: клип уже на диске, возвращаем относительный путь (раздаётся на ``/media``).
    r2-режим: льём mp4 в R2 (upsert), возвращаем публичный CDN-URL (если задан R2_PUBLIC_URL)
    либо presigned GET URL. JobError при сбое (правило №8 — никаких тихих фолбэков).
    """
    s = get_settings()
    if s.storage_backend != "r2":
        return local_url(clip_id)
    key = storage_object_key(job_id, clip_id)
    client = _r2_client()
    try:
        client.put_object(
            Bucket=s.r2_bucket,
            Key=key,
            Body=local_path.read_bytes(),
            ContentType="video/mp4",
        )
    except Exception as e:  # noqa: BLE001 — оборачиваем в JobError, не глотаем
        raise JobError("storage", f"R2 upload {clip_id} failed: {e}") from e
    if s.r2_public_url:
        return public_url(s.r2_public_url, key)
    try:
        return _presigned_get(client, s.r2_bucket, key, s.signed_url_ttl)
    except Exception as e:  # noqa: BLE001
        raise JobError("storage", f"R2 presign {clip_id} failed: {e}") from e
