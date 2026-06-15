"""Polar.sh интеграция (P1): проверка подписи вебхука (Standard Webhooks) + маппинг
product→план. Всё PURE и покрыто тестами (включая официальный тест-вектор Standard
Webhooks) — провод/секреты живут в main.py + config.

Polar шлёт вебхуки по спецификации **Standard Webhooks** (как svix):
заголовки ``webhook-id`` / ``webhook-timestamp`` / ``webhook-signature``; секрет
``whsec_<base64>``; подписывается ``"{id}.{timestamp}.{body}"`` через HMAC-SHA256,
результат base64; заголовок подписи — список ``v1,<sig>`` через пробел (любой матч).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import time
from typing import Any

# События подписки, после которых план = product (активная подписка).
_ACTIVE_EVENTS = frozenset(
    {
        "subscription.created",
        "subscription.active",
        "subscription.updated",
        "subscription.uncanceled",
    }
)
# События, после которых план сбрасывается во free.
_DOWNGRADE_EVENTS = frozenset({"subscription.canceled", "subscription.revoked"})
# Разовая оплата (PAYG-кредиты): одноразовый заказ, НЕ подписка.
_ORDER_PAID_EVENTS = frozenset({"order.created", "order.paid", "order.updated"})


def verify_signature(
    secret: str,
    body: bytes | str,
    *,
    webhook_id: str,
    webhook_timestamp: str,
    signature_header: str,
    tolerance_sec: int = 300,
    now: int | None = None,
) -> bool:
    """True ⇔ подпись валидна по Standard Webhooks. PURE (``now`` инъектируется в тестах).

    Проверяет HMAC-SHA256 над ``"{id}.{timestamp}.{body}"`` ключом base64-decode(secret
    без ``whsec_``), constant-time против записей ``v1,<sig>`` в заголовке. Плюс окно
    времени (анти-replay): |now − timestamp| ≤ tolerance_sec.
    """
    if not (secret and webhook_id and webhook_timestamp and signature_header):
        return False
    try:
        ts = int(webhook_timestamp)
    except ValueError:
        return False
    current = int(now if now is not None else time.time())
    if abs(current - ts) > tolerance_sec:
        return False

    # Снять префикс секрета: Standard Webhooks = ``whsec_``, Polar = ``polar_whs_``.
    # (Без снятия polar_whs_ ключ декодировался неверно → подпись НИКОГДА не матчилась → 401
    # на все реальные вебхуки Polar.) Плюс восстановить недостающий base64-паддинг (Polar часто
    # отдаёт секрет без ``=``), иначе b64decode падает на длине не кратной 4.
    raw_secret = secret
    for prefix in ("polar_whs_", "whsec_"):
        if raw_secret.startswith(prefix):
            raw_secret = raw_secret[len(prefix) :]
            break
    raw_secret += "=" * (-len(raw_secret) % 4)
    try:
        key = base64.b64decode(raw_secret)
    except (ValueError, binascii.Error):
        return False

    payload = body.decode("utf-8") if isinstance(body, bytes) else body
    signed = f"{webhook_id}.{webhook_timestamp}.{payload}".encode()
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode("ascii")

    for entry in signature_header.split():
        sig = entry.partition(",")[2] if "," in entry else entry
        if hmac.compare_digest(expected, sig):
            return True
    return False


def product_to_plan(product_id: str, *, starter: str, pro: str) -> str | None:
    """``product_id`` (Polar) → "starter" / "pro" / None (не наш продукт). PURE."""
    if starter and product_id == starter:
        return "starter"
    if pro and product_id == pro:
        return "pro"
    return None


def _metadata_plan(data: dict[str, Any]) -> str | None:
    """Фолбэк-маппинг плана через ``metadata.plan`` продукта/заказа (forward-compat:
    фаундер может выставить metadata.plan=starter|pro на продукте в Polar). PURE."""
    for src in (data.get("product"), data):
        if isinstance(src, dict):
            meta = src.get("metadata")
            if isinstance(meta, dict):
                plan = str(meta.get("plan", "")).lower()
                if plan in ("starter", "pro"):
                    return plan
    return None


def _extract_user_id(data: dict[str, Any]) -> str | None:
    """user_id из Polar-payload: customer.external_id (предпочтительно), затем
    metadata.user_id, затем customer_external_id на уровне подписки."""
    customer = data.get("customer")
    if isinstance(customer, dict) and customer.get("external_id"):
        return str(customer["external_id"])
    meta = data.get("metadata")
    if isinstance(meta, dict) and meta.get("user_id"):
        return str(meta["user_id"])
    ext = data.get("customer_external_id") or data.get("external_customer_id")
    return str(ext) if ext else None


def parse_plan_change(
    payload: dict[str, Any], *, product_starter: str, product_pro: str
) -> tuple[str, str] | None:
    """Из Polar webhook-payload достать ``(user_id, plan_id)``. PURE.

    Активная подписка наших продуктов → план starter/pro; canceled/revoked → "free".
    None, если ивент не про план, нет user_id, или продукт не наш (вебхук игнорируем —
    отвечаем 200, Polar не ретраит).
    """
    event = str(payload.get("type", ""))
    if event not in _ACTIVE_EVENTS and event not in _DOWNGRADE_EVENTS:
        return None
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return None
    user_id = _extract_user_id(data)
    if not user_id:
        return None
    if event in _DOWNGRADE_EVENTS:
        return (user_id, "free")
    plan = product_to_plan(
        str(data.get("product_id", "")), starter=product_starter, pro=product_pro
    )
    if plan is None:
        plan = _metadata_plan(data)  # фолбэк: metadata.plan на продукте/заказе
    if plan is None:
        return None
    return (user_id, plan)


def parse_payg_order(
    payload: dict[str, Any], *, product_payg: str, credits_per_order: int = 1
) -> tuple[str, int] | None:
    """Из Polar webhook-payload разовой оплаты достать ``(user_id, credits)``. PURE.

    PAYG = одноразовый заказ продукта ``product_payg`` (НЕ подписка) → начисляем
    ``credits_per_order`` НЕ-сгорающих кредитов (с учётом quantity заказа, если задан).
    None, если ивент не про разовую оплату, продукт не наш, или нет user_id.
    """
    event = str(payload.get("type", ""))
    if event not in _ORDER_PAID_EVENTS:
        return None
    # ``product_payg`` может быть СПИСКОМ id через запятую (несколько PAYG-продуктов: основной
    # + тестовый $1 и т.п.) — заказ любого из них начисляет кредиты. PURE, по product_id (он
    # всегда в payload), без зависимости от вложенных метаданных.
    payg_ids = {p.strip() for p in product_payg.split(",") if p.strip()}
    if not payg_ids:
        return None
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return None
    if str(data.get("product_id", "")) not in payg_ids:
        return None
    user_id = _extract_user_id(data)
    if not user_id:
        return None
    qty = data.get("quantity")
    units = int(qty) if isinstance(qty, int) and qty > 0 else 1
    return (user_id, credits_per_order * units)
