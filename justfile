# ClipFlow task runner. На Windows рецепты исполняет PowerShell (тут PS 5.1: без &&).
# Fail-fast в `check` обеспечивают ЗАВИСИМОСТИ рецептов, а не shell-цепочки.
set windows-shell := ["powershell.exe", "-NoProfile", "-Command"]

# Список рецептов (bare `just`)
default:
    @just --list

# ── установка ──
install: install-node install-py
install-node:
    pnpm install
install-py:
    cd services/worker; uv sync

# ── dev-серверы (Windows: в двух терминалах `just web` / `just worker`) ──
web:
    pnpm --filter web dev
worker:
    cd services/worker; uv run uvicorn app.main:app --reload --port 8000

# ── codegen контракта (TS руками НЕ пишем: models.py → contract.json → types.ts) ──
types: types-ts
types-schema:
    cd services/worker; uv run python -m app.export_schema
types-ts: types-schema
    cd packages/shared; pnpm json2ts

# ── линт ──
lint: lint-py lint-web
lint-py:
    cd services/worker; uv run ruff check app tests
lint-web:
    pnpm --filter web lint

# ── формат ──
format: format-web format-py
format-web:
    pnpm format
format-py:
    cd services/worker; uv run ruff format app tests

# ── статическая типизация ──
typecheck: typecheck-py typecheck-web
typecheck-py:
    cd services/worker; uv run mypy app
typecheck-web:
    pnpm --filter web exec tsc --noEmit

# ── юнит-тесты (быстро, без сети) ──
test-unit:
    cd services/worker; uv run pytest tests/unit -q

# ── e2e на одном реальном сэмпле (наполнится на H1: app/run.py) ──
e2e SAMPLE:
    cd services/worker; uv run python -m app.run "{{SAMPLE}}"

# ── anti-drift: перегенерить типы и убедиться в отсутствии расхождений ──
anti-drift: types
    git diff --exit-code packages/shared

# ── ГЛАВНЫЙ ГЕЙТ перед коммитом: lint + типы + тесты + anti-drift ──
check: lint typecheck test-unit anti-drift
