"""JWT-валидация Supabase (auth.py). PURE-помощники + HS256-путь decode (без сети).

Асимметричный JWKS-путь (ES256/RS256) проверяется живым e2e-входом — тут тестируем
извлечение Bearer, decode/exp/aud/подпись на HS256, извлечение user_id и resolve_user_id.
"""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app import auth

_SECRET = "test-hs256-secret-at-least-32-bytes-long!!"


def _token(**claims) -> str:
    base = {"sub": "user-123", "aud": "authenticated", "exp": int(time.time()) + 3600}
    base.update(claims)
    return jwt.encode(base, _SECRET, algorithm="HS256")


class TestExtractBearer:
    def test_valid(self) -> None:
        assert auth.extract_bearer("Bearer abc.def.ghi") == "abc.def.ghi"
        assert auth.extract_bearer("bearer abc") == "abc"  # схема нечувствительна к регистру

    def test_rejects_non_bearer_and_empty(self) -> None:
        assert auth.extract_bearer(None) is None
        assert auth.extract_bearer("") is None
        assert auth.extract_bearer("Basic abc") is None
        assert auth.extract_bearer("Bearer ") is None
        assert auth.extract_bearer("abc.def") is None


class TestJwksUrl:
    def test_builds_endpoint(self) -> None:
        assert (
            auth.jwks_url("https://ref.supabase.co")
            == "https://ref.supabase.co/auth/v1/.well-known/jwks.json"
        )
        # лишний слэш не дублируется
        assert auth.jwks_url("https://ref.supabase.co/").endswith("/auth/v1/.well-known/jwks.json")


class TestVerifyTokenHs256:
    def test_valid_token_returns_claims(self) -> None:
        claims = auth.verify_token(_token(), jwt_secret=_SECRET)
        assert claims["sub"] == "user-123"
        assert claims["aud"] == "authenticated"

    def test_expired_token_rejected(self) -> None:
        with pytest.raises(auth.AuthError):
            auth.verify_token(_token(exp=int(time.time()) - 100), jwt_secret=_SECRET)

    def test_wrong_secret_rejected(self) -> None:
        with pytest.raises(auth.AuthError):
            auth.verify_token(_token(), jwt_secret="a-different-secret-also-32-bytes-long!!")

    def test_wrong_audience_rejected(self) -> None:
        with pytest.raises(auth.AuthError):
            auth.verify_token(_token(aud="anon"), jwt_secret=_SECRET)

    def test_no_key_configured_raises(self) -> None:
        with pytest.raises(auth.AuthError):
            auth.verify_token(_token())  # ни jwt_secret, ни jwks_url


class TestUserIdFromClaims:
    def test_extracts_sub(self) -> None:
        assert auth.user_id_from_claims({"sub": "abc"}) == "abc"

    def test_missing_sub_raises(self) -> None:
        with pytest.raises(auth.AuthError):
            auth.user_id_from_claims({"aud": "authenticated"})


class TestResolveUserId:
    def test_valid_bearer_resolves_via_secret(self, monkeypatch) -> None:
        monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
        monkeypatch.setenv("SUPABASE_JWT_SECRET", _SECRET)
        uid = auth.resolve_user_id(f"Bearer {_token()}")
        assert uid == "user-123"

    def test_missing_token_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
        with pytest.raises(auth.AuthError):
            auth.resolve_user_id(None)

    def test_supabase_auth_enabled_flag(self, monkeypatch) -> None:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        assert auth.supabase_auth_enabled() is False
        monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
        assert auth.supabase_auth_enabled() is True


# ─────────────────────────── гейт create_job через JWT (endpoint) ───────────────────────────
# HS256-путь (SUPABASE_JWT_SECRET) → валидация без сети; auth включён через SUPABASE_URL.


def test_create_job_401_without_token(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", _SECRET)
    from app.main import app

    with TestClient(app) as client:
        r = client.post("/jobs", json={"source_type": "youtube", "source_ref": "x"})
    assert r.status_code == 401


def test_create_job_202_with_valid_token(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", _SECRET)
    monkeypatch.delenv("BILLING_ENABLED", raising=False)  # auth on, quota off
    from app import main as main_mod
    from app.main import app

    monkeypatch.setattr(main_mod, "run_pipeline_job", lambda *a, **k: None)
    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            json={"source_type": "youtube", "source_ref": "x"},
            headers={"Authorization": f"Bearer {_token()}"},
        )
    assert r.status_code == 202


def test_create_job_401_with_expired_token(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", _SECRET)
    from app.main import app

    expired = _token(exp=int(time.time()) - 100)
    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            json={"source_type": "youtube", "source_ref": "x"},
            headers={"Authorization": f"Bearer {expired}"},
        )
    assert r.status_code == 401


def test_usage_endpoint_defaults_without_user(monkeypatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)  # auth off → нет юзера → дефолт free
    from app.main import app

    with TestClient(app) as client:
        r = client.get("/usage")
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "free"
    assert body["monthly_credits"] == 2
