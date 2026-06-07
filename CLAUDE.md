# CLAUDE.md — правила работы над ClipFlow

Единственный источник плана: `CLIPFLOW_DEV_PLAN.md`. Делай строго по нему, сверху вниз.

## Железные правила
1. Работай ПО ОДНОМУ шагу чеклиста (раздел 5). Не перескакивай.
2. На каждый шаг: сначала покажи мини-план шага, потом делай.
3. Тест — ПЕРВЫМ на любой pure-логике (тайминги субтитров, crop 9:16,
   группировка слов, валидация score, пересечения сегментов, маппинг офсетов).
4. Шаг НЕ готов, пока его DoD не зелёный. Покажи РЕАЛЬНЫЙ вывод проверки
   (команда + результат). Без доказательства не пиши «готово».
5. Перед каждым коммитом — `just check` зелёный (lint + mypy + tsc + test-unit
   + anti-drift). Коммит на каждый зелёный гейт, conventional commits.
6. Типы — ТОЛЬКО через `just types` (codegen из models.py). НИКОГДА не правь
   `packages/shared/*` руками. Контракты меняются только в `app/models.py`.
7. Никакого скоупа сверх плана. «Магия», auth, оплата — это Phase 1+, не трогай.
8. Никаких `except: pass` и тихих фолбэков. Ошибка → JobError + статус failed.
9. Если DoD не сходится 2 раза подряд — СТОП, спроси меня. Не угадывай.
10. Не трогай репозиторий лендинга Shorts-Automatizator.

## Границы кода
- `pipeline/*` — чистые функции (вход→выход, без HTTP/DB).
- Склейка только в `tasks.py` / `run.py`. Логика дублируется → выноси в одну функцию.
- Docstring на каждой публичной функции. README в каждом пакете. ADR на решения.

---

## Журнал прогресса (ЧИТАТЬ ПЕРВЫМ в новой сессии)

### Состояние среды (Windows 11, проверено 2026-06-07)
- Уже стоят: `node` 22.19.0, `pnpm` 10.29.2, `git` 2.49.0, `gh` 2.92.0,
  `python` 3.12.10, `winget` 1.28.
- A1 доставил: `ffmpeg` 8.1.1 (Gyan build), `uv` 0.11.19, `just` 1.51.0.

### Грабли инструментов агента (важно для скорости)
- **Bash-инструмент = настоящий bash** (`/usr/bin/bash`), НЕ PowerShell. `Select-Object`
  и пр. PS-командлеты в нём падают. Для Windows-специфики (PATH, реестр, winget) —
  инструмент **PowerShell**.
- **Состояние shell между вызовами НЕ сохраняется** (env-vars/функции сбрасываются).
  Поэтому после установки бинарника PATH подтягивать В ТОМ ЖЕ вызове, где проверяешь:
  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  ```
  Это заменяет «перезапусти терминал» для текущего процесса.
- **`just check` гейт появляется только в A6** (до этого нет justfile/тестов). Бутстрап-
  коммиты A3–A5 идут ДО существования гейта — это нормально и по плану.
- **git identity** (глобальная): name=`Varenik-vkusny`, email=`akybaevtimur7@gmail.com`
  (НЕ дзакпеловский — это осознанный конфиг фаундера, не трогаю).
- В корне periodically появляется чужой `debug.log` (ICU-ошибки Electron) — он в
  `.gitignore` (`*.log`), не коммитим, не удаляем.

### Каталог репо — РЕШЕНО (2026-06-07)
- **Корень репо = `C:\Users\user\Desktop\ClipClow`** (текущая рабочая папка). Все пути
  плана §5 трактуем относительно неё.
- **GitHub:** `Varenik-vkusny/clipflow` (private). `origin` уже настроен. Аккаунт `gh` =
  `Varenik-vkusny` (scopes repo/workflow).
- **PENDING (последним действием сессии):** переименовать папку `ClipClow → clipflow`.
  ПОЧЕМУ не сейчас: харнесс держит cwd = `...\ClipClow`; ренейм посреди сессии сломает
  все последующие команды. Git/remote переживут ренейм (пути относительные). После
  ренейма — переоткрыть Claude Code на `...\clipflow`.

### Чеклист прохождения (ставлю [x] только когда DoD зелёный и вывод показан)
- [x] **A1** — ffmpeg/uv/just установлены, версии печатаются. 2026-06-07.
- [x] **A2** — `git init -b main` в ClipClow + `Varenik-vkusny/clipflow` (private) + origin.
      Лендинг pushedAt не изменился (2026-06-06T18:01:34Z). 2026-06-07.
- [x] **A3** — `.gitignore` + дерево §3 + первый коммит `a14814e`. git status чистый. 2026-06-07.
- [x] **A4** — `apps/web` (Next 16, Tailwind v4, App Router) + pnpm workspace + prettier.
      `pnpm --filter web dev` → :3000 отдаёт 200. Коммит `1f980fd`. 2026-06-07.
- [x] **A5** — `services/worker` (uv, hatchling, пакет `app`), `/healthz` → ok.
      STOP-GATE чисто: :3000 (200) + :8000 одновременно. Коммит `3030e00`. 2026-06-07.
- [x] **A6** — `models.py` (источник типов, тест-первым) + `export_schema.py` + codegen
      `@clipflow/shared` + `justfile` + mypy strict + `.gitattributes` + pre-commit.
      `just check` зелёный, `just types` идемпотентен, `pre-commit run -a` ок. Коммит `0079e50`. 2026-06-07.
      ✅ **ЭТАП A (бутстрап) ЗАВЕРШЁН.**
- [x] **B1/B2** — Import: `app/errors.py` (JobError) + `app/pipeline/stage0_import.py`.
      pure-логика (parse_fps, build_source_meta) TDD, 21 unit-тест. Реальный прогон
      (EDCwQe7P8T0, ~33 мин): mp4 1920×1080 играется, wav pcm_s16le/16000/mono,
      meta.json (duration=1987.6, fps=23.976). DoD зелёный. Коммит `fe47329`. 2026-06-07.
      ⚠️ Видео-кодек source.mp4 = **AV1** (YouTube отдаёт AV1-в-mp4 при ext=mp4).
      gyan-ffmpeg декодит AV1 → этап G ок. Если на G всплывёт декод — добавить
      `[vcodec^=avc1]` в yt-dlp format. Тестовый ролик мультиспикерный (Mafia show) —
      для C ок (речь есть), для E reframe ожидаемо труднее (R1, многоликий кадр).
- [x] **C1** — Транскрипция: `app/config.py` (pydantic-settings, fail-fast) +
      `app/pipeline/stage1_transcribe.py`. Deepgram REST `/v1/listen` через httpx
      (НЕ генерёный SDK v7). pure-нормализатор TDD + контракт-тест на реальной фикстуре.
      Реальный прогон sample01: 5446 слов, en, времена в секундах (first=30.22),
      last_end 1970.7 ≤ dur+0.5, cost ≈$0.14, 51.8s. DoD зелёный. 2026-06-07.
- [x] **D1/D2** — Выбор моментов (**Gemini**, structured output) → segments.json. ГЛАВНЫЙ GATE.
      LLM Anthropic→**Gemini** (нет Anthropic-ключа; swappable). D2 pure (clamp/snap/
      indices_to_times/resolve_overlaps/postprocess) — 19 тестов. D1 `select_segments` с
      ретраями (R7). Реальный прогон sample01: 4–5 сегментов, 15–60с, без overlap, reason
      КОНКРЕТНЫЙ, score∈[0,1]. ~$0.016/прогон, ~39с. DoD зелёный. 2026-06-07.
      ⚠️ free-tier: **2.5-pro = квота 0**, **2.5-flash транзиентно 503** → дефолт
      `gemini-flash-latest` (config + .env.example). Платный тариф → можно pro.
      ⚠️ В ТВОЁМ `.env` стоит `LLM_MODEL=gemini-2.5-pro` (из шаблона) — поменять на
      `gemini-flash-latest`, иначе пайплайн 429-ит.
- [ ] **E1** — Reframe 9:16 (MediaPipe face → static crop).
- [ ] **F1** — Субтитры ASS (группировка слов, тайминг от клипа).
- [ ] **G1** — Cut+Encode FFmpeg → clips/*.mp4 (1080×1920).
- [ ] **H1** — `run.py` склейка Stage 0→5 + runs.jsonl. STOP-GATE 3.
- [ ] **I1/I2/I3** — Минимальный web (токены лендинга, типы, компоненты).
- [ ] **J1/J2** — worker REST+SQLite + реальный прогон. ГЛАВНЫЙ ГЕЙТ UI.

> Правило журнала: после КАЖДОГО зелёного DoD — отметить [x] здесь и дописать
> одну строку «что сделано + чем доказано». Это контекст для следующей сессии.

### Расхождения плана с реальностью (учесть на будущих шагах)
- **Tailwind v4** (Next 16 ставит v4, не v3): НЕТ `tailwind.config.ts`. Конфиг —
  через CSS `@theme` в `apps/web/app/globals.css`. На **I1** мост токенов лендинга
  делать через `@theme`, а НЕ через `tailwind.config.ts`, как написано в плане.
- **Next.js 16** ломает API относительно обучающих данных (см. `apps/web/AGENTS.md`).
  Перед написанием web-кода (I1–I3) читать `apps/web/node_modules/next/dist/docs/`
  или свериться через context7.
- **TODO на A6:** добавить `.gitattributes` (`* text=auto eol=lf`, плюс явный `eol=lf`
  для `packages/shared/contract.json` и `src/types.ts`) — иначе CRLF↔LF на Windows
  может ложно ронять anti-drift `git diff --exit-code packages/shared`.
- Версии (зафиксировано A4): next 16.2.7, react 19.2.4, tailwindcss 4.3.0,
  typescript 5.9.3, eslint 9.39.4, prettier ^3.8.3.
- **Worker layout (A5):** пакет импортируется как `app` (НЕ src-layout). uv init по
  умолчанию делает `src/<name>` + бэкенд `uv_build` — заменено на **hatchling**
  (`[tool.hatch.build.targets.wheel] packages=["app"]`). `uv sync` ставит проект
  editable → `app` импортируется везде.
- **ruff config:** `select` живёт под `[tool.ruff.lint]` (не `[tool.ruff]`, как в плане) —
  иначе deprecation-варнинг в новом ruff.
- **Грабли Next 16 dev:** `next dev` (Turbopack) держит ОТДЕЛЬНЫЙ серверный процесс +
  lock. `TaskStop` на pnpm-обёртке его НЕ убивает → зомби держит :3000. Гасить web/worker
  по порту/PID:
  ```powershell
  foreach ($port in 3000,8000) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select -Expand OwningProcess -Unique | % { Stop-Process -Id $_ -Force } }
  ```
- Версии воркера (A5): mediapipe 0.10.35, opencv-headless 4.13, numpy 2.4.6,
  fastapi 0.136.3, pydantic 2.13.4, ruff 0.15.16, mypy 2.1.0, pytest 9.0.3.

### Грабли инструментов (A6) — КРИТИЧНО для коммитов
- **`just` НЕ виден в Bash-инструменте** (winget-шим не на bash-PATH). Любой `just`
  запускаем из **PowerShell с обновлением PATH из реестра** (строка выше). Дочерние
  recipe-шеллы наследуют PATH → uv/pnpm/git внутри рецептов резолвятся.
- **pre-commit хук установлен** (`.git/hooks/pre-commit`) и на КАЖДОМ коммите гоняет
  `just check`. Значит **коммитим ТОЛЬКО из PowerShell** (PATH refresh), иначе хук не
  найдёт `just`. pre-commit живёт в venv: `services\worker\.venv\Scripts\pre-commit.exe`.
- **Кодировка коммит-сообщений:** PowerShell 5.1 пайп (`$msg | git commit -F -`) бьёт
  кириллицу в `?????` + добавляет BOM. ПРАВИЛО: писать сообщение в файл (Write-tool,
  UTF-8 без BOM) и `git commit -F <файл>` — git читает байты напрямую. Например
  `services/worker/tmp/COMMIT_MSG.txt` (gitignored).
- **codegen-цепочка для anti-drift:** title-поля из pydantic-схемы СРЕЗАЮТСЯ в
  `export_schema.py` (`_strip_titles`) — иначе json2ts плодит мусорные алиасы и коллизии.
  Менять контракт → только `app/models.py`, потом `just types`.
- Enum'ы в TS становятся union-типами (`type ClipType = "hook" | ...`), не TS-enum —
  совместимо с Next SWC `isolatedModules`.

### Грабли инструментов (B)
- **PowerShell-инструмент ДЕРЖИТ cwd между вызовами** и сейчас он на `services\worker`
  (не на корне!). Относительные пути в PowerShell удваивались (`services\worker\services\worker\...`)
  и тихо промахивались (Remove-Item «удалил» несуществующее → ложное «removed»).
  ПРАВИЛО: в PowerShell всегда **абсолютные пути** (или Set-Location на абсолютный путь
  в начале). Bash-инструмент cwd НЕ держит — там `cd` в каждой команде.
- **ffmpeg/ffprobe НЕ на PATH Bash-инструмента** (winget после старта сессии). Любые
  прогоны пайплайна, дёргающие ffmpeg/ffprobe/yt-dlp, — через PowerShell с registry
  PATH refresh + `uv run` (он пробрасывает PATH и venv-скрипты в subprocess).
- Лимит источника 90 мин в `stage0_import._check_limits` работает (JobError). Тестовый
  ролик должен быть в пределах лимита, иначе meta.json не пишется (гейт раньше записи).

### Грабли инструментов (C)
- **`deepgram-sdk` 7.3.1 = генерёный клиент** (куча `...V1`, Agent-API), классического
  `DeepgramClient.listen.rest` нет. Решение: зовём стабильный REST `/v1/listen` через
  **httpx** напрямую (`stage1_transcribe.call_deepgram`). Провайдер-абстракция цела,
  фикстуры снимать проще. deepgram-sdk пока висит в депах неиспользуемым — можно убрать.
- **smart_format=true раздувает ответ:** добавляет `paragraphs`, дублирующие ВСЕ слова
  (15-словная фикстура была 225KB!). Для golden-фикстуры выкидываем `alt["paragraphs"]`
  и тримим metadata → 3.6KB.
- **config.py:** `.env` читается по АБСОЛЮТНОМУ пути (`parents[3]/.env`), т.к. воркер
  гоняется из `services/worker` (cwd ≠ корень). `get_settings()` ленив+кэширован —
  валидация ключа при первом вызове (не при импорте), чтобы unit-тесты жили без ключей.
- Deepgram Nova pre-recorded ≈ **$0.0043/мин** (~$0.258/час). Наш 33-мин ролик ≈ $0.14.
- **Внешние сервисы задокументированы:** `docs/EXTERNAL_SERVICES.md` (что/где/чем свапнуть).

### Решение по LLM (этап D): Gemini вместо Anthropic
- У фаундера НЕТ Anthropic-ключа → этап D на **Gemini** (план это разрешает: LLM swappable).
- SDK: **`google-genai` 2.8.0** (`from google import genai`). Авторитетно (интроспекция,
  НЕ веб-пересказ — он переврал форму):
  ```python
  from google import genai
  from google.genai import types
  client = genai.Client(api_key=GEMINI_API_KEY)
  resp = client.models.generate_content(
      model="gemini-2.5-pro",
      contents=user_prompt,
      config=types.GenerateContentConfig(
          system_instruction=SYSTEM_PROMPT,
          response_mime_type="application/json",
          response_schema=SEGMENTS_SCHEMA,            # dict JSON-schema или pydantic
          thinking_config=types.ThinkingConfig(thinking_level="high"),
      ),
  )
  raw = resp.text            # сырой JSON; resp.parsed — типизировано; resp.usage_metadata — токены
  ```
- Модели 2026: gemini-3.1-pro-preview, gemini-3.5-flash, gemini-3.1-flash-lite,
  **gemini-2.5-pro** (дефолт, stable, deep reasoning), gemini-2.5-flash(-lite).
- score НЕ ограничиваем в схеме (Gemini может игнорить min/max) → клиппим в постобработке (D2).
- Ключ в `.env`: `GEMINI_API_KEY`, `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-2.5-pro`.