"""Supabase-персистенс (supa.py): PURE-агрегаторы + флаг активации. HTTP не тестируем
(тонкие обёртки PostgREST); агрегацию строк — да."""

from __future__ import annotations

from app import supa


class TestSumUsage:
    def test_empty(self) -> None:
        assert supa._sum_usage([]) == {"videos": 0, "minutes": 0.0, "credits": 0}

    def test_sums_rows(self) -> None:
        rows = [
            {"source_minutes": 10.0, "credits": 1},
            {"source_minutes": 90.0, "credits": 2},
        ]
        out = supa._sum_usage(rows)
        assert out == {"videos": 2, "minutes": 100.0, "credits": 3}

    def test_tolerates_missing_fields(self) -> None:
        out = supa._sum_usage([{"source_minutes": None}, {}])
        assert out == {"videos": 2, "minutes": 0.0, "credits": 0}


class TestProfileFromRows:
    def test_empty_defaults_free(self) -> None:
        assert supa._profile_from_rows([]) == {"plan": "free", "payg_credits": 0}

    def test_reads_first_row(self) -> None:
        out = supa._profile_from_rows([{"plan": "pro", "payg_credits": 5}])
        assert out == {"plan": "pro", "payg_credits": 5}

    def test_nulls_default(self) -> None:
        out = supa._profile_from_rows([{"plan": None, "payg_credits": None}])
        assert out == {"plan": "free", "payg_credits": 0}


class TestSupaEnabled:
    def test_off_without_billing(self, monkeypatch) -> None:
        monkeypatch.delenv("BILLING_ENABLED", raising=False)
        monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc")
        assert supa.supa_enabled() is False

    def test_off_without_keys(self, monkeypatch) -> None:
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        assert supa.supa_enabled() is False

    def test_on_with_all(self, monkeypatch) -> None:
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc")
        assert supa.supa_enabled() is True
