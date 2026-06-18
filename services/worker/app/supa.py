"""Persist плана/расхода в Supabase Postgres через PostgREST (service_role).

Активен ⇔ ``BILLING_ENABLED`` + ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``. Привязка
к ``BILLING_ENABLED`` намеренная: пока биллинг выключен — всё идёт в SQLite, а миграцию
0002 (payg_credits/credits) фаундеру не обязательно применять. Когда фаундер применит
0002 и включит ``BILLING_ENABLED`` — план/usage начинают писаться в Postgres.

``service_role`` обходит RLS → план и usage пишет ТОЛЬКО сервер (у юзера нет таких прав).
PURE-агрегаторы (``_sum_usage`` / ``_profile_from_rows``) покрыты тестами; httpx-вызовы тонкие.

Схема (миграции 0001+0002): ``profiles(id uuid PK, plan, payg_credits)``,
``usage_events(user_id uuid, job_id, source_minutes, credits, month)``.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


def supa_enabled() -> bool:
    """Писать ли в Supabase (vs SQLite). Гейт = BILLING_ENABLED + URL + service_role."""
    billing = os.environ.get("BILLING_ENABLED", "").strip().lower() in ("1", "true", "yes")
    return bool(
        billing and os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )


def _base() -> str:
    return f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1"


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra:
        headers.update(extra)
    return headers


# ─────────────────────────── PURE-агрегаторы (тестируемые) ───────────────────────────


def _sum_usage(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Строки usage_events за месяц → {videos, minutes, credits}. PURE."""
    return {
        "videos": len(rows),
        "minutes": float(sum(float(r.get("source_minutes") or 0) for r in rows)),
        "credits": int(sum(int(r.get("credits") or 0) for r in rows)),
    }


def _profile_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Ответ PostgREST на profiles → {plan, payg_credits}. Пусто → free / 0. PURE."""
    if not rows:
        return {"plan": "free", "payg_credits": 0}
    r = rows[0]
    return {"plan": str(r.get("plan") or "free"), "payg_credits": int(r.get("payg_credits") or 0)}


# ─────────────────────────── I/O (тонкие обёртки) ───────────────────────────


def get_profile(user_id: str) -> dict[str, Any]:
    r = httpx.get(
        f"{_base()}/profiles",
        params={"id": f"eq.{user_id}", "select": "plan,payg_credits"},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return _profile_from_rows(r.json())


def get_user_plan(user_id: str) -> str:
    return str(get_profile(user_id)["plan"])


def set_user_plan(user_id: str, plan: str) -> None:
    # Как add_payg_credits: PATCH по несуществующей строке = 0 строк → upgrade МОЛЧА терялся
    # бы (юзер оплатил подписку, остался free). return=representation + INSERT-фолбэк = upsert.
    r = httpx.patch(
        f"{_base()}/profiles",
        params={"id": f"eq.{user_id}"},
        headers=_headers({"Prefer": "return=representation"}),
        json={"plan": plan},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    if r.json():
        return
    ins = httpx.post(
        f"{_base()}/profiles",
        headers=_headers({"Prefer": "return=minimal"}),
        json={"id": user_id, "plan": plan},
        timeout=_TIMEOUT,
    )
    ins.raise_for_status()


def add_payg_credits(user_id: str, credits: int) -> None:
    # GET текущий баланс + PATCH (вебхук последователен → гонка маловероятна).
    # return=representation → видим, обновилась ли строка. Если профиля ещё нет (триггер
    # signup не сработал / гонка) — PATCH затрагивает 0 строк, и без фолбэка оплата МОЛЧА
    # терялась бы (правило №8). Тогда INSERT'им профиль (как SQLite-путь = upsert).
    current = int(get_profile(user_id)["payg_credits"])
    r = httpx.patch(
        f"{_base()}/profiles",
        params={"id": f"eq.{user_id}"},
        headers=_headers({"Prefer": "return=representation"}),
        json={"payg_credits": current + int(credits)},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    if r.json():  # строка существовала и обновилась
        return
    ins = httpx.post(
        f"{_base()}/profiles",
        headers=_headers({"Prefer": "return=minimal"}),
        json={"id": user_id, "plan": "free", "payg_credits": int(credits)},
        timeout=_TIMEOUT,
    )
    ins.raise_for_status()


def deduct_payg(user_id: str, credits: int) -> None:
    # BE-H: списать PAYG-кредиты (PAYG-покрытая часть джоба). Зеркалит SQLite-семантику:
    # пол 0 (баланс не уходит в минус), credits<=0 → no-op, нет профиля → no-op (нечего
    # списывать; в отличие от add_payg_credits НЕ INSERT'им — отрицательный PAYG бессмыслен).
    # read-modify-write через PATCH (вебхук/таск последователен → гонка маловероятна).
    if credits <= 0:
        return
    current = int(get_profile(user_id).get("payg_credits") or 0)
    if current <= 0:
        return  # нет баланса (или профиля) → списывать нечего, PATCH не нужен
    new_balance = max(0, current - int(credits))
    r = httpx.patch(
        f"{_base()}/profiles",
        params={"id": f"eq.{user_id}"},
        headers=_headers({"Prefer": "return=representation"}),
        json={"payg_credits": new_balance},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def record_usage(
    user_id: str, job_id: str | None, source_minutes: float, month: str, credits: int
) -> bool:
    # Идемпотентность по job_id: если расход этого джоба уже записан (ретрай/повторный
    # прогон), НЕ вставляем второй раз → вызыватель не спишет PAYG дважды. Durable-гарантию
    # даёт UNIQUE-индекс (migrations/0003); check-then-act работает и до его применения
    # (таск последователен → гонка маловероятна). job_id=None (аноним) дедупом не покрыт.
    if job_id is not None:
        chk = httpx.get(
            f"{_base()}/usage_events",
            params={"job_id": f"eq.{job_id}", "select": "id", "limit": "1"},
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        chk.raise_for_status()
        if chk.json():
            return False
    r = httpx.post(
        f"{_base()}/usage_events",
        headers=_headers({"Prefer": "return=minimal"}),
        json={
            "user_id": user_id,
            "job_id": job_id,
            "source_minutes": source_minutes,
            "credits": int(credits),
            "month": month,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return True


def get_monthly_usage(user_id: str, month: str) -> dict[str, float]:
    r = httpx.get(
        f"{_base()}/usage_events",
        params={
            "user_id": f"eq.{user_id}",
            "month": f"eq.{month}",
            "select": "source_minutes,credits",
        },
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return _sum_usage(r.json())


# ─────────────── Auth Admin: авторитетная проверка подтверждения email ───────────────
# JWT Supabase НЕ несёт email_confirmed_at (см. docs/SUPABASE_SETUP.md §6). Авторитет —
# auth.users.email_confirmed_at, доступный только service-role через Auth Admin API
# (GET /auth/v1/admin/users/{id}). Анти-абьюз free-гейт зовёт это, когда verified нельзя
# вывести из claims (не OAuth, нет user_metadata-флага).


def _auth_admin_base() -> str:
    return f"{os.environ['SUPABASE_URL'].rstrip('/')}/auth/v1"


def auth_user_email_confirmed(user_id: str) -> bool:
    """auth.users.email_confirmed_at для ``user_id`` непуст? (service-role Admin API).

    True ⇔ email подтверждён (или Google/SSO-провайдер уже verified — GoTrue ставит
    confirmed_at). Без тихих фолбэков: HTTP-ошибка всплывает (вызывающий → 5xx, не «молча
    разрешить» абьюзеру). Нет такого юзера / нет даты → False.
    """
    r = httpx.get(
        f"{_auth_admin_base()}/admin/users/{user_id}",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    return bool(data.get("email_confirmed_at") or data.get("confirmed_at"))
