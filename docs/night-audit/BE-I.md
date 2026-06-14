# BE-I — отчёт агента (Modal production deployment entry)

## Сводка
- Файлов проверено: 6 в `deploy/modal/` (worker.py, test_job.py, proof_ffmpeg.py,
  clipflow_modal.py, README.md, .gitignore) + кросс-чтение `app/dispatch.py`, `app/tasks.py`,
  `app/main.py`, `app/db.py`, `app/cloud_state.py`, `app/config.py`, `app/storage.py`,
  `app/pipeline/stage0_import.py` (read-only).
- Багов найдено: 5 (crit 0 / high 1 / med 2 / low 2)
- Багов починено: 1 (в моём ownership — cookies-env конфликт в worker.py)
- Тесты добавлены: 0 (worker.py — деклар. Modal-граф, не pure-логика; верификация = parse-ok +
  статическая трассировка yt-dlp поведения вживую)
- Верификация фикса: `ast.parse(worker.py)` → `parse ok`; поведение yt-dlp на несуществующем
  cookies-пути воспроизведено локально (`uv run yt-dlp --cookies <bad-path>` → traceback в
  cookiejar save/open).

## Баги

### [HIGH] YTDLP_COOKIES_FILE указывает на файл, которого может не быть в образе — worker.py:107 (было)
**Симптом:** Если при `modal deploy` локально НЕТ `www.youtube.com_cookies.txt`
(`_COOKIES.exists() == False`), файл в образ НЕ добавляется, НО `.env()` всё равно
безусловно ставил `YTDLP_COOKIES_FILE=/root/cookies.txt`. Конфиг воркера читает это в
`ytdlp_cookies_file`, и `stage0_import.download_youtube` (stage0:174) делает
`yt-dlp --cookies /root/cookies.txt`. Файла нет → yt-dlp либо падает на cookie-jar
load/save, либо тянет ПУСТОЙ jar (нулевой обход YouTube бот-гейта с DC-IP).
**Корень:** env-переменная и добавление файла были РАЗВЯЗАНЫ: переменная ставилась всегда,
файл — условно. Классический «secret/env → silent wrong behavior»: либо fail-fast на каждом
скачивании, либо тихая деградация (jar пуст → бот-гейт не обойдён → «n challenge»/403).
Воспроизведено: `uv run yt-dlp --cookies /this/path/does/not/exist.txt -F <yt-url>` →
traceback в `cookies.py save()/open()`.
**Фикс:** `YTDLP_COOKIES_FILE` теперь ставится ТОЛЬКО внутри `if _COOKIES.exists():`, в той же
цепочке, что и `add_local_file(...)`. Нет файла → переменная не задаётся → stage0 идёт без
`--cookies` (а `YTDLP_COOKIES_BROWSER=""` остался, чтобы дефолт config `"edge"` не дёрнул
`--cookies-from-browser edge` на Linux-контейнере, где edge нет). worker.py:106-126.
**Тест:** parse-ok + ручная трассировка stage0:174-177 (cookies_file пуст → ветка
`elif cookies_browser` тоже пуста → cmd без cookies-флагов).

### [MED] Upload-пайплайн на Modal идёт BackgroundTask'ом на scale-to-zero web-контейнере (timeout=900) — main.py:250 (ЧУЖОЙ ФАЙЛ, не чинил)
**Симптом:** `POST /jobs/upload` стримит файл на диск web-контейнера и делает
`bg.add_task(run_upload_job, ...)` БЕЗ проверки `dispatch.modal_spawn_enabled()` (в отличие
от `POST /jobs` и `POST /render`, которые спавнят отдельную функцию). На Modal весь тяжёлый
пайплайн (transcribe + reframe ASD@25fps + PySceneDetect ~2× длительности + render) исполняется
ВНУТРИ `web` (`@modal.asgi_app`, `timeout=900` = 15 мин, `min_containers=0`). Длинное видео
→ либо упирается в 900-с таймаут web и убивается на полпути, либо контейнер скейлится в 0 после
ответа и фон-таск умирает. Джоб остаётся в `processing`/`queued` навсегда.
**Корень:** загруженный файл лежит на ЛОКАЛЬНОМ диске web-контейнера, поэтому его нельзя просто
`spawn` в отдельную `run_job`-функцию (у неё другой контейнер/диск). Это архитектурный пробел:
для upload-пути на Modal нужно (а) залить upload-файл в R2, затем (б) `spawn` отдельной
функции, которая скачает его и прогонит пайплайн. Сейчас такой Modal-функции (`upload_job`)
НЕТ в worker.py, и dispatch её не знает.
**Фикс:** не чинил — затрагивает `main.py` (read-only для BE-I) + требует новой Modal-функции в
worker.py + заливки upload в R2 в `app.storage`. Передаю оркестратору (см. ниже). В worker.py
сейчас определены только `web`/`run_job`/`render_job` — для upload-пути нужен 4-й энтрипоинт
ИЛИ переиспользование `run_job` с предварительной R2-заливкой + `source_type="upload_r2"`.
Likelihood: средняя (upload — не основной поток; основной = YouTube-URL/spawn). Blast radius:
высокий для тех, кто грузит файл (тихо зависший джоб).

### [MED] chapters-кэш на scratch-диске Modal → повторная оплата Gemini на каждом холодном контейнере — main.py:371-378 / tasks.py:180 (ЧУЖОЙ ФАЙЛ, документировано в коде уже)
**Симптом:** `generate_chapters_job` пишет `chapters.json` на локальный диск контейнера
(`artifacts.job_dir`). На Modal web — scale-to-zero, новый контейнер = пустой scratch → кэш
теряется → каждый повторный GET /chapters перегенерирует главы (Gemini-вызов ~$0.01-0.03).
Также: BackgroundTask в web (короткий Gemini-вызов, обычно <30с, в пределах 900с — НЕ
зависает, в отличие от upload-пайплайна), но кэш не персистится в Postgres.
**Корень:** chapters-кэш не переведён в cloud_state (Postgres), в отличие от job-артефактов/
транскрипта. Уже помечено TODO в коде (main.py:371-372 «перенос кэша в Postgres — follow-up
Phase C»).
**Фикс:** не чинил — `main.py`/`tasks.py`/`editor/chapters.py` вне моего ownership. Передаю
оркестратору как известный follow-up. Likelihood: высокая (повторные GET частые). Blast radius:
низкий (деньги, не поломка; ~$0.02/регенерация).

### [LOW] bgutil-ytdlp-pot-provider (PO-token плагин) не установлен в Modal-образе — worker.py:81-98
**Симптом:** pyproject воркера держит `bgutil-ytdlp-pot-provider>=1.3.1` (yt-dlp PO-token
provider для обхода YouTube бот-гейта), но Modal-образ его НЕ ставит. Образ полагается на
Deno + `--remote-components ejs:github` (nsig/«n»-челлендж) + cookies. Если YouTube ужесточит
PO-token-гейт на DC-IP, скачивание может падать без этого плагина.
**Корень:** список pip_install в образе — ручное зеркало pyproject, и bgutil опущен осознанно
(подход через Deno/ejs новее). Но это не задокументировано как осознанное решение в worker.py.
**Фикс:** не чинил (вероятно осознанный выбор — Deno-путь покрывает nsig). Флагую как
deployment-risk низкой уверенности: если фаундер увидит «Sign in to confirm you're not a bot»
/ format-missing на Modal — добавить `bgutil-ytdlp-pot-provider` в `pip_install` + (возможно)
bgutil HTTP-провайдер. Likelihood: низкая-средняя (зависит от политики YouTube). Blast radius:
высокий (нет скачивания = нет продукта на YouTube-пути).

### [LOW] Стейл-документация README.md ссылается на несуществующий app.py — README.md:37,39 / clipflow_modal.py
**Симптом:** `deploy/modal/README.md` описывает СТАРЫЙ benchmark-scaffold и зовёт
`modal run deploy/modal/app.py` — такого файла НЕТ (бенчмарк лежит в `clipflow_modal.py`,
а боевой энтрипоинт — `worker.py`). README не упоминает `worker.py` / `modal deploy`.
**Корень:** README не обновлён после перехода benchmark → боевой worker.py.
**Фикс:** не чинил (документация бенчмарка, не баг рантайма; вне scope охоты за багами). Можно
обновить отдельно. `clipflow_modal.py` сам себя помечает «УСТАРЕВШИЙ SPIKE — заменён worker.py»
(clipflow_modal:14) — корректно зафенсен, не путь прода.

## Передать оркестратору (чужие/общие файлы)

1. **[HIGH-арх] Upload-путь на Modal зависает** (`main.py:248-250`, `tasks.py:245-281`,
   `dispatch.py`, `storage.py`). `POST /jobs/upload` не спавнит — гоняет весь пайплайн
   BackgroundTask'ом в `web` (timeout=900, scale-to-zero). Нужно: (а) `app.storage` —
   функция заливки локального upload-файла в R2; (б) новая Modal-функция в worker.py
   (`upload_job` или переиспользование `run_job` с R2-source); (в) ветка `if
   dispatch.modal_spawn_enabled():` в `create_upload_job`, симметрично `create_job`.
   Я (BE-I) подготовлю Modal-функцию в worker.py, как только владелец main.py/storage.py
   определит контракт (R2-ключ upload-источника).

2. **[MED] chapters-кэш не в Postgres** (`main.py:371`, `tasks.py:180`, `editor/chapters.py`).
   На Modal перегенерируется на каждом холодном контейнере (Gemini $$). Перенести кэш
   `chapters.json` в cloud_state/Postgres (как job-артефакты). Уже TODO в коде.

3. **[INFO] Кросс-проверка dispatch/storage/cloud_state — чисто.** `dispatch.spawn` корректно
   резолвит `quip-worker::<fn>` по имени (переживает include_source=False + serialized).
   `db.py` полностью dual-mode gated через `cloud_state.cloud_enabled()` (нет случайного
   SQLite на Modal). `cloud_enabled()` = STORAGE_BACKEND=r2 + SUPABASE_URL + SERVICE_ROLE_KEY
   (config.py:28-ish) — гейтинг корректный. Error-propagation в `run_job` целостный:
   `run_pipeline_job` ловит JobError/Exception → `db.set_failed` → cloud_state → Postgres
   (джоб НЕ исчезает, помечается failed). spawn-сбой в `create_job` тоже → `db.set_failed` +
   HTTP 500 (main.py:206-215). Хорошо.

## Не успел / открыто
- **Тюнинг-риски (low, не баги):** `run_job` timeout=3600 (60 мин) и БЕЗ явного лимита памяти.
  Тяжёлый reframe (ASD@25fps + PySceneDetect ~2× длительности на CPU) на длинном видео с
  многими клипами может упереться в 60 мин ИЛИ OOM (MediaPipe+torch+ffmpeg+кадры в памяти).
  Дефолтный план кап ≤30 мин видео → вероятно ок для free/starter; Pro (длиннее) — проверить
  под нагрузкой. Рекомендация: добавить `memory=` (напр. 4096) и при необходимости поднять
  timeout на `run_job`. Не менял — нужен реальный замер, которого без деплоя нет.
- **test_job.py:14** спавнит `run_job` НЕ вставив строку job в Postgres заранее →
  `db.update_status` внутри пайплайна обновит несуществующую строку (PostgREST PATCH 0 rows,
  тихо). Для боевого пути строку вставляет `POST /jobs` (main.py:203) ДО spawn — там ок. Это
  только тест-скрипт; если им пользуются для smoke-теста, статус-апдейты «пропадут» (артефакты/
  клипы в R2 всё равно лягут через set_done). Низкий приоритет — оставил как есть (тест-утилита).
- Не смог запустить `modal deploy`/`modal run` (нет кредов — и не создаю). Вся верификация —
  статическая + воспроизведение yt-dlp cookies-поведения локально.
