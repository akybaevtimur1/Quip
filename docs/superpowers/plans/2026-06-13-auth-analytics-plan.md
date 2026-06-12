# Auth & Analytics Layer — Implementation Plan

> ⚠️ **ЧАСТИЧНО УСТАРЕЛ (2026-06-13).** Фаундер выбрал РЕАЛЬНЫЙ масштаб + облачный воркер →
> деплой/инфра-часть заменена на `2026-06-13-infra-scaling-cloud-worker.md`. **Сначала читай
> тот документ.** Auth-ЛОГИКА (Supabase, JWT, /admin) тут валидна, но при исполнении на масштабе
> учти деформации (см. §4 инфра-плана «carried-forward баги»):
> - **CORS:** `allow_origins=["https://*.vercel.app"]` СЛОМАН в Starlette → используй
>   `allow_origin_regex=r"https://.*\.vercel\.app$"` (Task 5).
> - **app/auth.py:** HS256+shared-secret → перейти на JWKS (RS256) при асимметричных ключах.
> - **jobs/clip_edits:** SQLite (Task 4) → Supabase Postgres + RLS по user_id на масштабе.
> - **media:** локальный `/media` → объектное хранилище + CDN.
> - **middleware:** `getUser()` → `getClaims()` (локальная верификация, меньше латентности).
> - **деплой:** ngrok (Task 13) ВЫКИНУТ — free-тариф (20k req/мес, 2ч-сессия) не годен;
>   воркер деплоится в облако со стабильным URL.
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить Supabase Auth (email/пароль + Google OAuth) поверх существующего MVP-редактора, изолировать джобы по юзеру и добавить /admin страницу аналитики.

**Architecture:** Supabase Auth хранит пользователей в облаке; JWT access_token от Supabase передаётся из браузера в воркер через `Authorization: Bearer`; воркер верифицирует токен локально через PyJWT + SUPABASE_JWT_SECRET; джобы в SQLite получают колонку `user_id`. Если SUPABASE_JWT_SECRET пуст — auth пропускается (dev-режим без Supabase).

**Tech Stack:** `@supabase/ssr`, Supabase Auth (cloud), PyJWT 2.8+, FastAPI Depends, SQLite ALTER TABLE migration, Next.js App Router middleware, Vercel deployment.

**Spec:** `docs/superpowers/specs/2026-06-13-auth-analytics-design.md`

---

## File Map

### Создать
```
services/worker/app/auth.py
services/worker/tests/unit/test_auth.py
services/worker/tests/unit/test_db_auth.py
apps/web/lib/supabase/client.ts
apps/web/lib/supabase/server.ts
apps/web/app/api/auth/callback/route.ts
apps/web/app/admin/page.tsx
```

### Изменить
```
services/worker/pyproject.toml            ← добавить PyJWT
services/worker/app/config.py             ← supabase_jwt_secret, worker_admin_key
services/worker/app/db.py                 ← user_id колонка + migration + get_admin_stats
services/worker/app/main.py               ← Depends(get_current_user) на /jobs/*, CORS, /admin/stats
services/worker/tests/unit/test_editor_api.py   ← auth dependency_override в _client()
services/worker/tests/unit/test_chapters_api.py ← то же
apps/web/middleware.ts                    ← заменить passcode на Supabase session
apps/web/app/login/page.tsx               ← email+пароль + кнопка Google
apps/web/lib/api.ts                       ← getAuthHeaders() + обновить все fetch-вызовы
```

### Удалить
```
apps/web/app/api/auth/route.ts            ← старый passcode-эндпоинт
```

---

## Task 1: Supabase проект — ручная настройка

**Files:** нет кода

- [ ] **Шаг 1: Создать проект**

  Открыть https://supabase.com → New project → придумать название (например `clipflow`).
  Region: ближайший. Записать данные.

- [ ] **Шаг 2: Включить Email auth**

  Dashboard → Authentication → Providers → Email → Enable.
  «Confirm email»: по желанию (для demo можно выключить).

- [ ] **Шаг 3: Включить Google OAuth**

  Dashboard → Authentication → Providers → Google → Enable.
  Нужен Google OAuth App: https://console.cloud.google.com → APIs → Credentials → Create OAuth Client.
  Redirect URI: `https://<ваш-supabase-project>.supabase.co/auth/v1/callback`
  Скопировать Client ID + Client Secret в Supabase.

- [ ] **Шаг 4: Добавить redirect URLs**

  Dashboard → Authentication → URL Configuration → Redirect URLs:
  ```
  http://localhost:3000/api/auth/callback
  https://<ваш-vercel-домен>.vercel.app/api/auth/callback
  ```

- [ ] **Шаг 5: Записать ключи**

  Dashboard → Project Settings → API. Сохранить:
  ```
  NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
  NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
  SUPABASE_SERVICE_ROLE_KEY=eyJ...  (никогда не коммитить)
  ```
  Dashboard → Project Settings → API → JWT Settings → JWT Secret. Сохранить:
  ```
  SUPABASE_JWT_SECRET=...
  ```

---

## Task 2: Worker — PyJWT + app/auth.py (TDD)

**Files:**
- Create: `services/worker/app/auth.py`
- Create: `services/worker/tests/unit/test_auth.py`
- Modify: `services/worker/pyproject.toml`

- [ ] **Шаг 1: Написать падающий тест**

  Создать `services/worker/tests/unit/test_auth.py`:

  ```python
  """Тесты JWT-верификации воркера (app.auth.get_current_user)."""

  import time

  import jwt
  import pytest
  from fastapi import HTTPException


  JWT_SECRET = "test-jwt-secret-32chars-minimum!!"


  def _make_token(
      user_id: str = "user-uuid-123",
      *,
      expired: bool = False,
      secret: str = JWT_SECRET,
  ) -> str:
      exp = int(time.time()) + (-1 if expired else 3600)
      return jwt.encode(
          {"sub": user_id, "aud": "authenticated", "exp": exp},
          secret,
          algorithm="HS256",
      )


  @pytest.fixture(autouse=True)
  def _patch_secret(monkeypatch):
      from app import config

      class _FakeSettings:
          supabase_jwt_secret = JWT_SECRET

      monkeypatch.setattr(config, "get_settings", lambda: _FakeSettings())


  def test_valid_token_returns_user_id():
      from app.auth import get_current_user

      token = _make_token("user-abc-456")
      assert get_current_user(f"Bearer {token}") == "user-abc-456"


  def test_missing_header_raises_401():
      from app.auth import get_current_user

      with pytest.raises(HTTPException) as exc:
          get_current_user(None)
      assert exc.value.status_code == 401


  def test_no_bearer_prefix_raises_401():
      from app.auth import get_current_user

      with pytest.raises(HTTPException) as exc:
          get_current_user("Basic dXNlcjpwYXNz")
      assert exc.value.status_code == 401


  def test_invalid_token_raises_401():
      from app.auth import get_current_user

      with pytest.raises(HTTPException) as exc:
          get_current_user("Bearer not.a.valid.jwt")
      assert exc.value.status_code == 401


  def test_expired_token_raises_401():
      from app.auth import get_current_user

      token = _make_token(expired=True)
      with pytest.raises(HTTPException) as exc:
          get_current_user(f"Bearer {token}")
      assert exc.value.status_code == 401


  def test_empty_secret_returns_anonymous():
      """Когда SUPABASE_JWT_SECRET не задан — dev-режим, auth пропускается."""
      from app import config, auth as auth_mod

      class _NoSecret:
          supabase_jwt_secret = ""

      import importlib
      # reload чтобы не было кэша из других тестов
      old = config.get_settings
      config.get_settings = lambda: _NoSecret()
      try:
          result = auth_mod.get_current_user("Bearer invalid-token")
          assert result == "anonymous"
      finally:
          config.get_settings = old
  ```

- [ ] **Шаг 2: Запустить — убедиться, что падает**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv run pytest tests/unit/test_auth.py -v 2>&1 | head -20
  ```

  Ожидаем: `ModuleNotFoundError: No module named 'app.auth'` или ImportError на `jwt`.

- [ ] **Шаг 3: Добавить PyJWT в pyproject.toml**

  В `services/worker/pyproject.toml` найти блок `[project]` → `dependencies` и добавить:
  ```toml
  "PyJWT>=2.8",
  ```

  Затем:
  ```powershell
  uv sync
  ```

- [ ] **Шаг 4: Создать app/auth.py**

  Создать `services/worker/app/auth.py`:

  ```python
  """JWT-верификация Supabase (app/auth.py).

  get_current_user — FastAPI Dependency. Принимает Bearer-токен, верифицирует
  HS256 подписью из SUPABASE_JWT_SECRET, возвращает user_id (sub-claim).

  Dev-режим: если SUPABASE_JWT_SECRET пуст — auth пропускается, возвращает
  "anonymous". Это позволяет запускать воркер локально без Supabase.
  """

  from __future__ import annotations

  import jwt
  from fastapi import Header, HTTPException

  from app.config import get_settings


  def get_current_user(authorization: str | None = Header(None)) -> str:
      """Извлечь и верифицировать Supabase JWT. Вернуть user_id (UUID)."""
      s = get_settings()

      if not s.supabase_jwt_secret:
          return "anonymous"

      if not authorization or not authorization.startswith("Bearer "):
          raise HTTPException(status_code=401, detail="Missing Bearer token")

      token = authorization.removeprefix("Bearer ")
      try:
          payload = jwt.decode(
              token,
              s.supabase_jwt_secret,
              algorithms=["HS256"],
              audience="authenticated",
          )
          return str(payload["sub"])
      except jwt.PyJWTError as exc:
          raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
  ```

- [ ] **Шаг 5: Запустить тесты — убедиться, что зелёные**

  ```powershell
  uv run pytest tests/unit/test_auth.py -v
  ```

  Ожидаем: все 6 тестов PASSED.

- [ ] **Шаг 6: Коммит**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git add services/worker/pyproject.toml services/worker/app/auth.py services/worker/tests/unit/test_auth.py
  "feat(auth): JWT verification — app/auth.py + PyJWT dep, 6 tests" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 3: Worker — config.py новые поля

**Files:**
- Modify: `services/worker/app/config.py`

- [ ] **Шаг 1: Добавить поля в Settings**

  В `services/worker/app/config.py` в класс `Settings` добавить после `reframe_split_enabled`:

  ```python
  # auth
  supabase_jwt_secret: str = ""  # Supabase → Settings → API → JWT Secret; "" = dev-bypass
  worker_admin_key: str = ""     # для GET /admin/stats; "" = эндпоинт отключён
  ```

- [ ] **Шаг 2: Проверить что `just check` зелёный**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow"
  just check
  ```

- [ ] **Шаг 3: Коммит**

  ```powershell
  git add services/worker/app/config.py
  "feat(auth): add supabase_jwt_secret + worker_admin_key to config" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 4: Worker — db.py: user_id колонка + migration + admin stats (TDD)

**Files:**
- Create: `services/worker/tests/unit/test_db_auth.py`
- Modify: `services/worker/app/db.py`

- [ ] **Шаг 1: Написать падающие тесты**

  Создать `services/worker/tests/unit/test_db_auth.py`:

  ```python
  """Тесты user_id в jobs-таблице и get_admin_stats."""

  import sqlite3

  import pytest

  from app import db


  def test_insert_job_stores_user_id(monkeypatch, tmp_path):
      monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
      db.init_db()
      db.insert_job("job1", "youtube", "url1", user_id="user-uuid-abc")

      conn = sqlite3.connect(str(tmp_path / "jobs.db"))
      conn.row_factory = sqlite3.Row
      row = conn.execute("SELECT user_id FROM jobs WHERE id='job1'").fetchone()
      conn.close()
      assert row["user_id"] == "user-uuid-abc"


  def test_insert_job_without_user_id_stores_null(monkeypatch, tmp_path):
      """Backward compat: старые вызовы без user_id работают."""
      monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
      db.init_db()
      db.insert_job("job1", "youtube", "url1")

      conn = sqlite3.connect(str(tmp_path / "jobs.db"))
      conn.row_factory = sqlite3.Row
      row = conn.execute("SELECT user_id FROM jobs WHERE id='job1'").fetchone()
      conn.close()
      assert row["user_id"] is None


  def test_init_db_migrates_legacy_table(monkeypatch, tmp_path):
      """init_db добавляет колонку user_id в существующую БД без неё."""
      monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")

      # Создать старую схему без user_id
      conn = sqlite3.connect(str(tmp_path / "jobs.db"))
      conn.execute("""CREATE TABLE jobs (
          id TEXT PRIMARY KEY, status TEXT, stage TEXT, progress INTEGER,
          source_type TEXT, source_ref TEXT, error TEXT,
          clips_json TEXT, cost_usd REAL, duration_sec REAL, elapsed_sec REAL,
          created_at REAL, updated_at REAL
      )""")
      conn.execute("""CREATE TABLE IF NOT EXISTS clip_edits (
          job_id TEXT, clip_id TEXT, version INTEGER, edit_json TEXT,
          render_status TEXT, render_url TEXT, render_error TEXT, updated_at REAL,
          PRIMARY KEY (job_id, clip_id)
      )""")
      conn.commit()
      conn.close()

      db.init_db()  # должен мигрировать

      conn = sqlite3.connect(str(tmp_path / "jobs.db"))
      cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
      conn.close()
      assert "user_id" in cols


  def test_get_admin_stats_groups_by_user(monkeypatch, tmp_path):
      monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
      db.init_db()
      db.insert_job("job1", "youtube", "u1", user_id="userA")
      db.insert_job("job2", "youtube", "u2", user_id="userA")
      db.insert_job("job3", "youtube", "u3", user_id="userB")
      db.insert_job("job4", "youtube", "u4")  # без user_id — не попадает в stats

      # Проставить cost_usd напрямую
      conn = sqlite3.connect(str(tmp_path / "jobs.db"))
      conn.execute("UPDATE jobs SET cost_usd=0.10 WHERE id='job1'")
      conn.execute("UPDATE jobs SET cost_usd=0.06 WHERE id='job2'")
      conn.commit()
      conn.close()

      stats = db.get_admin_stats()

      assert stats["totals"]["jobs"] == 3  # job4 без user_id исключён
      assert abs(stats["totals"]["cost_usd"] - 0.16) < 1e-4

      user_a = next(u for u in stats["users"] if u["user_id"] == "userA")
      assert user_a["job_count"] == 2
      assert abs(user_a["total_cost_usd"] - 0.16) < 1e-4

      user_b = next(u for u in stats["users"] if u["user_id"] == "userB")
      assert user_b["job_count"] == 1
      assert user_b["total_cost_usd"] == 0.0


  def test_get_admin_stats_empty_db(monkeypatch, tmp_path):
      monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
      db.init_db()
      stats = db.get_admin_stats()
      assert stats == {"users": [], "totals": {"jobs": 0, "cost_usd": 0.0}}
  ```

- [ ] **Шаг 2: Запустить — убедиться что падают**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv run pytest tests/unit/test_db_auth.py -v 2>&1 | head -20
  ```

  Ожидаем: ошибки — `insert_job()` не принимает `user_id`, нет `get_admin_stats`.

- [ ] **Шаг 3: Обновить db.py**

  В `services/worker/app/db.py`:

  **3a. Добавить _migrate_db helper** (после функции `_conn`):
  ```python
  def _migrate_db(c: sqlite3.Connection) -> None:
      """Добавить колонку user_id в существующую jobs-таблицу (backward compat)."""
      cols = {row[1] for row in c.execute("PRAGMA table_info(jobs)")}
      if "user_id" not in cols:
          c.execute("ALTER TABLE jobs ADD COLUMN user_id TEXT")
  ```

  **3b. Обновить CREATE TABLE в init_db** — добавить `user_id TEXT` в схему:
  ```python
  c.execute(
      """CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          status TEXT, stage TEXT, progress INTEGER,
          source_type TEXT, source_ref TEXT, error TEXT,
          clips_json TEXT, cost_usd REAL, duration_sec REAL, elapsed_sec REAL,
          created_at REAL, updated_at REAL,
          user_id TEXT
      )"""
  )
  ```

  **3c. Вызвать _migrate_db в init_db** (после CREATE TABLE jobs):
  ```python
  _migrate_db(c)
  ```

  **3d. Обновить insert_job** — добавить параметр `user_id`:
  ```python
  def insert_job(
      job_id: str, source_type: str, source_ref: str, *, user_id: str | None = None
  ) -> None:
      now = time.time()
      with _conn() as c:
          c.execute(
              "INSERT INTO jobs"
              " (id,status,stage,progress,source_type,source_ref,user_id,created_at,updated_at)"
              " VALUES (?,?,?,?,?,?,?,?,?)",
              (job_id, "queued", "queued", 0, source_type, source_ref, user_id, now, now),
          )
  ```

  **3e. Добавить get_job_user_id** (после insert_job):
  ```python
  def get_job_user_id(job_id: str) -> str | None:
      """Вернуть user_id джоба (для проверки владельца). None если джоб не найден."""
      with _conn() as c:
          row = c.execute("SELECT user_id FROM jobs WHERE id=?", (job_id,)).fetchone()
      return row["user_id"] if row else None
  ```

  **3f. Добавить get_admin_stats** (в конец файла):
  ```python
  def get_admin_stats() -> dict[str, Any]:
      """Агрегированная статистика джобов по user_id. Для /admin/stats эндпоинта."""
      with _conn() as c:
          rows = c.execute(
              "SELECT user_id,"
              " COUNT(*) as job_count,"
              " SUM(COALESCE(cost_usd, 0)) as total_cost_usd"
              " FROM jobs WHERE user_id IS NOT NULL"
              " GROUP BY user_id"
          ).fetchall()
      users = [
          {
              "user_id": r["user_id"],
              "job_count": r["job_count"],
              "total_cost_usd": round(r["total_cost_usd"], 4),
          }
          for r in rows
      ]
      return {
          "users": users,
          "totals": {
              "jobs": sum(u["job_count"] for u in users),
              "cost_usd": round(sum(u["total_cost_usd"] for u in users), 4),
          },
      }
  ```

  Добавить `from typing import Any` в импорты если не было.

- [ ] **Шаг 4: Запустить тесты — убедиться что зелёные**

  ```powershell
  uv run pytest tests/unit/test_db_auth.py -v
  ```

  Ожидаем: все 5 тестов PASSED.

- [ ] **Шаг 5: Убедиться что старые db-тесты не сломались**

  ```powershell
  uv run pytest tests/unit/test_db.py -v
  ```

  Ожидаем: все 3 теста PASSED (row_to_wire не трогали).

- [ ] **Шаг 6: Коммит**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git add services/worker/app/db.py services/worker/tests/unit/test_db_auth.py
  "feat(auth): user_id column + migration + get_admin_stats, 5 tests" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 5: Worker — main.py: auth gates + CORS + /admin/stats

**Files:**
- Modify: `services/worker/app/main.py`

- [ ] **Шаг 1: Добавить импорт auth + обновить CORS**

  В начало `app/main.py` добавить импорт:
  ```python
  from app.auth import get_current_user
  ```

  Обновить `CORSMiddleware`:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=[
          "http://localhost:3000",
          "https://*.vercel.app",
      ],
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

- [ ] **Шаг 2: Обновить create_job — добавить user_id**

  ```python
  @app.post("/jobs", status_code=202)
  def create_job(
      body: CreateJobBody,
      bg: BackgroundTasks,
      user_id: str = Depends(get_current_user),
  ) -> dict[str, Any]:
      """Создать задачу: запись queued в БД + фоновый прогон пайплайна."""
      job_id = f"job_{uuid.uuid4().hex[:12]}"
      db.insert_job(job_id, body.source_type, body.source_ref, user_id=user_id)
      bg.add_task(run_pipeline_job, job_id, body.source_type, body.source_ref, body.max_clips)
      return {"id": job_id, "status": "queued", "stage": "queued", "progress": 0}
  ```

- [ ] **Шаг 3: Обновить get_job — проверить владельца**

  ```python
  @app.get("/jobs/{job_id}")
  def get_job(
      job_id: str,
      user_id: str = Depends(get_current_user),
  ) -> dict[str, Any]:
      """Статус задачи из SQLite. 404 если нет или чужой."""
      job = db.get_job(job_id)
      if job is None:
          raise HTTPException(status_code=404, detail="job not found")
      owner = db.get_job_user_id(job_id)
      # owner=None — старый анонимный джоб (backward compat), не показываем
      if owner is not None and owner != user_id:
          raise HTTPException(status_code=404, detail="job not found")
      return job
  ```

- [ ] **Шаг 4: Добавить Depends(get_current_user) ко всем остальным /jobs/* эндпоинтам**

  Для каждого из следующих эндпоинтов добавить `user_id: str = Depends(get_current_user)` в параметры (используется только для проверки auth, владельца не проверяем — job_id не угадать):

  ```
  get_clip_edit       → добавить user_id: str = Depends(get_current_user)
  patch_clip_edit     → то же
  op_trim             → то же
  op_add_section      → то же
  op_extend           → то же
  op_crop             → то же
  post_render         → то же
  get_render          → то же
  get_analysis        → то же
  apply_preset_to_clip → то же
  create_preset        → то же
  ```

  Пример (все одинаковые):
  ```python
  @app.get("/jobs/{job_id}/clips/{clip_id}/edit")
  def get_clip_edit(
      job_id: str,
      clip_id: str,
      user_id: str = Depends(get_current_user),  # ← добавить
  ) -> dict[str, Any]:
      ...  # тело не меняется
  ```

  Для `get_chapters` и `get_timeline` (если есть в файле) — то же самое.

- [ ] **Шаг 5: Добавить /admin/stats эндпоинт**

  В конец файла (перед концом) добавить:
  ```python
  # ──────────────────────────── Admin endpoints ────────────────────────────


  @app.get("/admin/stats")
  def admin_stats(x_admin_key: str | None = Header(None)) -> dict[str, Any]:
      """Агрегированная статистика джобов по юзерам. Требует X-Admin-Key."""
      s = get_settings()
      if not s.worker_admin_key or x_admin_key != s.worker_admin_key:
          raise HTTPException(status_code=403, detail="forbidden")
      return db.get_admin_stats()
  ```

  Добавить `from app.config import get_settings` в импорты если не было.

- [ ] **Шаг 6: Проверить mypy**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv run mypy app/main.py --ignore-missing-imports
  ```

  Ожидаем: `Success: no issues found`.

- [ ] **Шаг 7: Коммит**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git add services/worker/app/main.py
  "feat(auth): add JWT auth gates to all /jobs/* endpoints + /admin/stats" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 6: Worker — починить существующие API-тесты (auth override)

**Files:**
- Modify: `services/worker/tests/unit/test_editor_api.py`
- Modify: `services/worker/tests/unit/test_chapters_api.py`

После добавления `Depends(get_current_user)` в main.py, все TestClient-запросы получат 401. Нужно добавить `dependency_overrides` в тестовых хелперах.

- [ ] **Шаг 1: Обновить _client() в test_editor_api.py**

  Найти функцию `_client(monkeypatch, tmp_path)` в `tests/unit/test_editor_api.py`.

  Добавить **после** `from app.main import app`:
  ```python
  from app.auth import get_current_user

  monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: "test-user-id")
  ```

  Итоговый конец функции `_client`:
  ```python
  from app.main import app
  from app.auth import get_current_user

  monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: "test-user-id")
  return TestClient(app), job
  ```

  `monkeypatch.setitem` автоматически восстанавливает словарь после каждого теста.

- [ ] **Шаг 2: Обновить _client() в test_chapters_api.py**

  Та же правка — найти `_client(monkeypatch, tmp_path)` и добавить:
  ```python
  from app.auth import get_current_user

  monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: "test-user-id")
  ```

  Функция возвращает `TestClient(app), job, d` — добавить перед return.

- [ ] **Шаг 3: Запустить все unit-тесты**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv run pytest tests/unit/ -v --tb=short 2>&1 | tail -20
  ```

  Ожидаем: все тесты PASSED (было ~297, теперь +11 новых).

- [ ] **Шаг 4: just check зелёный**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  just check
  ```

- [ ] **Шаг 5: Коммит**

  ```powershell
  git add services/worker/tests/unit/test_editor_api.py services/worker/tests/unit/test_chapters_api.py
  "fix(tests): add auth dependency_override to TestClient helpers" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 7: Frontend — @supabase/ssr + lib/supabase/

**Files:**
- Modify: `apps/web/package.json` (через pnpm)
- Create: `apps/web/lib/supabase/client.ts`
- Create: `apps/web/lib/supabase/server.ts`

- [ ] **Шаг 1: Установить пакеты**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow"
  pnpm --filter web add @supabase/ssr @supabase/supabase-js
  ```

- [ ] **Шаг 2: Создать apps/web/lib/supabase/client.ts**

  ```typescript
  import { createBrowserClient } from "@supabase/ssr";

  export function createClient() {
    return createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    );
  }
  ```

- [ ] **Шаг 3: Создать apps/web/lib/supabase/server.ts**

  ```typescript
  import { createServerClient } from "@supabase/ssr";
  import { cookies } from "next/headers";

  export async function createClient() {
    const cookieStore = await cookies();
    return createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return cookieStore.getAll();
          },
          setAll(cookiesToSet) {
            try {
              cookiesToSet.forEach(({ name, value, options }) =>
                cookieStore.set(name, value, options),
              );
            } catch {
              // Server Component — игнорировать ошибки set (read-only контекст)
            }
          },
        },
      },
    );
  }
  ```

- [ ] **Шаг 4: Проверить tsc**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  pnpm --filter web exec tsc --noEmit
  ```

  Ожидаем: без ошибок.

- [ ] **Шаг 5: Коммит**

  ```powershell
  git add apps/web/package.json apps/web/pnpm-lock.yaml apps/web/lib/supabase/
  "feat(auth): @supabase/ssr install + browser/server clients" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 8: Frontend — app/api/auth/callback/route.ts

**Files:**
- Create: `apps/web/app/api/auth/callback/route.ts`
- Delete: `apps/web/app/api/auth/route.ts` (старый passcode-эндпоинт)

- [ ] **Шаг 1: Создать OAuth callback route**

  Создать `apps/web/app/api/auth/callback/route.ts`:

  ```typescript
  import { createClient } from "@/lib/supabase/server";
  import { NextResponse } from "next/server";

  export async function GET(request: Request) {
    const { searchParams, origin } = new URL(request.url);
    const code = searchParams.get("code");
    const next = searchParams.get("next") ?? "/";

    if (code) {
      const supabase = await createClient();
      const { error } = await supabase.auth.exchangeCodeForSession(code);
      if (!error) {
        return NextResponse.redirect(`${origin}${next}`);
      }
    }

    return NextResponse.redirect(`${origin}/login?error=auth_callback_failed`);
  }
  ```

- [ ] **Шаг 2: Удалить старый passcode-эндпоинт**

  ```powershell
  Remove-Item "C:\Users\user\Desktop\ClipClow\apps\web\app\api\auth\route.ts"
  ```

- [ ] **Шаг 3: tsc check**

  ```powershell
  pnpm --filter web exec tsc --noEmit
  ```

- [ ] **Шаг 4: Коммит**

  ```powershell
  git add apps/web/app/api/auth/
  git rm apps/web/app/api/auth/route.ts
  "feat(auth): OAuth callback route, remove old passcode endpoint" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 9: Frontend — middleware.ts (замена passcode → Supabase)

**Files:**
- Modify: `apps/web/middleware.ts`

- [ ] **Шаг 1: Заменить содержимое middleware.ts**

  Полностью заменить `apps/web/middleware.ts`:

  ```typescript
  import { createServerClient } from "@supabase/ssr";
  import { NextResponse, type NextRequest } from "next/server";

  const PUBLIC_PATHS = ["/login", "/api/auth"];

  export async function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
      return NextResponse.next();
    }

    let supabaseResponse = NextResponse.next({ request });

    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll(cookiesToSet) {
            cookiesToSet.forEach(({ name, value, options }) =>
              request.cookies.set(name, value, options),
            );
            supabaseResponse = NextResponse.next({ request });
            cookiesToSet.forEach(({ name, value, options }) =>
              supabaseResponse.cookies.set(name, value, options),
            );
          },
        },
      },
    );

    // ВАЖНО: вызывать getUser() сразу после createServerClient
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      url.searchParams.set("from", pathname);
      return NextResponse.redirect(url);
    }

    return supabaseResponse;
  }

  export const config = {
    matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
  };
  ```

- [ ] **Шаг 2: Проверить tsc**

  ```powershell
  pnpm --filter web exec tsc --noEmit
  ```

- [ ] **Шаг 3: Коммит**

  ```powershell
  git add apps/web/middleware.ts
  "feat(auth): replace passcode gate with Supabase session middleware" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 10: Frontend — login page (email + Google OAuth)

**Files:**
- Modify: `apps/web/app/login/page.tsx`

- [ ] **Шаг 1: Заменить содержимое login/page.tsx**

  ```typescript
  "use client";

  import { useRouter, useSearchParams } from "next/navigation";
  import { Suspense, useState } from "react";
  import { createClient } from "@/lib/supabase/client";

  function LoginForm() {
    const supabase = createClient();
    const router = useRouter();
    const params = useSearchParams();
    const rawFrom = params.get("from") ?? "/";
    const from =
      rawFrom.startsWith("/") && !rawFrom.startsWith("//") && !rawFrom.startsWith("/\\")
        ? rawFrom
        : "/";

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [isSignUp, setIsSignUp] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [info, setInfo] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
      e.preventDefault();
      setLoading(true);
      setError(null);
      setInfo(null);

      if (isSignUp) {
        const { error: err } = await supabase.auth.signUp({ email, password });
        setLoading(false);
        if (err) { setError(err.message); return; }
        setInfo("Проверь email — отправили ссылку подтверждения");
      } else {
        const { error: err } = await supabase.auth.signInWithPassword({ email, password });
        setLoading(false);
        if (err) { setError(err.message); return; }
        router.replace(from);
      }
    }

    async function handleGoogle() {
      setLoading(true);
      await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/api/auth/callback?next=${encodeURIComponent(from)}`,
        },
      });
    }

    return (
      <form onSubmit={handleSubmit} className="space-y-3">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          autoFocus
          required
          disabled={loading}
          className="w-full rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Пароль"
          required
          disabled={loading}
          className="w-full rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
        />
        {error && <p className="text-xs text-red-400">{error}</p>}
        {info && <p className="text-xs text-green-400">{info}</p>}
        <button
          type="submit"
          disabled={loading || !email || !password}
          className="w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white transition hover:bg-accent-2 disabled:opacity-30"
        >
          {loading ? "Загрузка…" : isSignUp ? "Зарегистрироваться" : "Войти"}
        </button>
        <button
          type="button"
          onClick={handleGoogle}
          disabled={loading}
          className="w-full rounded-xl border border-line py-3 text-sm text-ink transition hover:bg-surface/60 disabled:opacity-30"
        >
          Войти через Google
        </button>
        <p className="text-center text-xs text-muted">
          {isSignUp ? "Уже есть аккаунт? " : "Нет аккаунта? "}
          <button
            type="button"
            onClick={() => { setIsSignUp(!isSignUp); setError(null); setInfo(null); }}
            className="text-accent hover:underline"
          >
            {isSignUp ? "Войти" : "Зарегистрироваться"}
          </button>
        </p>
      </form>
    );
  }

  export default function LoginPage() {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="w-full max-w-sm space-y-6">
          <div className="text-center space-y-1">
            <h1 className="text-2xl font-display font-black text-ink">ClipFlow</h1>
            <p className="text-sm text-muted">Войди чтобы продолжить</p>
          </div>
          <Suspense>
            <LoginForm />
          </Suspense>
        </div>
      </main>
    );
  }
  ```

- [ ] **Шаг 2: tsc check**

  ```powershell
  pnpm --filter web exec tsc --noEmit
  ```

- [ ] **Шаг 3: Коммит**

  ```powershell
  git add apps/web/app/login/page.tsx
  "feat(auth): login page — email/password + Google OAuth button" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 11: Frontend — lib/api.ts: auth headers на все fetch-вызовы к воркеру

**Files:**
- Modify: `apps/web/lib/api.ts`

- [ ] **Шаг 1: Добавить getAuthHeaders() хелпер**

  В начало `apps/web/lib/api.ts` добавить импорт и хелпер (после существующих импортов):

  ```typescript
  import { createClient } from "@/lib/supabase/client";

  async function getAuthHeaders(): Promise<Record<string, string>> {
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) return {};
    return { Authorization: `Bearer ${session.access_token}` };
  }
  ```

- [ ] **Шаг 2: Обновить createJob**

  ```typescript
  export async function createJob(input: CreateJobInput): Promise<{ id: string }> {
    const res = await fetch(`${BASE}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...await getAuthHeaders() },
      body: JSON.stringify(input),
    });
    if (!res.ok) throw new Error(`createJob failed: ${res.status}`);
    return res.json();
  }
  ```

- [ ] **Шаг 3: Обновить createUploadJob**

  ```typescript
  export async function createUploadJob(file: File, maxClips?: number): Promise<{ id: string }> {
    const form = new FormData();
    form.append("file", file);
    if (maxClips != null) form.append("max_clips", String(maxClips));
    const res = await fetch(`${BASE}/jobs/upload`, {
      method: "POST",
      headers: await getAuthHeaders(),  // без Content-Type — браузер ставит boundary сам
      body: form,
    });
    if (!res.ok) throw new Error(`createUploadJob failed: ${res.status}`);
    return res.json();
  }
  ```

- [ ] **Шаг 4: Обновить все остальные функции**

  Для каждой из следующих функций добавить `...await getAuthHeaders()` в headers.
  Функции без headers — добавить `headers: await getAuthHeaders()`.

  **getJob:**
  ```typescript
  const res = await fetch(`${BASE}/jobs/${id}`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  });
  ```

  **getTimeline:**
  ```typescript
  const res = await fetch(`${BASE}/jobs/${jobId}/timeline`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  });
  ```

  **getChapters:**
  ```typescript
  const res = await fetch(`${BASE}/jobs/${jobId}/chapters`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  });
  ```

  **getClipAss:**
  ```typescript
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/ass`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  });
  ```

  **getClipEdit:**
  ```typescript
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/edit`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  });
  ```

  **getClipAnalysis:**
  ```typescript
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/analysis`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  });
  ```

  **getRenderStatus:**
  ```typescript
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/render`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  });
  ```

  **setCropOverride, setClipInterval, trimClip, extendClip, startRenderClip, patchClipEdit, applyPreset** — все имеют `headers: { "Content-Type": "application/json" }`:
  ```typescript
  headers: { "Content-Type": "application/json", ...await getAuthHeaders() },
  ```

  **getPresets** — публичный, НЕ добавлять auth.

- [ ] **Шаг 5: tsc check**

  ```powershell
  pnpm --filter web exec tsc --noEmit
  ```

  Ожидаем: без ошибок.

- [ ] **Шаг 6: next build**

  ```powershell
  pnpm --filter web build
  ```

  Ожидаем: ✓ Compiled successfully.

- [ ] **Шаг 7: Коммит**

  ```powershell
  git add apps/web/lib/api.ts
  "feat(auth): add Supabase Bearer token to all worker API calls" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 12: Frontend — /admin страница аналитики

**Files:**
- Create: `apps/web/app/admin/page.tsx`

- [ ] **Шаг 1: Создать apps/web/app/admin/page.tsx**

  ```typescript
  import { createClient } from "@/lib/supabase/server";
  import { createClient as createAdminClient } from "@supabase/supabase-js";
  import { notFound } from "next/navigation";

  export default async function AdminPage() {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user || user.email !== process.env.ADMIN_EMAIL) {
      notFound();
    }

    // Список пользователей (требует service role key)
    const admin = createAdminClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.SUPABASE_SERVICE_ROLE_KEY!,
    );
    const {
      data: { users },
    } = await admin.auth.admin.listUsers();

    // Статистика джобов от воркера
    type UserStat = { user_id: string; job_count: number; total_cost_usd: number };
    type Stats = { users: UserStat[]; totals: { jobs: number; cost_usd: number } };
    let stats: Stats = { users: [], totals: { jobs: 0, cost_usd: 0 } };

    const workerUrl = process.env.NEXT_PUBLIC_WORKER_URL ?? "";
    if (workerUrl) {
      try {
        const r = await fetch(`${workerUrl}/admin/stats`, {
          headers: { "X-Admin-Key": process.env.WORKER_ADMIN_KEY ?? "" },
          cache: "no-store",
        });
        if (r.ok) stats = await r.json();
      } catch {
        // воркер недоступен — показываем только юзеров
      }
    }

    const statsMap = Object.fromEntries(stats.users.map((u) => [u.user_id, u]));
    const rows = users.map((u) => ({
      id: u.id,
      email: u.email ?? "—",
      created_at: u.created_at,
      job_count: statsMap[u.id]?.job_count ?? 0,
      cost_usd: statsMap[u.id]?.total_cost_usd ?? 0,
    }));

    return (
      <main className="mx-auto max-w-4xl px-5 py-8">
        <h1 className="font-display text-2xl font-black text-ink mb-6">Admin</h1>

        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="rounded-xl border border-line bg-surface p-4">
            <p className="text-xs text-muted mb-1">Пользователей</p>
            <p className="text-3xl font-bold text-ink">{users.length}</p>
          </div>
          <div className="rounded-xl border border-line bg-surface p-4">
            <p className="text-xs text-muted mb-1">Всего джобов</p>
            <p className="text-3xl font-bold text-ink">{stats.totals.jobs}</p>
          </div>
          <div className="rounded-xl border border-line bg-surface p-4">
            <p className="text-xs text-muted mb-1">Потрачено</p>
            <p className="text-3xl font-bold text-ink">${stats.totals.cost_usd.toFixed(2)}</p>
          </div>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted border-b border-line">
              <th className="pb-2 font-medium">Email</th>
              <th className="pb-2 font-medium">Зарегистрирован</th>
              <th className="pb-2 font-medium text-right">Джобов</th>
              <th className="pb-2 font-medium text-right">Потрачено</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-line/40 hover:bg-surface/60 transition">
                <td className="py-2.5 text-ink">{r.email}</td>
                <td className="py-2.5 text-muted">
                  {new Date(r.created_at).toLocaleDateString("ru-RU")}
                </td>
                <td className="py-2.5 text-right text-ink">{r.job_count}</td>
                <td className="py-2.5 text-right text-muted">${r.cost_usd.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </main>
    );
  }
  ```

- [ ] **Шаг 2: tsc + build**

  ```powershell
  pnpm --filter web exec tsc --noEmit
  pnpm --filter web build
  ```

- [ ] **Шаг 3: Коммит**

  ```powershell
  git add apps/web/app/admin/
  "feat(auth): /admin analytics page — users + job stats" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 13: Env vars + Vercel deploy

**Files:** нет кода — настройка

- [ ] **Шаг 1: Создать/обновить .env в корне репо**

  Добавить в `.env` (корень ClipClow, gitignored):
  ```bash
  # Auth
  SUPABASE_JWT_SECRET=xxx   # из Supabase → Settings → API → JWT Secret
  WORKER_ADMIN_KEY=сгенерировать-случайную-строку-32-символа
  ```

  Сгенерировать WORKER_ADMIN_KEY:
  ```powershell
  -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 32 | % {[char]$_})
  ```

- [ ] **Шаг 2: Создать apps/web/.env.local**

  ```bash
  NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
  NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
  SUPABASE_SERVICE_ROLE_KEY=eyJ...
  NEXT_PUBLIC_WORKER_URL=https://xxx.ngrok.io   # обновлять при каждом запуске ngrok
  WORKER_ADMIN_KEY=та-же-строка-что-в-.env
  ADMIN_EMAIL=akybaevtimur7@gmail.com
  ```

- [ ] **Шаг 3: Проверить локально**

  ```powershell
  # Терминал 1: воркер
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

  # Терминал 2: туннель
  ngrok http 8000
  # скопировать https://xxx.ngrok.io → вставить в NEXT_PUBLIC_WORKER_URL

  # Терминал 3: фронт
  Set-Location "C:\Users\user\Desktop\ClipClow"
  pnpm --filter web dev
  ```

  Проверить:
  - http://localhost:3000 → редиректит на /login (не прошёл auth)
  - /login → форма email + Google
  - Регистрация email → попадаешь на главную
  - Создать джоб → джоб появляется
  - Войти другим аккаунтом → чужие джобы не видны (404)
  - http://localhost:3000/admin → таблица юзеров

- [ ] **Шаг 4: Деплой на Vercel**

  ```powershell
  # Установить Vercel CLI если нет
  pnpm add -g vercel

  # Деплой
  Set-Location "C:\Users\user\Desktop\ClipClow\apps\web"
  vercel
  ```

  При первом запуске Vercel спросит:
  - Project name: `clipflow`
  - Framework: Next.js (автодетект)
  - Root directory: `.` (мы уже в apps/web)

  Добавить env vars через Vercel UI или CLI:
  ```powershell
  vercel env add NEXT_PUBLIC_SUPABASE_URL
  vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY
  vercel env add SUPABASE_SERVICE_ROLE_KEY
  vercel env add NEXT_PUBLIC_WORKER_URL
  vercel env add WORKER_ADMIN_KEY
  vercel env add ADMIN_EMAIL
  ```

  Продакшн деплой:
  ```powershell
  vercel --prod
  ```

- [ ] **Шаг 5: just check зелёный финальный**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  just check
  ```

  Ожидаем: все тесты (308+ с новыми) PASSED, mypy OK, tsc OK, anti-drift OK.

- [ ] **Шаг 6: Финальный коммит**

  ```powershell
  "docs: auth layer complete — Supabase + Vercel deploy" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Быстрая проверка после деплоя

```
curl https://ваш-vocker-url.ngrok.io/healthz
→ {"ok": true, "version": "..."}

curl -X POST https://ваш-vocker-url.ngrok.io/jobs \
  -H "Content-Type: application/json" \
  -d '{"source_type":"youtube","source_ref":"test"}'
→ 401 (нет токена — работает!)

curl https://ваш-vercel.vercel.app/admin
→ 404 (не тот email — работает!)
```
