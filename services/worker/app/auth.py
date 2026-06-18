"""Supabase JWT-валидация для воркера (заменяет плейсхолдер X-User-Id).

Фронт шлёт ``Authorization: Bearer <supabase access_token>``. Воркер проверяет подпись
JWT по JWKS проекта (асимметричные ключи ES256/RS256 — рекомендация Supabase) и достаёт
user_id (claim ``sub``). Dual-mode: без ``SUPABASE_URL`` воркер открыт (локалка/тесты).

Гейт активен ⇔ задан ``SUPABASE_URL``. Тогда защищённые эндпоинты требуют валидный токен
(иначе 401); без auth — фолбэк на заголовок ``X-User-Id`` (dev). Опциональный
``SUPABASE_JWT_SECRET`` переключает на HS256 (legacy-проекты); по умолчанию — JWKS.

PURE-функции (``extract_bearer``/``verify_token`` на заданном ключе/``user_id_from_claims``)
покрыты тестами; сетевой fetch JWKS изолирован в ``PyJWKClient`` (lru-кэш).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

_AUDIENCE = "authenticated"
_ASYMMETRIC_ALGS = ["ES256", "RS256"]


class AuthError(Exception):
    """Невалидный/отсутствующий токен → 401 на уровне эндпоинта."""


def extract_bearer(authorization: str | None) -> str | None:
    """``Authorization`` header → токен или None. PURE. Принимает только схему Bearer."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def supabase_auth_enabled() -> bool:
    """Гейт JWT активен ⇔ задан SUPABASE_URL (по нему резолвится JWKS)."""
    return bool(os.environ.get("SUPABASE_URL"))


def jwks_url(base_url: str) -> str:
    """SUPABASE_URL → URL JWKS проекта. PURE."""
    return f"{base_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    # PyJWKClient кэширует ключи внутри; lru_cache держит один клиент на URL.
    return PyJWKClient(url)


def verify_token(
    token: str,
    *,
    jwks_url: str | None = None,
    jwt_secret: str | None = None,
    audience: str = _AUDIENCE,
    leeway: int = 10,
) -> dict[str, Any]:
    """Верифицировать access-token Supabase → claims. Бросает ``AuthError`` на любой провал.

    ``jwt_secret`` задан → HS256 (симметричный/legacy); иначе JWKS-асимметрия (ES256/RS256).
    Проверяет подпись, ``exp`` (с leeway) и ``aud``.
    """
    try:
        if jwt_secret:
            return jwt.decode(
                token, jwt_secret, algorithms=["HS256"], audience=audience, leeway=leeway
            )
        if not jwks_url:
            raise AuthError("no verification key configured")
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=_ASYMMETRIC_ALGS,
            audience=audience,
            leeway=leeway,
        )
    except AuthError:
        raise
    except Exception as e:  # PyJWTError, JWKS-fetch и пр. → единый AuthError (нет тихих фолбэков)
        raise AuthError(str(e)) from e


def user_id_from_claims(claims: dict[str, Any]) -> str:
    """claim ``sub`` → user_id. Бросает ``AuthError``, если нет subject. PURE."""
    sub = claims.get("sub")
    if not sub:
        raise AuthError("token has no subject")
    return str(sub)


def resolve_user_id(authorization: str | None, *, jwt_secret: str | None = None) -> str:
    """``Authorization`` header → user_id (через JWKS текущего SUPABASE_URL).

    Бросает ``AuthError``, если токен отсутствует/невалиден (вызывающий → 401). Зовётся
    только при ``supabase_auth_enabled()``.
    """
    return user_id_from_claims(resolve_claims(authorization, jwt_secret=jwt_secret))


def resolve_claims(authorization: str | None, *, jwt_secret: str | None = None) -> dict[str, Any]:
    """``Authorization`` header → проверенные JWT-claims (Supabase access-token).

    Как ``resolve_user_id``, но отдаёт ВСЕ claims (email/app_metadata/user_metadata нужны
    анти-абьюз-гейту). Бросает ``AuthError`` при отсутствии/невалиде токена (вызывающий → 401).
    Зовётся только при ``supabase_auth_enabled()``.
    """
    base = os.environ.get("SUPABASE_URL", "")
    token = extract_bearer(authorization)
    if not token:
        raise AuthError("missing bearer token")
    secret = jwt_secret or os.environ.get("SUPABASE_JWT_SECRET") or None
    return verify_token(token, jwks_url=jwks_url(base), jwt_secret=secret, audience=_AUDIENCE)


# ─────────────────────── Verified-email (анти-абьюз free-плана) ───────────────────────
# Supabase JWT НЕ несёт авторитетного email_confirmed_at (см. docs/SUPABASE_SETUP.md §6):
# в токене есть email, app_metadata.provider(s), user_metadata.email_verified. Авторитет —
# auth.users.email_confirmed_at (только service-role/Admin API). email_is_verified резолвит
# дёшево из claims (OAuth/metadata), а где неоднозначно — добивает админ-lookup.

_OAUTH_VERIFIED_PROVIDERS = frozenset({"google"})  # email уже проверен провайдером


def email_from_claims(claims: dict[str, Any]) -> str | None:
    """claim ``email`` → нормализованный (lower/strip) адрес или None. PURE."""
    email = str(claims.get("email") or "").strip().lower()
    return email or None


def oauth_verified_from_claims(claims: dict[str, Any]) -> bool:
    """Юзер вошёл через внешний OAuth с уже-проверенным email (Google)? PURE.

    Google валидирует email до выдачи токена → такие аккаунты считаем verified без lookup
    (founder: не блокировать Google-входы). Проверяем ``app_metadata.provider`` и список
    ``providers`` (мог быть привязан вторым методом).
    """
    meta = claims.get("app_metadata") or {}
    provider = str(meta.get("provider") or "")
    providers = meta.get("providers") or []
    names = {provider, *(str(p) for p in providers)}
    return bool(names & _OAUTH_VERIFIED_PROVIDERS)


def metadata_email_verified(claims: dict[str, Any]) -> bool:
    """``user_metadata.email_verified is True``? PURE. GoTrue ставит флаг при подтверждении."""
    return (claims.get("user_metadata") or {}).get("email_verified") is True


def email_is_verified(claims: dict[str, Any]) -> bool:
    """Email пользователя подтверждён? (FREE-гейт). Дёшево из claims → дорого админ-lookup.

    Порядок: (1) внешний OAuth (Google) → True (провайдер уже проверил email); (2) флаг
    ``user_metadata.email_verified`` → True; (3) авторитетный админ-lookup
    ``email_confirmed_at`` по user_id (service-role). Никаких тихих фолбэков: ошибка lookup
    всплывает (вызывающий решает HTTP-код)."""
    if oauth_verified_from_claims(claims):
        return True
    if metadata_email_verified(claims):
        return True
    from app import supa

    return supa.auth_user_email_confirmed(user_id_from_claims(claims))
