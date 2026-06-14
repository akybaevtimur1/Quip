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


# ─────────────────────────── add_payg_credits: upsert, не теряет оплату ───────────────────────────
# Money-bug: PostgREST PATCH по несуществующей строке profiles затрагивает 0 строк и при
# return=minimal МОЛЧА теряет начисление (юзер заплатил → 0 кредитов). SQLite-путь делает
# upsert; Supabase-путь обязан вести себя так же. Мокаем httpx (без сети).


class _Resp:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


def _supa_env(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc")


class TestAddPaygCredits:
    def test_increments_existing_profile(self, monkeypatch) -> None:
        _supa_env(monkeypatch)
        calls: list[tuple[str, dict]] = []

        def fake_get(url, **kw):  # type: ignore[no-untyped-def]
            return _Resp([{"plan": "free", "payg_credits": 3}])

        def fake_patch(url, **kw):  # type: ignore[no-untyped-def]
            calls.append(("patch", kw.get("json", {})))
            # PATCH с return=representation вернул обновлённую строку → строка существовала
            return _Resp([{"id": "u1", "payg_credits": 5}])

        monkeypatch.setattr(supa.httpx, "get", fake_get)
        monkeypatch.setattr(supa.httpx, "patch", fake_patch)
        supa.add_payg_credits("u1", 2)
        assert calls and calls[0][1]["payg_credits"] == 5  # 3 + 2

    def test_inserts_when_profile_missing(self, monkeypatch) -> None:
        # Профиля ещё нет (триггер не сработал / гость до signup-row) → PATCH 0 строк →
        # ОБЯЗАН вставить, а не потерять оплату.
        _supa_env(monkeypatch)
        posts: list[dict] = []

        def fake_get(url, **kw):  # type: ignore[no-untyped-def]
            return _Resp([])  # профиля нет

        def fake_patch(url, **kw):  # type: ignore[no-untyped-def]
            return _Resp([])  # 0 строк обновлено

        def fake_post(url, **kw):  # type: ignore[no-untyped-def]
            posts.append(kw.get("json", {}))
            return _Resp(None, status=201)

        monkeypatch.setattr(supa.httpx, "get", fake_get)
        monkeypatch.setattr(supa.httpx, "patch", fake_patch)
        monkeypatch.setattr(supa.httpx, "post", fake_post)
        supa.add_payg_credits("u_new", 2)
        assert posts, "оплата должна вставить профиль, а не потеряться"
        assert posts[0]["payg_credits"] == 2 and posts[0]["plan"] == "free"


class TestDeductPayg:
    # BE-H: списание PAYG-баланса. read-modify-write через PATCH; floor at 0; нет профиля → no-op.
    def test_decrements_existing_balance(self, monkeypatch) -> None:
        _supa_env(monkeypatch)
        patched: list[dict] = []

        def fake_get(url, **kw):  # type: ignore[no-untyped-def]
            return _Resp([{"plan": "free", "payg_credits": 5}])

        def fake_patch(url, **kw):  # type: ignore[no-untyped-def]
            patched.append(kw.get("json", {}))
            return _Resp([{"id": "u1", "payg_credits": 3}])

        monkeypatch.setattr(supa.httpx, "get", fake_get)
        monkeypatch.setattr(supa.httpx, "patch", fake_patch)
        supa.deduct_payg("u1", 2)
        assert patched and patched[0]["payg_credits"] == 3  # 5 - 2

    def test_floors_at_zero(self, monkeypatch) -> None:
        _supa_env(monkeypatch)
        patched: list[dict] = []

        def fake_get(url, **kw):  # type: ignore[no-untyped-def]
            return _Resp([{"plan": "free", "payg_credits": 1}])

        def fake_patch(url, **kw):  # type: ignore[no-untyped-def]
            patched.append(kw.get("json", {}))
            return _Resp([{"id": "u1", "payg_credits": 0}])

        monkeypatch.setattr(supa.httpx, "get", fake_get)
        monkeypatch.setattr(supa.httpx, "patch", fake_patch)
        supa.deduct_payg("u1", 4)
        assert patched and patched[0]["payg_credits"] == 0  # max(0, 1-4)

    def test_missing_profile_is_noop_no_patch(self, monkeypatch) -> None:
        # Нет профиля → нечего списывать; не INSERT'им (в отличие от add — отрицательный
        # баланс бессмыслен), не падаем.
        _supa_env(monkeypatch)
        patched: list[dict] = []

        def fake_get(url, **kw):  # type: ignore[no-untyped-def]
            return _Resp([])  # профиля нет

        def fake_patch(url, **kw):  # type: ignore[no-untyped-def]
            patched.append(kw.get("json", {}))
            return _Resp([])

        monkeypatch.setattr(supa.httpx, "get", fake_get)
        monkeypatch.setattr(supa.httpx, "patch", fake_patch)
        supa.deduct_payg("ghost", 2)
        assert patched == []  # нечего списывать

    def test_zero_is_noop(self, monkeypatch) -> None:
        _supa_env(monkeypatch)
        patched: list[dict] = []
        monkeypatch.setattr(supa.httpx, "get", lambda url, **kw: _Resp([{"payg_credits": 5}]))
        monkeypatch.setattr(
            supa.httpx, "patch", lambda url, **kw: patched.append(kw.get("json", {}))
        )
        supa.deduct_payg("u1", 0)
        assert patched == []  # n=0 → не дёргаем PATCH


class TestRecordUsage:
    # Идемпотентность по job_id: дубль (ретрай) НЕ вставляет вторую строку → нет двойного заряда.
    def test_skips_insert_when_job_already_recorded(self, monkeypatch) -> None:
        _supa_env(monkeypatch)
        posted: list = []
        monkeypatch.setattr(supa.httpx, "get", lambda url, **kw: _Resp([{"id": 1}]))  # уже есть
        monkeypatch.setattr(supa.httpx, "post", lambda url, **kw: posted.append(kw))
        assert supa.record_usage("u", "job_a", 10.0, "2026-06", 1) is False
        assert posted == []  # дубль → POST не делаем

    def test_inserts_when_new(self, monkeypatch) -> None:
        _supa_env(monkeypatch)
        posted: list = []

        def fake_post(url, **kw):  # type: ignore[no-untyped-def]
            posted.append(kw.get("json", {}))
            return _Resp(None, status=201)

        monkeypatch.setattr(supa.httpx, "get", lambda url, **kw: _Resp([]))  # записи нет
        monkeypatch.setattr(supa.httpx, "post", fake_post)
        assert supa.record_usage("u", "job_b", 10.0, "2026-06", 1) is True
        assert posted and posted[0]["job_id"] == "job_b"

    def test_none_job_id_skips_dedup_check(self, monkeypatch) -> None:
        _supa_env(monkeypatch)
        gets: list = []
        posted: list = []

        def fake_get(url, **kw):  # type: ignore[no-untyped-def]
            gets.append(url)
            return _Resp([])

        def fake_post(url, **kw):  # type: ignore[no-untyped-def]
            posted.append(kw.get("json", {}))
            return _Resp(None, status=201)

        monkeypatch.setattr(supa.httpx, "get", fake_get)
        monkeypatch.setattr(supa.httpx, "post", fake_post)
        assert supa.record_usage("u", None, 10.0, "2026-06", 1) is True
        assert gets == []  # job_id=None → проверку дубля не делаем
        assert posted  # вставили


class TestSetUserPlan:
    def test_patches_existing_profile(self, monkeypatch) -> None:
        _supa_env(monkeypatch)
        posts: list[dict] = []
        _row = [{"id": "u", "plan": "pro"}]
        monkeypatch.setattr(supa.httpx, "patch", lambda url, **kw: _Resp(_row))
        monkeypatch.setattr(supa.httpx, "post", lambda url, **kw: posts.append(kw.get("json", {})))
        supa.set_user_plan("u", "pro")
        assert posts == []  # строка была → INSERT не нужен

    def test_inserts_when_profile_missing(self, monkeypatch) -> None:
        # Подписка оплачена до создания профиля → апгрейд НЕ должен теряться.
        _supa_env(monkeypatch)
        posts: list[dict] = []

        def fake_post(url, **kw):  # type: ignore[no-untyped-def]
            posts.append(kw.get("json", {}))
            return _Resp(None, status=201)

        monkeypatch.setattr(supa.httpx, "patch", lambda url, **kw: _Resp([]))  # 0 строк
        monkeypatch.setattr(supa.httpx, "post", fake_post)
        supa.set_user_plan("u_new", "starter")
        assert posts and posts[0] == {"id": "u_new", "plan": "starter"}
