"""W3: персистентность agent_runs (dual-mode: local SQLite / cloud Supabase).

Кросс-контейнерно (Modal): spawned agent_edit_job ПИШЕТ события, web-контейнер их ЧИТАЕТ →
в проде это Supabase. Единственный писатель на run (во время running) → read-modify-write
ленты событий безопасен. Изолированный модуль (не раздуваем db.py); local — через db._conn.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from app import cloud_state as cs
from app.db import _conn

_TERMINAL = ("done", "failed", "cancelled")


def new_run_id() -> str:
    return "ar_" + uuid.uuid4().hex[:16]


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    """Привести ряд (local: events_json str / cloud: events jsonb) к единому виду с events:list."""
    events = row.get("events")
    if events is None:
        raw = row.get("events_json") or "[]"
        events = json.loads(raw) if isinstance(raw, str) else raw
    return {
        "run_id": row["run_id"],
        "job_id": row["job_id"],
        "clip_id": row["clip_id"],
        "user_id": row.get("user_id"),
        "status": row["status"],
        "events": events,
        "error": row.get("error"),
        "function_call_id": row.get("function_call_id"),
        "cancellable": bool(row.get("cancellable", True)),
    }


# ─────────────────────────── cloud (Supabase REST) ───────────────────────────


def _cloud_get(run_id: str) -> dict[str, Any] | None:
    r = httpx.get(
        f"{cs._base()}/agent_runs",
        params={"run_id": f"eq.{run_id}", "select": "*"},
        headers=cs._headers(),
        timeout=cs._TIMEOUT,
    )
    r.raise_for_status()
    return cs.first_row(r.json())


# ─────────────────────────── public API (routing) ───────────────────────────


def create_run(run_id: str, job_id: str, clip_id: str, user_id: str | None) -> None:
    now = time.time()
    if cs.cloud_enabled():
        r = httpx.post(
            f"{cs._base()}/agent_runs",
            headers=cs._headers({"Prefer": "return=minimal"}),
            json={
                "run_id": run_id,
                "job_id": job_id,
                "clip_id": clip_id,
                "user_id": user_id,
                "status": "running",
                "events": [],
                "cancellable": True,
            },  # fmt: skip
            timeout=cs._TIMEOUT,
        )
        r.raise_for_status()
        return
    with _conn() as c:
        c.execute(
            "INSERT INTO agent_runs"
            " (run_id,job_id,clip_id,user_id,status,events_json,cancellable,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, job_id, clip_id, user_id, "running", "[]", 1, now, now),
        )


def get_run(run_id: str) -> dict[str, Any] | None:
    if cs.cloud_enabled():
        row = _cloud_get(run_id)
        return _normalize(row) if row else None
    with _conn() as c:
        row = c.execute("SELECT * FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
    return _normalize(dict(row)) if row is not None else None


def append_event(run_id: str, event: dict[str, Any]) -> None:
    """Дописать событие в ленту (read-modify-write; единственный писатель — agent_edit_job)."""
    if cs.cloud_enabled():
        row = _cloud_get(run_id)
        events = (row.get("events") if row else None) or []
        events.append(event)
        r = httpx.patch(
            f"{cs._base()}/agent_runs",
            params={"run_id": f"eq.{run_id}"},
            headers=cs._headers({"Prefer": "return=minimal"}),
            json={"events": events, "updated_at": "now()"},
            timeout=cs._TIMEOUT,
        )
        r.raise_for_status()
        return
    with _conn() as c:
        row = c.execute("SELECT events_json FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
        events = json.loads(row["events_json"]) if row else []
        events.append(event)
        c.execute(
            "UPDATE agent_runs SET events_json=?, updated_at=? WHERE run_id=?",
            (json.dumps(events, ensure_ascii=False), time.time(), run_id),
        )


def set_status(run_id: str, status: str, error: str | None = None) -> None:
    cancellable = status not in _TERMINAL
    if cs.cloud_enabled():
        r = httpx.patch(
            f"{cs._base()}/agent_runs",
            params={"run_id": f"eq.{run_id}"},
            headers=cs._headers({"Prefer": "return=minimal"}),
            json={
                "status": status,
                "error": error,
                "cancellable": cancellable,
                "updated_at": "now()",
            },  # fmt: skip
            timeout=cs._TIMEOUT,
        )
        r.raise_for_status()
        return
    with _conn() as c:
        c.execute(
            "UPDATE agent_runs SET status=?, error=?, cancellable=?, updated_at=? WHERE run_id=?",
            (status, error, 1 if cancellable else 0, time.time(), run_id),
        )


def set_function_call_id(run_id: str, fc_id: str) -> None:
    if cs.cloud_enabled():
        r = httpx.patch(
            f"{cs._base()}/agent_runs",
            params={"run_id": f"eq.{run_id}"},
            headers=cs._headers({"Prefer": "return=minimal"}),
            json={"function_call_id": fc_id},
            timeout=cs._TIMEOUT,
        )
        r.raise_for_status()
        return
    with _conn() as c:
        c.execute("UPDATE agent_runs SET function_call_id=? WHERE run_id=?", (fc_id, run_id))


def set_cancelled(run_id: str) -> bool:
    """Пометить cancelled, ТОЛЬКО если ещё не в терминале. True если применилось (guard)."""
    if cs.cloud_enabled():
        r = httpx.patch(
            f"{cs._base()}/agent_runs",
            params={"run_id": f"eq.{run_id}", "status": "eq.running"},
            headers=cs._headers({"Prefer": "return=representation"}),
            json={"status": "cancelled", "cancellable": False, "updated_at": "now()"},
            timeout=cs._TIMEOUT,
        )
        r.raise_for_status()
        return cs.lock_applied(r.json())
    with _conn() as c:
        cur = c.execute(
            "UPDATE agent_runs SET status='cancelled', cancellable=0, updated_at=?"
            " WHERE run_id=? AND status='running'",
            (time.time(), run_id),
        )
        return cur.rowcount == 1


def running_run(job_id: str, clip_id: str) -> dict[str, Any] | None:
    """Активный (running) прогон для клипа → идемпотентность старта (один run на клип)."""
    if cs.cloud_enabled():
        r = httpx.get(
            f"{cs._base()}/agent_runs",
            params={
                "job_id": f"eq.{job_id}",
                "clip_id": f"eq.{clip_id}",
                "status": "eq.running",
                "select": "*",
                "limit": "1",
            },  # fmt: skip
            headers=cs._headers(),
            timeout=cs._TIMEOUT,
        )
        r.raise_for_status()
        row = cs.first_row(r.json())
        return _normalize(row) if row else None
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM agent_runs WHERE job_id=? AND clip_id=? AND status='running'"
            " ORDER BY created_at DESC LIMIT 1",
            (job_id, clip_id),
        ).fetchone()
    return _normalize(dict(row)) if row is not None else None
