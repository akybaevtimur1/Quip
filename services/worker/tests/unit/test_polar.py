"""Тесты Polar.sh интеграции (P1): подпись (Standard Webhooks), маппинг product→план,
вебхук-эндпоинт и гейт квоты в create_job. PURE-функции + endpoint через TestClient."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from app import billing, db, polar

# ─────────────────────────── verify_signature ───────────────────────────
# Официальный тест-вектор Standard Webhooks (svix). Если наша проверка его принимает —
# реализация спека-корректна, а значит совпадает с подписью Polar.
_SW_SECRET = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
_SW_ID = "msg_p5jXN8AQM9LWM0D4loKWxJek"
_SW_TS = "1614265330"
_SW_PAYLOAD = '{"test": 2432232314}'
_SW_SIG = "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="


def test_verify_signature_official_vector() -> None:
    assert polar.verify_signature(
        _SW_SECRET,
        _SW_PAYLOAD,
        webhook_id=_SW_ID,
        webhook_timestamp=_SW_TS,
        signature_header=_SW_SIG,
        now=int(_SW_TS),
    )


def test_verify_signature_accepts_polar_whs_prefix_and_unpadded() -> None:
    # Polar отдаёт секрет как ``polar_whs_<base64>`` (часто БЕЗ ``=``-паддинга). Раньше код
    # снимал только ``whsec_`` → ключ декодился неверно → 401 на все реальные вебхуки Polar.
    key = b"0123456789abcdef0123456789abcdef"  # 32-байтный HMAC-ключ
    secret = "polar_whs_" + base64.b64encode(key).decode().rstrip("=")  # без паддинга
    wid, ts, body = "msg_polar_1", "1700000000", '{"type": "order.paid"}'
    signed = f"{wid}.{ts}.{body}".encode()
    sig = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    assert polar.verify_signature(
        secret,
        body,
        webhook_id=wid,
        webhook_timestamp=ts,
        signature_header=f"v1,{sig}",
        now=int(ts),
    )


def test_verify_signature_rejects_tampered_body() -> None:
    assert not polar.verify_signature(
        _SW_SECRET,
        _SW_PAYLOAD + " ",
        webhook_id=_SW_ID,
        webhook_timestamp=_SW_TS,
        signature_header=_SW_SIG,
        now=int(_SW_TS),
    )


def test_verify_signature_rejects_wrong_secret() -> None:
    assert not polar.verify_signature(
        "whsec_" + base64.b64encode(b"not-the-secret").decode(),
        _SW_PAYLOAD,
        webhook_id=_SW_ID,
        webhook_timestamp=_SW_TS,
        signature_header=_SW_SIG,
        now=int(_SW_TS),
    )


def test_verify_signature_rejects_expired_timestamp() -> None:
    # Подпись валидна, но timestamp вне окна толерантности (анти-replay).
    assert not polar.verify_signature(
        _SW_SECRET,
        _SW_PAYLOAD,
        webhook_id=_SW_ID,
        webhook_timestamp=_SW_TS,
        signature_header=_SW_SIG,
        now=int(_SW_TS) + 10_000,
    )


def test_verify_signature_rejects_missing_headers() -> None:
    assert not polar.verify_signature(
        _SW_SECRET, _SW_PAYLOAD, webhook_id="", webhook_timestamp=_SW_TS, signature_header=_SW_SIG
    )


# ─────────────────────────── product_to_plan / parse_plan_change ───────────────────────────


def test_product_to_plan() -> None:
    assert polar.product_to_plan("p_s", starter="p_s", pro="p_p") == "starter"
    assert polar.product_to_plan("p_p", starter="p_s", pro="p_p") == "pro"
    assert polar.product_to_plan("p_x", starter="p_s", pro="p_p") is None


def test_parse_plan_change_active_via_external_id() -> None:
    payload = {
        "type": "subscription.created",
        "data": {"product_id": "p_s", "customer": {"external_id": "user_1"}},
    }
    assert polar.parse_plan_change(payload, product_starter="p_s", product_pro="p_p") == (
        "user_1",
        "starter",
    )


def test_parse_plan_change_active_via_metadata() -> None:
    payload = {
        "type": "subscription.updated",
        "data": {"product_id": "p_p", "metadata": {"user_id": "user_2"}},
    }
    assert polar.parse_plan_change(payload, product_starter="p_s", product_pro="p_p") == (
        "user_2",
        "pro",
    )


def test_parse_plan_change_downgrade_on_cancel() -> None:
    payload = {
        "type": "subscription.canceled",
        "data": {"product_id": "p_s", "customer": {"external_id": "user_3"}},
    }
    assert polar.parse_plan_change(payload, product_starter="p_s", product_pro="p_p") == (
        "user_3",
        "free",
    )


def test_parse_plan_change_ignored_event() -> None:
    payload = {"type": "order.created", "data": {"customer": {"external_id": "user_4"}}}
    assert polar.parse_plan_change(payload, product_starter="p_s", product_pro="p_p") is None


def test_parse_plan_change_unknown_product() -> None:
    payload = {
        "type": "subscription.created",
        "data": {"product_id": "p_x", "customer": {"external_id": "user_5"}},
    }
    assert polar.parse_plan_change(payload, product_starter="p_s", product_pro="p_p") is None


def test_parse_plan_change_no_user_id() -> None:
    payload = {"type": "subscription.created", "data": {"product_id": "p_s"}}
    assert polar.parse_plan_change(payload, product_starter="p_s", product_pro="p_p") is None


def test_parse_plan_change_via_metadata_plan_fallback() -> None:
    # product_id не совпал с env, но product.metadata.plan задан → маппим по нему
    payload = {
        "type": "subscription.created",
        "data": {
            "product_id": "unknown",
            "customer": {"external_id": "user_md"},
            "product": {"metadata": {"plan": "pro"}},
        },
    }
    assert polar.parse_plan_change(payload, product_starter="p_s", product_pro="p_p") == (
        "user_md",
        "pro",
    )


# ─────────────────────────── parse_payg_order (разовая оплата) ───────────────────────────


def test_parse_payg_order_grants_credit() -> None:
    payload = {
        "type": "order.paid",
        "data": {"product_id": "p_payg", "customer": {"external_id": "user_p"}},
    }
    assert polar.parse_payg_order(payload, product_payg="p_payg") == ("user_p", 1)


def test_parse_payg_order_respects_quantity() -> None:
    payload = {
        "type": "order.created",
        "data": {"product_id": "p_payg", "quantity": 3, "customer": {"external_id": "user_q"}},
    }
    assert polar.parse_payg_order(payload, product_payg="p_payg", credits_per_order=1) == (
        "user_q",
        3,
    )


def test_parse_payg_order_ignores_other_product() -> None:
    payload = {
        "type": "order.paid",
        "data": {"product_id": "p_other", "customer": {"external_id": "u"}},
    }
    assert polar.parse_payg_order(payload, product_payg="p_payg") is None


def test_parse_payg_order_ignores_subscription_event() -> None:
    payload = {
        "type": "subscription.created",
        "data": {"product_id": "p_payg", "customer": {"external_id": "u"}},
    }
    assert polar.parse_payg_order(payload, product_payg="p_payg") is None


# ─────────────────────────── webhook endpoint ───────────────────────────


def _sign(secret: str, msg_id: str, ts: str, body: str) -> str:
    key = base64.b64decode(secret[len("whsec_") :])
    mac = hmac.new(key, f"{msg_id}.{ts}.{body}".encode(), hashlib.sha256).digest()
    return "v1," + base64.b64encode(mac).decode("ascii")


def test_polar_webhook_applies_plan(monkeypatch) -> None:
    from app.main import app

    monkeypatch.setenv("POLAR_WEBHOOK_SECRET", _SW_SECRET)
    monkeypatch.setenv("POLAR_PRODUCT_STARTER", "prod_starter")
    body = json.dumps(
        {
            "type": "subscription.created",
            "data": {"product_id": "prod_starter", "customer": {"external_id": "user_wh"}},
        }
    )
    ts = str(int(time.time()))
    headers = {
        "webhook-id": "msg_wh",
        "webhook-timestamp": ts,
        "webhook-signature": _sign(_SW_SECRET, "msg_wh", ts, body),
        "content-type": "application/json",
    }
    with TestClient(app) as client:
        r = client.post("/webhooks/polar", content=body, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "applied": True, "user_id": "user_wh", "plan": "starter"}
    assert db.get_user_plan("user_wh") == "starter"


def test_polar_webhook_grants_payg_credits(monkeypatch) -> None:
    from app.main import app

    monkeypatch.setenv("POLAR_WEBHOOK_SECRET", _SW_SECRET)
    monkeypatch.setenv("POLAR_PRODUCT_PAYG", "prod_payg")
    body = json.dumps(
        {
            "type": "order.paid",
            "data": {"product_id": "prod_payg", "customer": {"external_id": "user_payg"}},
        }
    )
    ts = str(int(time.time()))
    headers = {
        "webhook-id": "msg_payg",
        "webhook-timestamp": ts,
        "webhook-signature": _sign(_SW_SECRET, "msg_payg", ts, body),
        "content-type": "application/json",
    }
    before = db.get_profile("user_payg")["payg_credits"]
    with TestClient(app) as client:
        r = client.post("/webhooks/polar", content=body, headers=headers)
    assert r.status_code == 200
    assert r.json()["applied"] is True
    assert db.get_profile("user_payg")["payg_credits"] == before + 1


def test_polar_webhook_rejects_bad_signature(monkeypatch) -> None:
    from app.main import app

    monkeypatch.setenv("POLAR_WEBHOOK_SECRET", _SW_SECRET)
    body = json.dumps({"type": "subscription.created", "data": {}})
    ts = str(int(time.time()))
    headers = {"webhook-id": "m", "webhook-timestamp": ts, "webhook-signature": "v1,deadbeef"}
    with TestClient(app) as client:
        r = client.post("/webhooks/polar", content=body, headers=headers)
    assert r.status_code == 401


def test_polar_webhook_503_when_unconfigured(monkeypatch) -> None:
    from app.main import app

    monkeypatch.delenv("POLAR_WEBHOOK_SECRET", raising=False)
    with TestClient(app) as client:
        r = client.post("/webhooks/polar", content="{}", headers={"webhook-id": "m"})
    assert r.status_code == 503


# ─────────────────────────── quota gate in create_job ───────────────────────────


def test_create_job_quota_gate_blocks_over_limit(monkeypatch) -> None:
    from app.main import app

    monkeypatch.setenv("BILLING_ENABLED", "true")
    uid = "user_gate_over"
    db.set_user_plan(uid, "free")
    month = billing.current_month()
    db.record_usage(uid, "j1", 5.0, month)
    db.record_usage(uid, "j2", 5.0, month)  # 2 видео = лимит free
    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            json={"source_type": "youtube", "source_ref": "x"},
            headers={"X-User-Id": uid},
        )
    assert r.status_code == 402


def test_create_job_quota_gate_allows_fresh_user(monkeypatch) -> None:
    from app import main as main_mod
    from app.main import app

    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setattr(main_mod, "run_pipeline_job", lambda *a, **k: None)
    uid = f"user_gate_ok_{int(time.time())}"  # свежий юзер: 0 расхода → пускаем
    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            json={"source_type": "youtube", "source_ref": "x"},
            headers={"X-User-Id": uid},
        )
    assert r.status_code == 202


def test_create_job_no_gate_without_billing_env() -> None:
    # Дефолт (BILLING_ENABLED не задан): гейт инертен, пайплайн не трогается.
    from app import main as main_mod

    main_mod_run = main_mod.run_pipeline_job
    try:
        main_mod.run_pipeline_job = lambda *a, **k: None  # type: ignore[assignment]
        with TestClient(main_mod.app) as client:
            r = client.post("/jobs", json={"source_type": "youtube", "source_ref": "x"})
        assert r.status_code == 202
    finally:
        main_mod.run_pipeline_job = main_mod_run  # type: ignore[assignment]
