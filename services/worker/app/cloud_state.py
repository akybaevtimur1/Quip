"""Облачный стейт воркера в Supabase Postgres через PostgREST (service_role).

Зеркало диск/SQLite-стейта (`app/db.py`) для boevoy-режима (Modal): джобы, артефакты
пайплайна (meta/segments/transcript), правки клипов и content-addressed transcript-кэш —
всё в Supabase. ``service_role`` обходит RLS → стейт пишет ТОЛЬКО сервер; фронт читает свои
строки по RLS (политики `own jobs` и т.п. уже накатаны в проде).

Активен ⇔ ``cloud_enabled()`` (STORAGE_BACKEND=r2 + SUPABASE_URL + SERVICE_ROLE_KEY) — так
локальный dev остаётся на SQLite+диске без облака, а на Modal автоматически идёт в Postgres.
Тот же стиль, что ``app/supa.py`` (биллинг): тонкие httpx-обёртки + PURE-хелперы под тесты.

Схема (накатана в проде, ref qiagetbnsssvbiowuxpp): jobs / job_artifacts / clip_edits /
transcript_cache (см. docs или Supabase Table Editor).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)


def cloud_enabled() -> bool:
    """Писать ли стейт в Supabase (vs локальный SQLite/диск). Гейт = r2 + URL + service_role."""
    backend = os.environ.get("STORAGE_BACKEND", "").strip().lower()
    return bool(
        backend == "r2"
        and os.environ.get("SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )


def _base() -> str:
    return f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1"


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra:
        headers.update(extra)
    return headers


# ─────────────────────────── PURE-хелперы (тестируемые) ───────────────────────────


def first_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """PostgREST всегда отдаёт массив → первая строка или None. PURE."""
    return rows[0] if rows else None


def lock_applied(rows: list[dict[str, Any]]) -> bool:
    """Атомарный optimistic-lock: PATCH ...&version=eq.X с return=representation вернул строку?

    Пустой массив → версия не совпала (никакая строка не подошла под фильтр) → конфликт. PURE.
    """
    return len(rows) == 1


# ─────────────────────────── jobs ───────────────────────────


def insert_job(
    job_id: str, source_type: str, source_ref: str, *, user_id: str | None = None
) -> None:
    r = httpx.post(
        f"{_base()}/jobs",
        headers=_headers({"Prefer": "return=minimal"}),
        json={
            "id": job_id,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "source_type": source_type,
            "source_ref": source_ref,
            "user_id": user_id,
            "cancellable": True,  # Stop-кнопка: новый джоб стартует во FREE-фазе
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def update_status(job_id: str, status: str, progress: int) -> None:
    r = httpx.patch(
        f"{_base()}/jobs",
        params={"id": f"eq.{job_id}"},
        headers=_headers({"Prefer": "return=minimal"}),
        json={"status": status, "stage": status, "progress": progress},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def set_done(
    job_id: str,
    clips: list[dict[str, Any]],
    cost_usd: float,
    duration_sec: float,
    elapsed_sec: float,
) -> None:
    r = httpx.patch(
        f"{_base()}/jobs",
        params={"id": f"eq.{job_id}"},
        headers=_headers({"Prefer": "return=minimal"}),
        json={
            "status": "done",
            "stage": "done",
            "progress": 100,
            "clips": clips,
            "cost_usd": cost_usd,
            "duration_sec": duration_sec,
            "elapsed_sec": elapsed_sec,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def set_clips_pending(job_id: str, clips: list[dict[str, Any]], progress: int = 80) -> None:
    """Записать ВСЕ клипы со статусом "rendering" и пустым video_url СРАЗУ после Select.

    Та же колонка ``clips`` (jsonb), что пишет ``set_done`` — но status остаётся "rendering",
    а каждый клип несёт ``video_url=""`` (pending). Параллельные фан-аут-контейнеры затем
    проставляют свой video_url через ``set_clip_ready`` (атомарный jsonb_set). Так GET /jobs
    отдаёт уже готовые клипы по мере рендера, пока ``set_done`` не флипнет в "done".
    """
    r = httpx.patch(
        f"{_base()}/jobs",
        params={"id": f"eq.{job_id}"},
        headers=_headers({"Prefer": "return=minimal"}),
        json={"status": "rendering", "stage": "rendering", "progress": progress, "clips": clips},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def set_clip_ready(job_id: str, idx: int, url: str) -> None:
    """Атомарно проставить ``clips[idx].video_url`` ОДНОГО клипа (per-clip контейнер закончил).

    Вызывает Postgres-RPC ``set_clip_video_url`` (migrations/0010): jsonb_set внутри ОДНОГО
    серверного UPDATE атомарен (Postgres сериализует UPDATE'ы строки), поэтому параллельные
    контейнеры, пишущие РАЗНЫЕ индексы, не теряют запись друг друга — в отличие от PATCH целой
    колонки (read-modify-write → гонка). ``idx`` 0-based (позиция в массиве). RPC возвращает
    число обновлённых строк; 0 → джоба/индекса нет (логируем, не глотаем — правило №8).
    """
    r = httpx.post(
        f"{_base()}/rpc/set_clip_video_url",
        headers=_headers(),
        json={"p_job_id": job_id, "p_idx": idx, "p_url": url},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    updated = r.json()
    if not updated:
        print(f"[set_clip_ready] WARN: no row updated for job={job_id} idx={idx}")


def set_failed(job_id: str, error: str) -> None:
    r = httpx.patch(
        f"{_base()}/jobs",
        params={"id": f"eq.{job_id}"},
        headers=_headers({"Prefer": "return=minimal"}),
        json={"status": "failed", "stage": "failed", "error": error},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def set_function_call_id(job_id: str, fc_id: str) -> None:
    """Сохранить id Modal-``FunctionCall`` (для отмены джоба). Только эта колонка."""
    r = httpx.patch(
        f"{_base()}/jobs",
        params={"id": f"eq.{job_id}"},
        headers=_headers({"Prefer": "return=minimal"}),
        json={"function_call_id": fc_id},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def set_cancellable(job_id: str, value: bool) -> None:
    """Переключить флаг отмены (воркер гасит в False при входе в платную стадию)."""
    r = httpx.patch(
        f"{_base()}/jobs",
        params={"id": f"eq.{job_id}"},
        headers=_headers({"Prefer": "return=minimal"}),
        json={"cancellable": value},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def set_cancelled(job_id: str) -> None:
    """Пометить джоб отменённым (Stop). Guard ``status!=done & status!=failed`` — не
    перетираем завершённый джоб (гонка отмены с финишем пайплайна)."""
    # Дублирующийся ключ ``status`` (neq.done И neq.failed) — httpx сериализует список
    # значений в повторённые query-параметры, что PostgREST трактует как AND по колонке.
    r = httpx.patch(
        f"{_base()}/jobs",
        params={"id": f"eq.{job_id}", "status": ["neq.done", "neq.failed"]},
        headers=_headers({"Prefer": "return=minimal"}),
        json={"status": "cancelled", "stage": "cancelled", "cancellable": False},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def get_job_row(job_id: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{_base()}/jobs",
        params={"id": f"eq.{job_id}", "select": "*"},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return first_row(r.json())


# ─────────────────────────── job_artifacts (meta/segments/transcript) ───────────────────────────


def put_job_artifacts(
    job_id: str, meta: dict[str, Any], segments: list[Any], transcript: dict[str, Any]
) -> None:
    r = httpx.post(
        f"{_base()}/job_artifacts",
        headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        json={"job_id": job_id, "meta": meta, "segments": segments, "transcript": transcript},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def get_job_artifacts(job_id: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{_base()}/job_artifacts",
        params={"job_id": f"eq.{job_id}", "select": "meta,segments,transcript"},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return first_row(r.json())


def put_job_artifact(job_id: str, key: str, value: Any) -> None:
    """Upsert ОДНОЙ jsonb-колонки строки job_artifacts (напр. video_map), не трогая остальные.

    merge-duplicates по PK job_id: строка обычно уже создана put_job_artifacts (run.py до
    фан-аута), поэтому это UPDATE одной колонки. Cross-container: video_map_job (отдельный
    Modal-контейнер) пишет сюда, а /video-map (web-контейнер) читает get_job_artifact.
    Требует колонку job_artifacts.<key> (jsonb) в Postgres.
    """
    r = httpx.post(
        f"{_base()}/job_artifacts",
        headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        json={"job_id": job_id, key: value},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def get_job_artifact(job_id: str, key: str) -> Any:
    """Прочитать ОДНУ jsonb-колонку job_artifacts[key]; None если строки/значения нет."""
    r = httpx.get(
        f"{_base()}/job_artifacts",
        params={"job_id": f"eq.{job_id}", "select": key},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    row = first_row(r.json())
    return row.get(key) if row else None


# ─────────────────────────── transcript_cache (бережёт Deepgram) ───────────────────────────


def get_cached_transcript(audio_sha: str, provider: str, model: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{_base()}/transcript_cache",
        params={
            "audio_sha": f"eq.{audio_sha}",
            "provider": f"eq.{provider}",
            "model": f"eq.{model}",
            "select": "transcript",
        },
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    row = first_row(r.json())
    return row["transcript"] if row else None


def put_cached_transcript(
    audio_sha: str, provider: str, model: str, transcript: dict[str, Any]
) -> None:
    r = httpx.post(
        f"{_base()}/transcript_cache",
        headers=_headers({"Prefer": "resolution=ignore-duplicates,return=minimal"}),
        json={
            "audio_sha": audio_sha,
            "provider": provider,
            "model": model,
            "transcript": transcript,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


# ─────────────────────────── clip_edits (атомарный optimistic-lock) ───────────────────────────


def get_clip_edit_row(job_id: str, clip_id: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{_base()}/clip_edits",
        params={"job_id": f"eq.{job_id}", "clip_id": f"eq.{clip_id}", "select": "*"},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return first_row(r.json())


def insert_clip_edit(job_id: str, clip_id: str, edit: dict[str, Any], version: int) -> None:
    """Первичная вставка edit-state. on conflict do nothing (ignore-duplicates)."""
    r = httpx.post(
        f"{_base()}/clip_edits",
        headers=_headers({"Prefer": "resolution=ignore-duplicates,return=minimal"}),
        json={"job_id": job_id, "clip_id": clip_id, "version": version, "edit": edit},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def update_clip_edit_if_version(
    job_id: str, clip_id: str, edit: dict[str, Any], *, expected_version: int, new_version: int
) -> bool:
    """Атомарный optimistic-lock: PATCH ...&version=eq.expected. True если строка обновилась."""
    r = httpx.patch(
        f"{_base()}/clip_edits",
        params={
            "job_id": f"eq.{job_id}",
            "clip_id": f"eq.{clip_id}",
            "version": f"eq.{expected_version}",
        },
        headers=_headers({"Prefer": "return=representation"}),
        json={"edit": edit, "version": new_version},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return lock_applied(r.json())


def set_render_status(
    job_id: str, clip_id: str, status: str, url: str | None, error: str | None
) -> None:
    r = httpx.patch(
        f"{_base()}/clip_edits",
        params={"job_id": f"eq.{job_id}", "clip_id": f"eq.{clip_id}"},
        headers=_headers({"Prefer": "return=minimal"}),
        json={"render_status": status, "render_url": url, "render_error": error},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
