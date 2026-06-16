"""CORS: продакшен-origin'ы браузера должны проходить прелайт к API воркера.

Регрессия (домен-переезд, docs/SEO_STRATEGY.md §4): апекс ``quip.ink`` переехал на
проект ``quip-app``, но ``allow_origin_regex`` воркера знал только ``app.quip.ink`` →
браузерные запросы к воркеру (``/usage``, ``/jobs`` …) с ``quip.ink`` резались CORS-
политикой (прелайт 400, нет ``Access-Control-Allow-Origin``), а ``UsageMeter`` молча
падал в Free. Пиннит, что апекс/www/app/vercel-превью/localhost проходят, а чужой — нет.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _preflight(origin: str):
    return client.options(
        "/usage",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )


def test_cors_allows_production_origins() -> None:
    for origin in (
        "https://quip.ink",
        "https://www.quip.ink",
        "https://app.quip.ink",
        "https://quip-app-preview.vercel.app",
        "http://localhost:3000",
    ):
        resp = _preflight(origin)
        assert resp.headers.get("access-control-allow-origin") == origin, origin


def test_cors_rejects_foreign_origin() -> None:
    resp = _preflight("https://evil.example.com")
    assert resp.headers.get("access-control-allow-origin") is None
