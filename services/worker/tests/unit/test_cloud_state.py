"""Тесты PURE-хелперов облачного стейта (app.cloud_state). I/O (PostgREST) — интеграционно."""

from __future__ import annotations

import app.cloud_state as cs


def test_first_row_returns_first() -> None:
    assert cs.first_row([{"a": 1}, {"a": 2}]) == {"a": 1}


def test_first_row_none_on_empty() -> None:
    assert cs.first_row([]) is None


def test_lock_applied_true_on_single_returned_row() -> None:
    assert cs.lock_applied([{"job_id": "j", "clip_id": "c", "version": 2}]) is True


def test_lock_applied_false_on_empty() -> None:
    # PATCH ...&version=eq.X вернул пустой массив → версия не совпала → конфликт.
    assert cs.lock_applied([]) is False


def test_cloud_disabled_by_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert cs.cloud_enabled() is False


def test_cloud_disabled_when_backend_local(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    assert cs.cloud_enabled() is False


def test_cloud_enabled_when_r2_and_keys(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("STORAGE_BACKEND", "r2")
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    assert cs.cloud_enabled() is True
