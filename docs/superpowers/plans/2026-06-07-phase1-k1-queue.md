# Phase 1 · K1 — Очередь (RQ+Redis) + надёжность — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить FastAPI `BackgroundTasks` на durable-очередь RQ+Redis: задачи переживают рестарт, обрабатываются параллельно, транзиентные сбои ретраятся с бэк-оффом, у стадий есть таймауты.

**Architecture:** `POST /jobs` кладёт задачу в Redis-очередь (RQ). Отдельный процесс-воркер (`rq SimpleWorker` — на Windows без fork) берёт задачу и гоняет существующий `run_pipeline_job`. Pure-логика (классификация ошибки транзиентная/нет, расписание бэк-оффа) изолирована и покрыта тестами; обёртка `retry_call` применяется к сетевым операциям (yt-dlp, Deepgram). Падение задачи исчерпав ретраи → статус `failed` в SQLite (без тихих фолбэков).

**Tech Stack:** Python 3.12, RQ, redis-py, FastAPI, SQLite, pytest, fakeredis (тесты), Docker/Memurai (локальный Redis). Дисциплина §4А: `just check` зелёный до коммита, типы только через codegen.

---

## Файловая структура (что трогаем)

- Create: `services/worker/app/retry.py` — PURE: `is_transient`, `backoff_delays`, `retry_call`.
- Create: `services/worker/app/queue.py` — Redis-подключение + RQ-очередь (`get_queue`).
- Create: `services/worker/tests/unit/test_retry.py` — тесты pure-логики ретраев.
- Modify: `services/worker/pyproject.toml` — деп `rq`, `redis`; dev-деп `fakeredis`.
- Modify: `services/worker/app/config.py` — `redis_url`, `queue_name`, `job_timeout_sec`.
- Modify: `services/worker/app/tasks.py` — `run_pipeline_job` остаётся, добавить `report_failure` (RQ on_failure → set_failed).
- Modify: `services/worker/app/main.py` — `POST /jobs` enqueue в RQ вместо BackgroundTasks.
- Modify: `services/worker/app/pipeline/stage0_import.py` — таймаут в `_run` (yt-dlp/ffmpeg) + `retry_call` на download.
- Modify: `services/worker/app/pipeline/stage5_render.py` — таймаут в `_run` (ffmpeg).
- Modify: `justfile` — рецепты `redis` (Docker) и `worker-queue` (rq SimpleWorker).
- Modify: `.env.example` — `REDIS_URL`.

> Запускать `just`/`uv`/`git commit` — из PowerShell с registry-PATH refresh (см. CLAUDE.md). Коммит-сообщения — файлом (`git commit -F`), не пайпом.

---

### Task 0: Redis локально + зависимости

**Files:**
- Modify: `services/worker/pyproject.toml`
- Modify: `services/worker/app/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Поднять локальный Redis**

Docker (предпочтительно):
```
docker run -d --name clipflow-redis -p 6379:6379 redis:7-alpine
```
Нет Docker на Windows → Memurai (native Redis-совместимый, https://www.memurai.com) или WSL.
Проверка: `docker exec clipflow-redis redis-cli ping` → `PONG`.

- [ ] **Step 2: Добавить зависимости**

Run (из `services/worker`): `uv add rq redis` и `uv add --dev fakeredis`
Expected: pyproject `dependencies` содержит `rq`, `redis`; dev — `fakeredis`.

- [ ] **Step 3: Конфиг Redis**

Modify `app/config.py` — добавить в класс `Settings` (после блока pipeline tuning):
```python
    # queue (K1)
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "clipflow"
    job_timeout_sec: int = 1800  # 30 мин потолок на задачу
```

- [ ] **Step 4: .env.example**

Modify `.env.example` — добавить в секцию PATHS/DB:
```bash
REDIS_URL=redis://localhost:6379/0
```

- [ ] **Step 5: Commit**

```
git add services/worker/pyproject.toml services/worker/uv.lock services/worker/app/config.py .env.example
git commit -F <msg-file>   # "chore(queue): add rq/redis deps + REDIS_URL config (K1.0)"
```

---

### Task 1: `retry.py` — классификация ошибок + бэк-офф (PURE, TDD)

**Files:**
- Create: `services/worker/app/retry.py`
- Test: `services/worker/tests/unit/test_retry.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/unit/test_retry.py`:
```python
"""Тесты pure-логики ретраев: классификация транзиентных ошибок + бэк-офф."""

import httpx
import pytest

from app.errors import JobError
from app.retry import backoff_delays, is_transient, retry_call


class TestIsTransient:
    def test_httpx_network_error_is_transient(self) -> None:
        assert is_transient(httpx.ConnectError("boom")) is True

    def test_timeout_is_transient(self) -> None:
        assert is_transient(httpx.ReadTimeout("slow")) is True

    def test_joberror_429_503_transient(self) -> None:
        assert is_transient(JobError("select", "Gemini HTTP 503 UNAVAILABLE")) is True
        assert is_transient(JobError("transcribe", "Deepgram HTTP 429")) is True

    def test_joberror_other_not_transient(self) -> None:
        assert is_transient(JobError("import", "источник 127 мин > лимита")) is False

    def test_value_error_not_transient(self) -> None:
        assert is_transient(ValueError("bad input")) is False


class TestBackoffDelays:
    def test_exponential(self) -> None:
        assert backoff_delays(attempts=3, base=2.0) == [2.0, 4.0, 8.0]

    def test_single(self) -> None:
        assert backoff_delays(attempts=1, base=5.0) == [5.0]

    def test_zero(self) -> None:
        assert backoff_delays(attempts=0, base=2.0) == []


class TestRetryCall:
    def test_succeeds_first_try(self) -> None:
        calls = {"n": 0}

        def fn() -> str:
            calls["n"] += 1
            return "ok"

        assert retry_call(fn, attempts=3, base=0.0) == "ok"
        assert calls["n"] == 1

    def test_retries_transient_then_succeeds(self) -> None:
        calls = {"n": 0}

        def fn() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("flaky")
            return "ok"

        assert retry_call(fn, attempts=3, base=0.0) == "ok"
        assert calls["n"] == 3

    def test_non_transient_raises_immediately(self) -> None:
        calls = {"n": 0}

        def fn() -> str:
            calls["n"] += 1
            raise JobError("import", "fatal")

        with pytest.raises(JobError):
            retry_call(fn, attempts=3, base=0.0)
        assert calls["n"] == 1  # не ретраили

    def test_exhausts_then_raises_last(self) -> None:
        def fn() -> str:
            raise httpx.ConnectError("always")

        with pytest.raises(httpx.ConnectError):
            retry_call(fn, attempts=2, base=0.0)
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/unit/test_retry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.retry'`

- [ ] **Step 3: Реализация `app/retry.py`**

Create `app/retry.py`:
```python
"""Pure-логика ретраев: что считать транзиентным + экспоненциальный бэк-офф + retry_call.

base=0.0 в тестах → без реального сна. JobError с 429/503 в тексте — транзиентный.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import httpx

from app.errors import JobError

T = TypeVar("T")

_TRANSIENT_MARKERS = ("429", "503", "500", "502", "504", "unavailable", "timeout", "temporarily")


def is_transient(exc: BaseException) -> bool:
    """Сетевые ошибки httpx и JobError с маркерами перегрузки/таймаута → транзиентные."""
    if isinstance(exc, httpx.HTTPError):
        return True
    if isinstance(exc, JobError):
        text = str(exc).lower()
        return any(m in text for m in _TRANSIENT_MARKERS)
    return False


def backoff_delays(attempts: int, base: float = 2.0) -> list[float]:
    """Экспоненциальный бэк-офф: [base, base*2, base*4, ...] длиной attempts."""
    return [base * (2**i) for i in range(attempts)]


def retry_call(fn: Callable[[], T], *, attempts: int = 3, base: float = 2.0) -> T:
    """Вызвать fn с ретраями на транзиентных ошибках. Не-транзиентные — сразу наверх.

    Спит base*2^i перед попыткой i+1 (base=0.0 → без сна). Исчерпав — кидает последнюю.
    """
    delays = backoff_delays(attempts, base)
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except BaseException as e:  # noqa: BLE001 — решение о ретрае делает is_transient
            if not is_transient(e):
                raise
            last = e
            if i < attempts - 1 and delays[i] > 0:
                time.sleep(delays[i])
    assert last is not None
    raise last
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `uv run pytest tests/unit/test_retry.py -q`
Expected: PASS (все тесты)

- [ ] **Step 5: lint+mypy**

Run: `uv run ruff check app/retry.py tests/unit/test_retry.py && uv run ruff format app/retry.py tests/unit/test_retry.py && uv run mypy app`
Expected: clean

- [ ] **Step 6: Commit**

```
git add services/worker/app/retry.py services/worker/tests/unit/test_retry.py
git commit -F <msg>   # "feat(queue): retry classification + backoff (pure, TDD) (K1.1)"
```

---

### Task 2: `queue.py` — Redis + RQ очередь

**Files:**
- Create: `services/worker/app/queue.py`

- [ ] **Step 1: Реализация**

Create `app/queue.py`:
```python
"""Подключение к Redis и очередь RQ (K1). Воркер берёт задачи отсюда."""

from __future__ import annotations

from functools import lru_cache

from redis import Redis
from rq import Queue

from app.config import get_settings


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_queue() -> Queue:
    return Queue(get_settings().queue_name, connection=get_redis())
```

- [ ] **Step 2: mypy/ruff**

Run: `uv run ruff check app/queue.py && uv run ruff format app/queue.py && uv run mypy app`
Expected: clean (если redis/rq без стабов — добавить в `[[tool.mypy.overrides]]` `module=["rq","rq.*","redis","redis.*"] ignore_missing_imports=true`)

- [ ] **Step 3: Commit**

```
git add services/worker/app/queue.py services/worker/pyproject.toml
git commit -F <msg>   # "feat(queue): redis connection + RQ queue (K1.2)"
```

---

### Task 3: Таймауты стадий (yt-dlp/ffmpeg)

**Files:**
- Modify: `services/worker/app/pipeline/stage0_import.py` (`_run`)
- Modify: `services/worker/app/pipeline/stage5_render.py` (`_run`)

- [ ] **Step 1: Таймаут в stage0 `_run`**

Modify `stage0_import.py` — функция `_run`: добавить параметр и передать в subprocess:
```python
def _run(cmd: list[str], *, cwd: Path | None = None, timeout: float = 1200.0) -> subprocess.CompletedProcess[str]:
    """Запустить процесс; JobError при отсутствии бинарника, ненулевом коде или таймауте."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise JobError(_STAGE, f"не найден бинарник {cmd[0]!r}: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise JobError(_STAGE, f"{cmd[0]} timeout ({timeout}s)") from e
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-500:]
        raise JobError(_STAGE, f"{cmd[0]} код {proc.returncode}: {tail}")
    return proc
```

- [ ] **Step 2: Таймаут в stage5 `_run`-эквиваленте**

Modify `stage5_render.py` `render_clip` `subprocess.run(...)` — добавить `timeout=900.0` и поймать `subprocess.TimeoutExpired`:
```python
    try:
        proc = subprocess.run(cmd, cwd=data_dir, capture_output=True, text=True, timeout=900.0)
    except FileNotFoundError as e:
        raise JobError(_STAGE, f"не найден ffmpeg: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise JobError(_STAGE, f"ffmpeg render timeout (900s)") from e
```

- [ ] **Step 3: Тесты не ломаются**

Run: `uv run pytest tests/unit -q`
Expected: PASS (сигнатуры pure-функций не менялись)

- [ ] **Step 4: Commit**

```
git add services/worker/app/pipeline/stage0_import.py services/worker/app/pipeline/stage5_render.py
git commit -F <msg>   # "feat(reliability): per-stage subprocess timeouts (R5) (K1.3)"
```

---

### Task 4: Ретраи сетевых операций (yt-dlp, Deepgram)

**Files:**
- Modify: `services/worker/app/pipeline/stage0_import.py` (`download_youtube`)
- Modify: `services/worker/app/pipeline/stage1_transcribe.py` (`transcribe`)

- [ ] **Step 1: Обернуть download в retry_call**

Modify `stage0_import.py` `import_youtube` (или `download_youtube` вызов): импортировать `from app.retry import retry_call` и обернуть:
```python
    mp4 = retry_call(lambda: download_youtube(url, out_dir), attempts=3, base=3.0)
```
(в `import_youtube`, вместо прямого `mp4 = download_youtube(url, out_dir)`)

- [ ] **Step 2: Обернуть Deepgram-вызов в retry_call**

Modify `stage1_transcribe.py` `transcribe`: обернуть `call_deepgram`:
```python
        resp = retry_call(
            lambda: call_deepgram(wav, api_key=key, model=s.deepgram_model, language="en"),
            attempts=3, base=3.0,
        )
```
+ импорт `from app.retry import retry_call`. (Gemini в stage2 уже ретраит сам.)

- [ ] **Step 3: Тесты + mypy**

Run: `uv run pytest tests/unit -q && uv run mypy app`
Expected: PASS / clean (юнит-тесты сетевые не дёргают)

- [ ] **Step 4: Commit**

```
git add services/worker/app/pipeline/stage0_import.py services/worker/app/pipeline/stage1_transcribe.py
git commit -F <msg>   # "feat(reliability): retry transient network ops (yt-dlp, deepgram) (K1.4)"
```

---

### Task 5: `POST /jobs` → enqueue в RQ; on_failure → failed

**Files:**
- Modify: `services/worker/app/tasks.py` (добавить `report_failure`)
- Modify: `services/worker/app/main.py` (enqueue вместо BackgroundTasks)

- [ ] **Step 1: report_failure в tasks.py**

Modify `tasks.py` — добавить callback (RQ зовёт при исчерпании ретраев/падении):
```python
def report_failure(job, connection, exc_type, exc_value, tb) -> None:  # noqa: ANN001
    """RQ on_failure: задача упала окончательно → статус failed в SQLite."""
    db.set_failed(job.args[0], f"{exc_type.__name__}: {exc_value}")
```
(`job.args[0]` = job_id, т.к. enqueue(run_pipeline_job, job_id, ...))

- [ ] **Step 2: main.py — enqueue**

Modify `main.py`:
- удалить импорт/использование `BackgroundTasks`;
- импорт `from rq import Retry; from app.queue import get_queue; from app.tasks import report_failure, run_pipeline_job`;
- `create_job`:
```python
@app.post("/jobs", status_code=202)
def create_job(body: CreateJobBody) -> dict[str, Any]:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    db.insert_job(job_id, body.source_type, body.source_ref)
    get_queue().enqueue(
        run_pipeline_job,
        job_id, body.source_type, body.source_ref,
        retry=Retry(max=2, interval=[30, 90]),
        job_timeout=get_settings().job_timeout_sec,
        on_failure=report_failure,
    )
    return {"id": job_id, "status": "queued", "stage": "queued", "progress": 0}
```
+ `from app.config import get_settings`.

- [ ] **Step 3: mypy/ruff**

Run: `uv run ruff check app && uv run ruff format app && uv run mypy app`
Expected: clean

- [ ] **Step 4: Commit**

```
git add services/worker/app/main.py services/worker/app/tasks.py
git commit -F <msg>   # "feat(queue): POST /jobs enqueues to RQ; on_failure -> failed (K1.5)"
```

---

### Task 6: justfile рецепты (redis, worker-queue)

**Files:**
- Modify: `justfile`

- [ ] **Step 1: Рецепты**

Modify `justfile` — добавить:
```
# локальный Redis в Docker
redis:
    docker run -d --name clipflow-redis -p 6379:6379 redis:7-alpine

# воркер очереди (Windows: SimpleWorker — без fork)
worker-queue:
    cd services/worker; uv run rq worker {{queue}} --url redis://localhost:6379/0 --worker-class rq.SimpleWorker

queue := "clipflow"
```
> На Windows ОБЯЗАТЕЛЬНО `--worker-class rq.SimpleWorker` (RQ по умолчанию использует os.fork, которого на Windows нет).

- [ ] **Step 2: Проверить парсинг**

Run (PowerShell, PATH refresh): `just --list`
Expected: `redis`, `worker-queue` в списке

- [ ] **Step 3: Commit**

```
git add justfile
git commit -F <msg>   # "chore(queue): just recipes redis + worker-queue (SimpleWorker on Windows) (K1.6)"
```

---

### Task 7: Интеграционная проверка (DoD K1)

**Files:** нет (проверка)

- [ ] **Step 1: Поднять Redis + worker-queue + web/worker REST**

Терминалы (PowerShell, PATH refresh):
- `just redis` (один раз)
- `just worker-queue`  (процесс-воркер очереди)
- `cd services/worker; uv run uvicorn app.main:app --port 8000`  (REST, теперь только enqueue)

- [ ] **Step 2: Отправить 3 задачи разом**

```
1..3 | % { curl -s -X POST http://localhost:8000/jobs -H "Content-Type: application/json" -d '{"source_type":"youtube","source_ref":"https://www.youtube.com/watch?v=EDCwQe7P8T0"}' }
```
Expected: три `202 {"id":"job_..."}`. Воркер берёт их из очереди (видно в логе worker-queue).
Цель: все три доходят до `done` (GET /jobs/{id}); транзиентный сбой ретраится.

- [ ] **Step 3: Durability — убить воркер посреди задачи**

Запустить 1 задачу, во время обработки `Ctrl-C` воркер-очереди → перезапустить `just worker-queue`.
Expected: задача НЕ теряется (RQ держит в Redis); до-выполняется или (исчерпав) `failed`. Не «висит queued» бесконечно.

- [ ] **Step 4: Зафиксировать результат**

GET /jobs/{id} каждого → `done`/`failed` с понятным статусом. Если зелено — DoD K1 выполнен.

---

### Task 8: Финальный гейт + журнал

- [ ] **Step 1: just check**

Run (PowerShell, PATH refresh, repo root): `just check`
Expected: All passed (lint+mypy+tsc+тесты+anti-drift)

- [ ] **Step 2: Обновить журнал CLAUDE.md**

Добавить в чеклист запись K1 (что сделано + чем доказано), отметить грабли (SimpleWorker на Windows, Redis через Docker/Memurai).

- [ ] **Step 3: Commit + push**

```
git add -A
git commit -F <msg>   # "docs(journal): K1 (RQ queue + reliability) done"
git push origin main
```

---

## Self-Review (по чеклисту скилла)

- **Покрытие spec K1:** очередь (Task 2,5,6,7) ✓; ретраи/бэк-офф (Task 1,4) ✓; таймауты стадий (Task 3) ✓; durability/рестарт (Task 7) ✓; статусы в SQLite (уже есть, on_failure добавлен Task 5) ✓.
- **Плейсхолдеры:** нет — у каждого шага реальный код/команда.
- **Консистентность типов:** `run_pipeline_job(job_id, source_type, source_ref)` — та же сигнатура в enqueue (Task 5) и в `report_failure` (`job.args[0]`=job_id). `retry_call(fn, *, attempts, base)` — одна сигнатура в Task 1/4.
- **Граница Windows:** SimpleWorker зафиксирован (Task 6). Redis-инфра — Task 0 (Docker/Memurai).

## После K1 — следующие планы (по дизайну, в порядке)
K2 (кэш транскрипции), K3 (авто-язык), K4 (progressive output), K5 (storage-абстракция),
K6 (стили субтитров), K7 (cost-дашборд) — каждый получает свой план перед исполнением.
