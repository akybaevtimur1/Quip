"""Анти-абьюз: verified-email гейт (auth.py PURE-хелперы + free-job enforcement).

Бесплатный план абьюзят непроверенными ящиками. Гейт (серверно, авторитетно): FREE-план
без подтверждённого email → отказ 4xx. Платные — мимо. Google OAuth = уже verified Google
(не блокируем). Verified резолвится из JWT-claims (provider google / user_metadata.email_verified),
а где неоднозначно — админ-lookup email_confirmed_at (тут замокан).

PURE-хелперы (email_from_claims / oauth_verified_from_claims / metadata_email_verified)
покрыты без сети; сам endpoint-гейт — через TestClient с HS256-токеном и моками профиля.
"""

from __future__ import annotations

import time

import jwt
from fastapi.testclient import TestClient

from app import auth

_SECRET = "test-hs256-secret-at-least-32-bytes-long!!"


def _token(**claims) -> str:
    base = {"sub": "user-123", "aud": "authenticated", "exp": int(time.time()) + 3600}
    base.update(claims)
    return jwt.encode(base, _SECRET, algorithm="HS256")


class TestEmailFromClaims:
    def test_extracts_and_lowercases(self) -> None:
        assert auth.email_from_claims({"email": "User@Example.com"}) == "user@example.com"

    def test_missing_email_is_none(self) -> None:
        assert auth.email_from_claims({"sub": "x"}) is None
        assert auth.email_from_claims({"email": ""}) is None


class TestOAuthVerifiedFromClaims:
    def test_google_provider_is_verified(self) -> None:
        # Google уже проверил email → considered verified, lookup не нужен.
        assert auth.oauth_verified_from_claims({"app_metadata": {"provider": "google"}}) is True

    def test_google_in_providers_list_is_verified(self) -> None:
        claims = {"app_metadata": {"provider": "email", "providers": ["email", "google"]}}
        assert auth.oauth_verified_from_claims(claims) is True

    def test_email_provider_not_oauth_verified(self) -> None:
        # email/password или OTP — НЕ внешний OAuth → этот хелпер не считает verified.
        assert auth.oauth_verified_from_claims({"app_metadata": {"provider": "email"}}) is False
        assert auth.oauth_verified_from_claims({}) is False


class TestMetadataEmailVerified:
    def test_true_flag(self) -> None:
        assert auth.metadata_email_verified({"user_metadata": {"email_verified": True}}) is True

    def test_false_or_missing(self) -> None:
        assert auth.metadata_email_verified({"user_metadata": {"email_verified": False}}) is False
        assert auth.metadata_email_verified({"user_metadata": {}}) is False
        assert auth.metadata_email_verified({}) is False


# ─────────────────────────── endpoint-гейт (free-job) ───────────────────────────
# auth on (SUPABASE_URL + HS256 secret), billing on. Профиль/usage/админ-lookup замоканы.


def _client_env(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", _SECRET)
    monkeypatch.setenv("BILLING_ENABLED", "true")


def _stub_profile(monkeypatch, plan: str) -> None:
    from app import db
    from app import main as main_mod

    monkeypatch.setattr(db, "get_profile", lambda uid: {"plan": plan, "payg_credits": 0})
    monkeypatch.setattr(
        db, "get_monthly_usage", lambda uid, month: {"videos": 0, "minutes": 0.0, "credits": 0}
    )
    monkeypatch.setattr(main_mod, "run_pipeline_job", lambda *a, **k: None)


def test_free_unverified_email_rejected(monkeypatch) -> None:
    _client_env(monkeypatch)
    _stub_profile(monkeypatch, "free")
    from app import auth as auth_mod
    from app.main import app

    # Авторитетная проверка verified → False (email не подтверждён).
    monkeypatch.setattr(auth_mod, "email_is_verified", lambda claims: False)
    tok = _token(email="new@example.com", app_metadata={"provider": "email"})
    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            json={"source_type": "youtube", "source_ref": "x"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    assert r.status_code == 403
    assert "verify" in r.json()["detail"].lower()


def test_free_verified_email_allowed(monkeypatch) -> None:
    _client_env(monkeypatch)
    _stub_profile(monkeypatch, "free")
    from app import auth as auth_mod
    from app.main import app

    monkeypatch.setattr(auth_mod, "email_is_verified", lambda claims: True)
    tok = _token(email="ok@example.com", app_metadata={"provider": "email"})
    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            json={"source_type": "youtube", "source_ref": "x"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    assert r.status_code == 202


def test_free_disposable_email_rejected(monkeypatch) -> None:
    _client_env(monkeypatch)
    _stub_profile(monkeypatch, "free")
    from app import auth as auth_mod
    from app.main import app

    # Verified True, но домен одноразовый → всё равно отказ (анти-абьюз).
    monkeypatch.setattr(auth_mod, "email_is_verified", lambda claims: True)
    tok = _token(email="abuser@mailinator.com", app_metadata={"provider": "email"})
    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            json={"source_type": "youtube", "source_ref": "x"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    assert r.status_code == 403
    assert "real email" in r.json()["detail"].lower()


def test_google_oauth_user_not_blocked(monkeypatch) -> None:
    # Google OAuth: email уже verified Google → НЕ блокируем (даже без админ-lookup).
    _client_env(monkeypatch)
    _stub_profile(monkeypatch, "free")
    from app.main import app

    tok = _token(email="g@gmail.com", app_metadata={"provider": "google", "providers": ["google"]})
    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            json={"source_type": "youtube", "source_ref": "x"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    assert r.status_code == 202


def test_paid_plan_bypasses_verification(monkeypatch) -> None:
    _client_env(monkeypatch)
    _stub_profile(monkeypatch, "starter")
    from app import auth as auth_mod
    from app.main import app

    # Платный план: даже неподтверждённый/одноразовый email НЕ гейтится (заплатил → не абьюз).
    monkeypatch.setattr(auth_mod, "email_is_verified", lambda claims: False)
    tok = _token(email="x@mailinator.com", app_metadata={"provider": "email"})
    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            json={"source_type": "youtube", "source_ref": "x"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    assert r.status_code == 202


def test_email_is_verified_uses_oauth_then_metadata_then_admin(monkeypatch) -> None:
    # email_is_verified: OAuth google → True без lookup; иначе metadata flag; иначе админ-lookup.
    # google → True
    assert auth.email_is_verified({"app_metadata": {"provider": "google"}}) is True
    # email provider + metadata verified → True (без админ-вызова)
    assert (
        auth.email_is_verified(
            {"app_metadata": {"provider": "email"}, "user_metadata": {"email_verified": True}}
        )
        is True
    )


def test_email_is_verified_admin_lookup_fallback(monkeypatch) -> None:
    # Нет OAuth, нет metadata-флага → авторитетный админ-lookup email_confirmed_at.
    from app import supa

    monkeypatch.setattr(supa, "auth_user_email_confirmed", lambda uid: True)
    claims = {"sub": "u1", "app_metadata": {"provider": "email"}, "user_metadata": {}}
    assert auth.email_is_verified(claims) is True

    monkeypatch.setattr(supa, "auth_user_email_confirmed", lambda uid: False)
    assert auth.email_is_verified(claims) is False
