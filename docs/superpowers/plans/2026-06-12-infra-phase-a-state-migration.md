# Phase A — State Migration to Supabase (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенести стейт воркера (джобы, правки, артефакты пайплайна, клипы) с локального SQLite+диска в Supabase Postgres+Storage, ОСТАВИВ воркер локальным — чтобы миграцию данных проверить в изоляции до смены платформы (Modal — отдельная Фаза B).

**Architecture:** Воркер крутится локально (`uv run`), но `db.py` пишет в Supabase Postgres (через psycopg к транзакционному пулеру), артефакты пайплайна (meta/segments/transcript) — в таблицу `job_artifacts` (jsonb), content-addressed transcript-кэш — в таблицу `transcript_cache`, готовые клипы — в Supabase Storage (бакет `clips`) с публичным CDN-URL. Pure-пайплайн (`stage0-5`, editor, reframe) НЕ трогаем. Auth остаётся в dev-bypass (user_id = NULL) — реальный JWKS-auth и фронт — следующий план.

**Tech Stack:** Supabase (Postgres + Storage + RLS), `psycopg[binary]` 3.x (pooler, `prepare_threshold=None`), `httpx` (Storage REST upload), pydantic-settings, pytest (TDD на pure-логике).

**Spec:** `docs/superpowers/specs/2026-06-12-infra-modal-deploy-design.md` (§4 миграция, §5 схема БД).

---

## Что НЕ входит в этот план (отдельные планы)
- **Auth (JWKS) + фронт читает из Supabase + Bearer-токены** — обновление `2026-06-13-auth-analytics-plan.md` (HS256→JWKS). После этой Фазы A.
- **Modal-деплой** (Dockerfile, split API/worker, spawn-очередь) — Фаза B.
- **Realtime вместо поллинга + квоты + queue-position UI** — Фаза C.

## File Map

### Создать
```
services/worker/app/storage.py                       ← Storage upload + pure URL-билдеры
services/worker/tests/unit/test_storage.py           ← TDD pure URL-билдеров
services/worker/sql/001_schema.sql                   ← таблицы + RLS (применяется в Supabase SQL editor)
services/worker/tests/unit/test_db_mapping.py        ← TDD нового row_to_wire (Storage URL)
```

### Изменить
```
services/worker/pyproject.toml          ← + psycopg[binary]
services/worker/app/config.py           ← supabase_url / service_role / db_url / storage_bucket
services/worker/app/db.py               ← SQLite → psycopg (Postgres); row_to_wire → Storage URL; артефакты; transcript_cache; атомарный optimistic-lock
services/worker/app/editor/store.py     ← читать artifacts из Postgres; убрать disk-mirror edit.json
services/worker/app/run.py              ← persist: артефакты+клипы в облако; transcript_cache в Postgres
services/worker/app/tasks.py            ← render persist: клип в Storage, render_url = публичный URL
services/worker/app/main.py             ← lifespan: db.init_db() → ping (схема не создаётся приложением)
services/worker/tests/unit/test_db.py   ← обновить под новый row_to_wire (или заменить на test_db_mapping)
```

---

## Task 0: Supabase проект (Pro) + Storage-бакет — ручная настройка

**Files:** нет кода.

- [ ] **Шаг 1: Создать проект + Pro**

  https://supabase.com → New project (`clipflow`), регион ближайший. Затем Settings → Billing →
  **Upgrade to Pro** ($25/мес) — снимает 7-дневную паузу + бэкапы + 500 realtime-конн.

- [ ] **Шаг 2: Включить асимметричные JWT-ключи** (для будущего auth-плана; включаем сейчас)

  Dashboard → Authentication → Signing Keys → **Migrate to asymmetric keys** (RS256/ES256).
  Запиши JWKS-URL: `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json`.

- [ ] **Шаг 3: Создать Storage-бакет `clips`**

  Dashboard → Storage → New bucket → name `clips`, **Public bucket: ON** (клипы отдаются CDN по
  публичному URL; пути неугадываемые `job_<uuid>/clip_XX.mp4`). Save.

- [ ] **Шаг 4: Записать ключи** (в `.env` корня, gitignored)

  Settings → API:
  ```
  SUPABASE_URL=https://<ref>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=eyJ...        # секрет, НЕ коммитить
  ```
  Settings → Database → Connection string → **Transaction pooler** (порт 6543), Python/psycopg:
  ```
  SUPABASE_DB_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
  ```

- [ ] **Шаг 5: DoD** — проект Pro активен, бакет `clips` (public) существует, 3 значения в `.env`.

---

## Task 1: SQL-схема + RLS

**Files:** Create `services/worker/sql/001_schema.sql`

- [ ] **Шаг 1: Создать `services/worker/sql/001_schema.sql`**

  ```sql
  -- ClipFlow Phase A schema. Применять в Supabase SQL Editor.

  create table if not exists jobs (
    id text primary key,
    user_id uuid references auth.users,           -- NULL в dev-bypass (Phase A); NOT NULL после auth-плана
    status text, stage text, progress int,
    source_type text, source_ref text, error text,
    clips jsonb, cost_usd numeric, duration_sec numeric, elapsed_sec numeric,
    created_at timestamptz default now(), updated_at timestamptz default now()
  );

  create table if not exists clip_edits (
    job_id text references jobs(id), clip_id text,
    version int, edit jsonb,
    render_status text, render_url text, render_error text,
    updated_at timestamptz default now(),
    primary key (job_id, clip_id)
  );

  create table if not exists job_artifacts (
    job_id text primary key references jobs(id),
    meta jsonb, segments jsonb, transcript jsonb
  );

  create table if not exists transcript_cache (
    audio_sha text, provider text, model text,
    transcript jsonb, created_at timestamptz default now(),
    primary key (audio_sha, provider, model)
  );

  create table if not exists runs (
    run_id text, source_minutes numeric, stages jsonb,
    total_sec numeric, total_usd numeric, n_clips int,
    time_to_first_clip_sec numeric, created_at timestamptz default now()
  );

  -- RLS: фронт читает СВОИ джобы; воркер пишет через service_role (минует RLS).
  alter table jobs enable row level security;
  alter table clip_edits enable row level security;
  alter table job_artifacts enable row level security;

  drop policy if exists "own jobs" on jobs;
  create policy "own jobs" on jobs for select using (user_id = auth.uid());

  drop policy if exists "own edits" on clip_edits;
  create policy "own edits" on clip_edits for select
    using (exists (select 1 from jobs j where j.id = job_id and j.user_id = auth.uid()));

  drop policy if exists "own artifacts" on job_artifacts;
  create policy "own artifacts" on job_artifacts for select
    using (exists (select 1 from jobs j where j.id = job_id and j.user_id = auth.uid()));
  -- transcript_cache / runs — без RLS (служебные, только service_role).
  ```

- [ ] **Шаг 2: Применить**

  Supabase Dashboard → SQL Editor → вставить содержимое `001_schema.sql` → Run.

- [ ] **Шаг 3: DoD**

  Dashboard → Table Editor: видны `jobs`, `clip_edits`, `job_artifacts`, `transcript_cache`, `runs`.
  Database → Roles/Policies: на `jobs`/`clip_edits`/`job_artifacts` включён RLS.

- [ ] **Шаг 4: Коммит**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git add services/worker/sql/001_schema.sql
  "feat(infra): Supabase schema + RLS (jobs/clip_edits/job_artifacts/transcript_cache/runs)" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 2: Зависимости + config.py

**Files:** Modify `services/worker/pyproject.toml`, `services/worker/app/config.py`

- [ ] **Шаг 1: Добавить psycopg в pyproject.toml**

  В `[project].dependencies` добавить:
  ```toml
  "psycopg[binary]>=3.2",
  ```
  Затем:
  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv sync --extra asd   # держим ASD-extra, иначе torch выпиливается (CLAUDE.md грабля)
  ```

- [ ] **Шаг 2: Добавить поля в Settings (`app/config.py`)**

  Найти класс `Settings` и добавить поля (после существующих reframe-полей):
  ```python
  # cloud state (Phase A)
  supabase_url: str = ""                 # https://<ref>.supabase.co
  supabase_service_role_key: str = ""    # секрет; bypass RLS из воркера
  supabase_db_url: str = ""              # postgresql://...pooler...:6543/postgres
  storage_bucket: str = "clips"
  ```

  > Примечание: `.env` уже читается по абсолютному пути (`parents[3]/.env`, см. CLAUDE.md C-грабли).
  > Новые значения из Task 0 подхватятся автоматически.

- [ ] **Шаг 3: Проверить mypy**

  ```powershell
  uv run mypy app/config.py
  ```
  Ожидаем: `Success: no issues found`.

- [ ] **Шаг 4: Коммит**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git add services/worker/pyproject.toml services/worker/uv.lock services/worker/app/config.py
  "feat(infra): add psycopg dep + Supabase config fields" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 3: app/storage.py — Storage upload + pure URL-билдеры (TDD)

**Files:**
- Create: `services/worker/app/storage.py`
- Create: `services/worker/tests/unit/test_storage.py`

- [ ] **Шаг 1: Написать падающий тест pure-билдеров**

  Создать `services/worker/tests/unit/test_storage.py`:
  ```python
  """Тесты pure URL-билдеров Storage (app.storage)."""

  from app.storage import public_url, storage_object_path


  def test_storage_object_path():
      assert storage_object_path("job_abc", "clip_01") == "job_abc/clip_01.mp4"


  def test_public_url_builds_cdn_path():
      url = public_url("clips", "job_abc/clip_01.mp4", "https://ref.supabase.co")
      assert url == "https://ref.supabase.co/storage/v1/object/public/clips/job_abc/clip_01.mp4"


  def test_public_url_strips_trailing_slash_on_base():
      url = public_url("clips", "p.mp4", "https://ref.supabase.co/")
      assert url == "https://ref.supabase.co/storage/v1/object/public/clips/p.mp4"
  ```

- [ ] **Шаг 2: Запустить — убедиться, что падает**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv run pytest tests/unit/test_storage.py -v
  ```
  Ожидаем: `ModuleNotFoundError: No module named 'app.storage'`.

- [ ] **Шаг 3: Создать `app/storage.py`**

  ```python
  """Supabase Storage: upload готового клипа + pure URL-билдеры (Phase A).

  Воркер грузит mp4 в бакет `clips` через Storage REST (service_role bypass RLS),
  возвращает публичный CDN-URL, который пишется в строку джоба/клипа.
  """

  from __future__ import annotations

  from pathlib import Path

  import httpx

  from app.config import get_settings
  from app.errors import JobError


  def storage_object_path(job_id: str, clip_id: str) -> str:
      """Путь объекта внутри бакета clips для клипа. PURE."""
      return f"{job_id}/{clip_id}.mp4"


  def public_url(bucket: str, path: str, base_url: str) -> str:
      """Публичный CDN-URL объекта public-бакета. PURE."""
      return f"{base_url.rstrip('/')}/storage/v1/object/public/{bucket}/{path}"


  def upload_clip(local_path: Path, job_id: str, clip_id: str) -> str:
      """Залить mp4 в Storage (upsert) → вернуть публичный CDN-URL. JobError при сбое."""
      s = get_settings()
      path = storage_object_path(job_id, clip_id)
      endpoint = f"{s.supabase_url.rstrip('/')}/storage/v1/object/{s.storage_bucket}/{path}"
      resp = httpx.post(
          endpoint,
          content=local_path.read_bytes(),
          headers={
              "Authorization": f"Bearer {s.supabase_service_role_key}",
              "apikey": s.supabase_service_role_key,
              "Content-Type": "video/mp4",
              "x-upsert": "true",
          },
          timeout=httpx.Timeout(connect=10, write=None, read=60, pool=10),
      )
      if resp.status_code not in (200, 201):
          raise JobError("storage", f"upload {clip_id} failed {resp.status_code}: {resp.text}")
      return public_url(s.storage_bucket, path, s.supabase_url)
  ```

- [ ] **Шаг 4: Запустить — убедиться, что зелёные**

  ```powershell
  uv run pytest tests/unit/test_storage.py -v
  ```
  Ожидаем: 3 PASSED.

- [ ] **Шаг 5: Коммит**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git add services/worker/app/storage.py services/worker/tests/unit/test_storage.py
  "feat(infra): app/storage.py — Supabase Storage upload + pure URL builders, 3 tests" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 4: app/db.py → Postgres (psycopg) + новый row_to_wire (TDD на pure-маппинге)

**Files:**
- Modify: `services/worker/app/db.py`
- Create: `services/worker/tests/unit/test_db_mapping.py`
- Modify/replace: `services/worker/tests/unit/test_db.py`

> Ключевое решение: клипы в `clips` (jsonb) хранят **полный публичный URL** (его проставляет
> persist-шаг, Task 6). Поэтому `row_to_wire` БОЛЬШЕ НЕ префиксит `media/...` — отдаёт URL как есть.

- [ ] **Шаг 1: Написать падающий тест нового row_to_wire**

  Создать `services/worker/tests/unit/test_db_mapping.py`:
  ```python
  """Тесты pure-маппинга row_to_wire (Postgres-эра: video_url = полный Storage URL)."""

  from app.db import row_to_wire


  def _row(**over):
      base = {
          "id": "job_x", "status": "done", "stage": "done", "progress": 100,
          "error": None,
          "clips": [{"id": "clip_01",
                     "video_url": "https://ref.supabase.co/storage/v1/object/public/clips/job_x/clip_01.mp4"}],
          "cost_usd": 0.16, "duration_sec": 120.0, "elapsed_sec": 30.0,
      }
      base.update(over)
      return base


  def test_clip_video_url_passes_through_unchanged():
      wire = row_to_wire(_row())
      assert wire["clips"][0]["video_url"] == (
          "https://ref.supabase.co/storage/v1/object/public/clips/job_x/clip_01.mp4"
      )


  def test_metrics_present_only_when_done():
      assert row_to_wire(_row(status="processing"))["metrics"] is None
      m = row_to_wire(_row(status="done"))["metrics"]
      assert m == {"cost_usd": 0.16, "duration_sec": 120.0, "elapsed_sec": 30.0}


  def test_empty_clips_when_none():
      wire = row_to_wire(_row(clips=None, status="queued"))
      assert wire["clips"] == []
  ```

- [ ] **Шаг 2: Запустить — убедиться, что падает**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv run pytest tests/unit/test_db_mapping.py -v
  ```
  Ожидаем: FAIL (старый row_to_wire префиксит `media/...` и читает `clips_json`, а не `clips`).

- [ ] **Шаг 3: Переписать `app/db.py` на psycopg**

  Полностью заменить содержимое `services/worker/app/db.py`:
  ```python
  """Postgres-хранилище задач (Phase A — Supabase). Воркер пишет через service_role.

  Подключение — через транзакционный пулер Supabase (порт 6543), поэтому
  prepare_threshold=None (иначе prepared-statement ошибки на пулере). Pure-маппинг
  row_to_wire изолирован и покрыт unit-тестами. Схема создаётся SQL-миграцией
  (sql/001_schema.sql), НЕ приложением.
  """

  from __future__ import annotations

  import json
  import time
  from typing import Any

  import psycopg
  from psycopg.rows import dict_row
  from psycopg.types.json import Jsonb

  from app.config import get_settings
  from app.models import Job


  def _conn() -> psycopg.Connection[dict[str, Any]]:
      s = get_settings()
      return psycopg.connect(
          s.supabase_db_url,
          row_factory=dict_row,
          prepare_threshold=None,  # обязательно для транзакционного пулера (6543)
          autocommit=True,
      )


  def init_db() -> None:
      """Ping соединения (схема — в sql/001_schema.sql, не создаём из кода)."""
      with _conn() as c:
          c.execute("select 1")


  def insert_job(
      job_id: str, source_type: str, source_ref: str, *, user_id: str | None = None
  ) -> None:
      now = time.time()
      with _conn() as c:
          c.execute(
              "insert into jobs"
              " (id,status,stage,progress,source_type,source_ref,user_id,created_at,updated_at)"
              " values (%s,%s,%s,%s,%s,%s,%s,to_timestamp(%s),to_timestamp(%s))",
              (job_id, "queued", "queued", 0, source_type, source_ref, user_id, now, now),
          )


  def update_status(job_id: str, status: str, progress: int) -> None:
      with _conn() as c:
          c.execute(
              "update jobs set status=%s, stage=%s, progress=%s, updated_at=now() where id=%s",
              (status, status, progress, job_id),
          )


  def set_done(job_id: str, job: Job) -> None:
      clips = [c.model_dump() for c in job.clips]
      m = job.metrics
      with _conn() as c:
          c.execute(
              "update jobs set status='done', stage='done', progress=100, clips=%s,"
              " cost_usd=%s, duration_sec=%s, elapsed_sec=%s, updated_at=now() where id=%s",
              (
                  Jsonb(clips),
                  m.cost_usd if m else 0.0,
                  m.duration_sec if m else 0.0,
                  m.elapsed_sec if m else 0.0,
                  job_id,
              ),
          )


  def set_failed(job_id: str, error: str) -> None:
      with _conn() as c:
          c.execute(
              "update jobs set status='failed', stage='failed', error=%s, updated_at=now()"
              " where id=%s",
              (error, job_id),
          )


  def row_to_wire(row: dict[str, Any]) -> dict[str, Any]:
      """Строка БД → wire-Job (dict). clips[].video_url уже полный Storage URL (без префикса)."""
      clips: list[dict[str, Any]] = row.get("clips") or []
      metrics = None
      if row.get("status") == "done":
          metrics = {
              "cost_usd": float(row.get("cost_usd") or 0.0),
              "duration_sec": float(row.get("duration_sec") or 0.0),
              "elapsed_sec": float(row.get("elapsed_sec") or 0.0),
          }
      return {
          "id": row["id"],
          "status": row["status"],
          "stage": row["stage"],
          "progress": row["progress"] or 0,
          "source_kind": "youtube",
          "error": row.get("error"),
          "clips": clips,
          "metrics": metrics,
      }


  def get_job(job_id: str) -> dict[str, Any] | None:
      with _conn() as c:
          row = c.execute("select * from jobs where id=%s", (job_id,)).fetchone()
      return row_to_wire(row) if row is not None else None


  # ── артефакты пайплайна (читает лёгкий API; пишет воркер) ──


  def put_job_artifacts(
      job_id: str, meta: dict[str, Any], segments: list[Any], transcript: dict[str, Any]
  ) -> None:
      with _conn() as c:
          c.execute(
              "insert into job_artifacts (job_id, meta, segments, transcript)"
              " values (%s,%s,%s,%s)"
              " on conflict (job_id) do update set meta=excluded.meta,"
              " segments=excluded.segments, transcript=excluded.transcript",
              (job_id, Jsonb(meta), Jsonb(segments), Jsonb(transcript)),
          )


  def get_job_artifacts(job_id: str) -> dict[str, Any] | None:
      with _conn() as c:
          row = c.execute(
              "select meta, segments, transcript from job_artifacts where job_id=%s", (job_id,)
          ).fetchone()
      return row


  # ── content-addressed transcript-кэш (общий, бережёт Deepgram) ──


  def get_cached_transcript(audio_sha: str, provider: str, model: str) -> dict[str, Any] | None:
      with _conn() as c:
          row = c.execute(
              "select transcript from transcript_cache"
              " where audio_sha=%s and provider=%s and model=%s",
              (audio_sha, provider, model),
          ).fetchone()
      return row["transcript"] if row else None


  def put_cached_transcript(
      audio_sha: str, provider: str, model: str, transcript: dict[str, Any]
  ) -> None:
      with _conn() as c:
          c.execute(
              "insert into transcript_cache (audio_sha, provider, model, transcript)"
              " values (%s,%s,%s,%s) on conflict (audio_sha, provider, model) do nothing",
              (audio_sha, provider, model, Jsonb(transcript)),
          )


  # ── clip_edits (атомарный optimistic-lock) ──


  def get_clip_edit_row(job_id: str, clip_id: str) -> dict[str, Any] | None:
      with _conn() as c:
          row = c.execute(
              "select * from clip_edits where job_id=%s and clip_id=%s", (job_id, clip_id)
          ).fetchone()
      return row


  def insert_clip_edit(job_id: str, clip_id: str, edit: dict[str, Any], version: int) -> None:
      """Первичная вставка edit-state (version=1 при создании дефолта)."""
      with _conn() as c:
          c.execute(
              "insert into clip_edits (job_id, clip_id, version, edit, updated_at)"
              " values (%s,%s,%s,%s,now()) on conflict (job_id, clip_id) do nothing",
              (job_id, clip_id, version, Jsonb(edit)),
          )


  def update_clip_edit_if_version(
      job_id: str, clip_id: str, edit: dict[str, Any], *, expected_version: int, new_version: int
  ) -> bool:
      """Атомарный optimistic-lock: UPDATE ... WHERE version=expected. True если применилось."""
      with _conn() as c:
          cur = c.execute(
              "update clip_edits set edit=%s, version=%s, updated_at=now()"
              " where job_id=%s and clip_id=%s and version=%s",
              (Jsonb(edit), new_version, job_id, clip_id, expected_version),
          )
          return cur.rowcount == 1


  def set_render_status(
      job_id: str, clip_id: str, status: str, url: str | None, error: str | None
  ) -> None:
      with _conn() as c:
          c.execute(
              "update clip_edits set render_status=%s, render_url=%s, render_error=%s,"
              " updated_at=now() where job_id=%s and clip_id=%s",
              (status, url, error, job_id, clip_id),
          )
  ```

- [ ] **Шаг 4: Удалить старый sqlite-тест, оставить pure-маппинг**

  Старый `tests/unit/test_db.py` тестировал sqlite tmp-файлы (insert/get через sqlite) — больше
  не применимо (нужен живой Postgres). Pure-маппинг покрыт новым `test_db_mapping.py`.
  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git rm services/worker/tests/unit/test_db.py
  ```
  > I/O-функции db.py (insert/update/get с реальным Postgres) проверяются ИНТЕГРАЦИОННО в Task 7
  > (живой прогон), не unit-тестом — как принято в репо для I/O.

- [ ] **Шаг 5: Запустить pure-тест — зелёный**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv run pytest tests/unit/test_db_mapping.py -v
  ```
  Ожидаем: 3 PASSED.

- [ ] **Шаг 6: mypy db.py**

  ```powershell
  uv run mypy app/db.py
  ```
  Ожидаем: Success.

- [ ] **Шаг 7: Коммит**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git add services/worker/app/db.py services/worker/tests/unit/test_db_mapping.py
  git rm --cached services/worker/tests/unit/test_db.py 2>$null
  "feat(infra): db.py SQLite to Postgres (psycopg pooler) + artifacts + transcript_cache + atomic lock" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 5: app/editor/store.py — артефакты из Postgres, убрать disk-mirror

**Files:** Modify `services/worker/app/editor/store.py`

> Неочевидное место **A**: store читал transcript/segments С ДИСКА + писал disk-mirror `edit.json`.
> На Modal лёгкий API и тяжёлый воркер — разные контейнеры без общего диска → читаем из Postgres.

- [ ] **Шаг 1: Переписать `store.py`**

  Полностью заменить `services/worker/app/editor/store.py`:
  ```python
  """Персистентность ClipEdit (Phase A): Postgres (источник правды).

  ensure_edit лениво создаёт дефолт из job_artifacts (segments+transcript из Postgres).
  save_edit — атомарный optimistic-lock через db.update_clip_edit_if_version.
  """

  from __future__ import annotations

  from app import db
  from app.editor.defaults import default_clip_edit
  from app.models import ClipEdit, Segment, Transcript, Word


  class EditConflict(Exception):
      """Версия edit-state в запросе устарела (optimistic-lock)."""


  def _artifacts_or_raise(job_id: str) -> dict:
      arts = db.get_job_artifacts(job_id)
      if arts is None:
          raise FileNotFoundError(f"no artifacts for {job_id}")
      return arts


  def load_transcript_words(job_id: str) -> list[Word]:
      tr = Transcript.model_validate(_artifacts_or_raise(job_id)["transcript"])
      return tr.words


  def load_edit(job_id: str, clip_id: str) -> ClipEdit | None:
      row = db.get_clip_edit_row(job_id, clip_id)
      if row is None or not row.get("edit"):
          return None
      return ClipEdit.model_validate(row["edit"])


  def save_edit(
      job_id: str, clip_id: str, edit: ClipEdit, *, expected_version: int | None
  ) -> ClipEdit:
      """Сохранить edit (инкремент version). EditConflict при несовпадении версии."""
      row = db.get_clip_edit_row(job_id, clip_id)
      current = row["version"] if row else None
      if current is None:
          saved = edit.model_copy(update={"version": 1})
          db.insert_clip_edit(job_id, clip_id, saved.model_dump(), saved.version)
          return saved
      if expected_version is not None and current != expected_version:
          raise EditConflict(f"version {expected_version} != current {current}")
      saved = edit.model_copy(update={"version": current + 1})
      ok = db.update_clip_edit_if_version(
          job_id, clip_id, saved.model_dump(),
          expected_version=current, new_version=saved.version,
      )
      if not ok:
          raise EditConflict(f"concurrent update on {job_id}/{clip_id}")
      return saved


  def ensure_edit(job_id: str, clip_id: str) -> ClipEdit:
      """Загрузить edit, либо создать дефолт из сегмента (job_artifacts)."""
      existing = load_edit(job_id, clip_id)
      if existing is not None:
          return existing
      arts = _artifacts_or_raise(job_id)
      segs = arts["segments"]
      idx = int(clip_id.split("_")[1]) - 1  # clip_01 → 0
      if idx < 0 or idx >= len(segs):
          raise KeyError(clip_id)
      seg = Segment.model_validate(segs[idx])
      edit = default_clip_edit(clip_id, seg, load_transcript_words(job_id))
      return save_edit(job_id, clip_id, edit, expected_version=None)
  ```

  > Удалены: `data_root()`, `_mirror_path()`, disk-чтение/запись. Если `data_root()` импортируется
  > где-то ещё — найти и заменить (см. Шаг 2).

- [ ] **Шаг 2: Найти оставшиеся ссылки на store.data_root / диск-артефакты**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  Select-String -Path app\*.py,app\**\*.py -Pattern "store\.data_root|DATA_ROOT / job_id" -ErrorAction SilentlyContinue
  ```
  В `app/main.py` эндпоинты `get_timeline`/`get_chapters` используют `store.data_root()/job_id` для
  чтения meta/segments/transcript с диска → заменить на `db.get_job_artifacts(job_id)`
  (meta/segments/transcript из jsonb). chapters.json-кэш → пока оставить как есть (Phase C) или
  перенести в Postgres-колонку (вне скоупа Phase A; отметить TODO в коде).

- [ ] **Шаг 3: mypy + затронутые тесты**

  ```powershell
  uv run mypy app/editor/store.py
  uv run pytest tests/unit/ -k "editor or store or chapters" -v --tb=short
  ```
  Тесты редактора (`test_editor_api.py`, `test_chapters_api.py`) используют диск-фикстуры —
  обновить их хелперы под Postgres-артефакты (вставлять `job_artifacts` вместо записи файлов),
  ИЛИ замокать `db.get_job_artifacts`. Конкретно: в `_client()`-хелпере заменить запись
  `segments.json`/`transcript.json` на `monkeypatch`-подстановку `db.get_job_artifacts`/
  `db.get_clip_edit_row` in-memory.

- [ ] **Шаг 4: Коммит**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git add services/worker/app/editor/store.py services/worker/app/main.py services/worker/tests/unit/
  "refactor(infra): store.py reads artifacts from Postgres, drop disk mirror" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 6: run.py / tasks.py — persist в облако (артефакты + клипы + transcript_cache)

**Files:** Modify `services/worker/app/run.py`, `services/worker/app/tasks.py`

> Неочевидные места **B/D**: эфемерный FS → durable-выход надо явно затолкать. Within-job стадии
> по-прежнему пишут в `DATA_ROOT` (scratch, ок локально и на Modal-ephemeral). В КОНЦЕ — persist.

- [ ] **Шаг 1: transcript_cache: файл → Postgres (Неочевидное B)**

  В `app/run.py`, Stage 1, заменить чтение/запись content-addressed кэша с диска
  (`get_cached`/`put_cached` из `app.transcript_cache`) на Postgres:
  ```python
  # было: from app.transcript_cache import audio_sha, cache_key, evict, get_cached, put_cached
  from app.transcript_cache import audio_sha  # оставляем только хэш-функцию
  ```
  В блоке Level-2 кэша (строки ~104-126 текущего run.py) заменить:
  ```python
          cached_tr_dict: dict | None = None
          sha: str | None = None
          if s.transcript_cache_enabled:
              sha = audio_sha(wav_path)
              cached_tr_dict = db.get_cached_transcript(
                  sha, s.transcription_provider, s.deepgram_model
              )

          if cached_tr_dict is not None:
              transcript = Transcript.model_validate(cached_tr_dict)
              tr_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
              print(f"[1] transcribe: cached/hash ({len(transcript.words)} words, $0)")
          else:
              transcript = transcribe_to_file(wav_path, tr_path)
              transcribe_cost = round(transcript.duration / 60 * DEEPGRAM_NOVA_USD_PER_MIN, 4)
              print(f"[1] transcribe: {len(transcript.words)} words (${transcribe_cost})")
              if s.transcript_cache_enabled and sha is not None:
                  db.put_cached_transcript(
                      sha, s.transcription_provider, s.deepgram_model, transcript.model_dump()
                  )
  ```
  Добавить `from app import db` в импорты run.py. (Старый `app/transcript_cache.py` модуль
  оставляем — `audio_sha` ещё используется; disk-evict больше не нужен.)

- [ ] **Шаг 2: persist артефактов + клипов в конце run_pipeline**

  В `app/run.py`, ПЕРЕД формированием `job` (после цикла per-clip, ~строка 200), добавить:
  ```python
      # ── persist артефактов в Postgres (для лёгкого API: редактор/таймлайн) ──
      db.put_job_artifacts(
          job_id,
          meta=meta.model_dump(),
          segments=[s.model_dump() for s in segments],
          transcript=transcript.model_dump(),
      )
  ```
  И в цикле per-clip, СРАЗУ после `render_clip(...)`, заменить локальный `video_url` на upload:
  ```python
          from app.storage import upload_clip
          clip_url = upload_clip(out / "clips" / f"{clip_id}.mp4", job_id, clip_id)
  ```
  и в `ClipOut(...)` использовать `video_url=clip_url` (полный CDN-URL) вместо `f"clips/{clip_id}.mp4"`.

- [ ] **Шаг 3: render-таск → Storage (tasks.py, Неочевидное C)**

  В `app/tasks.py` `render_clip_edit_job`, после `render_timeline(...)` заменить:
  ```python
          # было: db.set_render_status(job_id, clip_id, "done", f"clips/{clip_id}.mp4", None)
          from app.storage import upload_clip
          clip_url = upload_clip(out / "clips" / f"{clip_id}.mp4", job_id, clip_id)
          db.set_render_status(job_id, clip_id, "done", clip_url, None)
  ```

- [ ] **Шаг 4: main.py get_render — отдавать URL как есть (Неочевидное C)**

  В `app/main.py` `get_render`:
  ```python
      url = row.get("render_url")
      return {
          "status": row.get("render_status"),
          "video_url": url,            # уже полный CDN-URL (без префикса media/)
          "error": row.get("render_error"),
      }
  ```

- [ ] **Шаг 5: mypy на изменённых модулях**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv run mypy app/run.py app/tasks.py app/main.py
  ```
  Ожидаем: Success.

- [ ] **Шаг 6: Коммит**

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git add services/worker/app/run.py services/worker/app/tasks.py services/worker/app/main.py
  "feat(infra): persist artifacts+clips to Supabase; transcript_cache in Postgres; Storage URLs" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Task 7: DoD — интеграционный прогон (локальный воркер → Supabase)

**Files:** нет кода (верификация).

- [ ] **Шаг 1: `just check` зелёный (unit-уровень)**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow"
  just check
  ```
  Ожидаем: lint/mypy/tsc/anti-drift зелёные; unit-тесты PASSED (db.py I/O не unit-тестим —
  проверяем ниже интеграционно).

- [ ] **Шаг 2: Поднять локальный воркер с облачным `.env`**

  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```
  Воркер на старте дёрнет `db.init_db()` → `select 1` к Supabase. Если падает — проверить
  `SUPABASE_DB_URL` (порт 6543, пароль) и доступность пулера.

- [ ] **Шаг 3: Создать джоб (короткий ролик) и дождаться done**

  ```powershell
  # отдельный терминал
  $body = '{"source_type":"youtube","source_ref":"<короткий_YT_url>","max_clips":3}'
  Invoke-RestMethod -Uri http://localhost:8000/jobs -Method Post -ContentType "application/json" -Body $body
  # → {id: job_xxx}; поллить:
  Invoke-RestMethod -Uri http://localhost:8000/jobs/job_xxx
  ```

- [ ] **Шаг 4: Проверить ОБЛАЧНЫЙ стейт (главный DoD)**

  - Supabase Table Editor → `jobs`: строка `job_xxx`, `status=done`, `clips` (jsonb) с **полными
    `https://...supabase.co/storage/v1/object/public/clips/...` URL**.
  - `job_artifacts`: строка `job_xxx` с `meta`/`segments`/`transcript`.
  - `transcript_cache`: появилась строка (audio_sha) → повторный прогон того же видео не платит Deepgram.
  - Storage → бакет `clips` → папка `job_xxx/` с `clip_01.mp4` и т.д.
  - Открыть публичный URL клипа в браузере → **mp4 играется с CDN** (не с локального /media).
  - `GET /jobs/job_xxx` → `clips[].video_url` = тот самый CDN-URL.

- [ ] **Шаг 5: Проверить редактор-путь через Postgres**

  ```powershell
  Invoke-RestMethod -Uri http://localhost:8000/jobs/job_xxx/clips/clip_01/edit
  # → ClipEdit (ensure_edit создал дефолт из job_artifacts, не с диска)
  ```
  Затем `POST .../clips/clip_01/render` → дождаться → `GET .../render` отдаёт CDN `video_url`;
  в Storage появился перерендеренный клип.

- [ ] **Шаг 6: Проверить optimistic-lock (атомарность)**

  Дважды подряд PATCH одного клипа со СТАРОЙ `version` → второй возвращает **409** (EditConflict).

- [ ] **Шаг 7: Зафиксировать DoD в журнале CLAUDE.md**

  Дописать в «Журнал прогресса» строку: «Phase A ✅ — стейт в Supabase: jobs/artifacts/clips в
  облаке, клипы с CDN, transcript-кэш в Postgres, optimistic-lock 409. Доказано: job_xxx done,
  Storage mp4 играется, GET отдаёт CDN-URL.»

  ```powershell
  Set-Location "C:\Users\user\Desktop\ClipClow"
  git add CLAUDE.md
  "docs: Phase A done — state migrated to Supabase (Postgres+Storage), integration verified" | Out-File -FilePath services/worker/tmp/COMMIT_MSG.txt -Encoding utf8
  git commit -F services/worker/tmp/COMMIT_MSG.txt
  ```

---

## Self-Review (покрытие спеки §4-5)

- §4.1 db.py→Postgres + атомарный optimistic-lock → Task 4 ✅
- §4.2 store.py артефакты из Postgres, убрать mirror (место A) → Task 5 ✅
- §4.3 transcript-кэш durable (место B) + persist (место D) → Task 6 ✅
- §4.4 медиа → Storage + CDN (место C) → Task 3 + Task 6 ✅
- §5 схема + RLS → Task 1 ✅
- Место E (атомарный lock) → Task 4 `update_clip_edit_if_version` ✅
- Место F (yt-dlp DC-IP) → НЕ в Phase A (воркер локальный, IP домашний) → Фаза B ⚠️ отмечено
- Auth JWKS / фронт / Realtime / Modal → вне скоупа (отдельные планы) ✅

---

## Execution Handoff (после ревью плана фаундером)
- Фаза A проверяется **локально** (воркер на машине, стейт в облаке) → де-рискует до Modal.
- Затем: план Auth(JWKS)+фронт → Фаза B (Modal) → Фаза C (Realtime+квоты).
