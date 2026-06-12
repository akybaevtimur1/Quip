# CLAUDE.md — правила работы над ClipFlow

> 🚀 **НОВАЯ СЕССИЯ — читай `docs/HANDOFF.md` ПЕРВЫМ** (состояние, как запустить, граблии,
> что делать дальше — всё сжато). Затем — этот файл (правила + журнал) и план ниже.

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
11. **Фронт ОБЯЗАН закладывать задержки бэка.** Пайплайн долгий (мин). Никакого
    блокирующего UI: polling статуса, степпер стадий, таймер elapsed, скелетоны,
    дизейбл двойного сабмита, таймаут+ретрай на сетевых сбоях, понятные состояния
    (queued/processing/done/failed/empty). Это требование на этапы I/J.
12. **Маржа/экономика — первоклассно.** Cost/latency на стадию → `runs.jsonl` (H1);
    сравнение моделей и юнит-экономика/маржа → `docs/BENCHMARKS.md` (живая таблица,
    дополнять на КАЖДОМ прогоне новой модели). Доминанта cost = транскрипция.

> Доки: план — `CLIPFLOW_DEV_PLAN.md`; сервисы/свапы — `docs/EXTERNAL_SERVICES.md`;
> бенчмарки скорость/стоимость/качество — `docs/BENCHMARKS.md`.

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
- [x] **E1** — Reframe 9:16: `app/pipeline/stage3_reframe.py`. PURE (compute_crop_window,
      aggregate_center=медиана) — 12 тестов. I/O: кадры через ffmpeg (AV1), лица MediaPipe
      **Tasks API**. Реальный прогон sample01 seg0: face_found=True, crop x=880/608×1080,
      9:16±1px, в границах; превью подтвердил лица в рамке. DoD зелёный. 2026-06-07.
      ⚠️ sample01 мультиспикер (R1) → широкий кадр ожидаемо; single-speaker кадрировался бы плотнее.
- [x] **F1** — Субтитры ASS: `app/pipeline/stage4_captions.py`, всё PURE — 15 тестов.
      `to_clip_time` (R3, t_clip=t_source−seg.start), group_words (≤5, разрыв на .?!/пауза>0.4/
      >2.5с), build_ass (Montserrat 90, контур 6, MarginV 260, .upper()). Реальный прогон
      sample01 seg0: 50 слов→17 реплик, первая 0:00:00.00, последняя=длина клипа. DoD зелёный. 2026-06-07.
      💡 Тюнинг-кандидат: на быстрой речи бывают 1-словные чанки (мин-слов-перед-разрывом).
- [x] **G1** — Cut+Encode: `app/pipeline/stage5_render.py`. PURE build_vf/build_ffmpeg_cmd —
      5 тестов. Один проход ffmpeg: -ss ДО -i (PTS→0, синк субтитров R3) + -t, crop→scale
      1080×1920→setpts→subtitles, libx264 crf20/aac. Реальный рендер sample01 clip_01:
      h264 1080×1920, aac, 20.85с, 3.81с рендер. DoD зелёный. 2026-06-07.
      ⚠️ Спот-чек поймал: `WrapStyle: 2` резал длинные субтитры краями → исправил на
      `WrapStyle: 0` (авто-перенос) в stage4. Превью подтвердило перенос в 2 строки.
- [x] **H1** — `app/run.py` склейка Stage 0→5 + `job.json` (wire-контракт) + `runs.jsonl`.
      Кэш по наличию (source/transcript/segments) → повторы не платят Deepgram/Gemini.
      `just e2e sample01`: 5 клипов, 64с, ttfc 15.4с, job.json валиден. STOP-GATE 3 пройден. 2026-06-07.
- [x] **I1/I2/I3** — Минимальный web. Палитра **№1 Warm Charcoal+Coral** (выбрана фаундером
      из 4 превью; тёмная, не дженерик). Tailwind v4 `@theme` (свап палитры — 1 блок
      globals.css). Шрифты Unbounded/Onest/IBM Plex Mono. Типы из `@clipflow/shared`
      (`import type`, runtime-импорта нет → transpilePackages не нужен). lib (api/useJob
      polling 2.5с/3-фейла/effect-based, format) + мок-воркер (/api/mock, прогресс по времени).
      Компоненты: SourceForm/JobProgress(степпер+таймер+скелетоны)/ClipCard/ClipGrid/
      ReasonChip/StatusBadge/ErrorPanel. page.tsx state-машина idle→tracking→done→error.
      `next build` зелёный, `just check` зелёный. Мок-флоу idle→done проверен скриншотами. 2026-06-07.
      ⚠️ Контракт: `Job.clips`/`metrics`/`error` ОПЦИОНАЛЬНЫ в TS (pydantic default → не required
      в JSON-схеме) → на фронте `job.clips ?? []`. Скилл `ui-ux-pro-max` использован для направления.
- [x] **J1** — worker REST+SQLite: `app/db.py`(+pure row_to_wire, 3 теста), `app/tasks.py`
      (фон+статус), `app/main.py` (POST/GET/healthz, CORS :3000, StaticFiles /media). Коммит `6fa3b46`. 2026-06-07.
- [x] **J2** — РЕАЛЬНЫЙ прогон через UI: вставил EDCwQe7P8T0 → прогресс → 3 живых 9:16-клипа
      из воркера (/media), субтитры/reason/score/Download, CORS ок. $0.16, 74.7с. GET из SQLite
      `done`/3 clips, mp4 HTTP 200. ГЛАВНЫЙ ГЕЙТ UI пройден. 2026-06-07.
      ✅✅ **PHASE 0 ЗАВЕРШЁН (A→J).**
      ⚠️ Находка: `language="en"` захардкожен в stage1. Русское/немо-видео (мото-трип
      l5Rzsv8qDOM) → ~5 слов → 0 клипов → корректно сработал empty-state «Нечего нарезать»
      (НЕ баг — неподходящий контент). На будущее: detect_language / конфиг языка; кэш
      транскрипции по hash(source) (R6) чтобы повторные прогоны не платили.

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
- **MediaPipe 0.10.35 выпилил `mp.solutions`** (легаси). Используем **Tasks API**
  (`mediapipe.tasks.python.vision.FaceDetector`), модель `.tflite` качается в кэш
  `app/assets/` (gitignored `*.tflite`) из storage.googleapis.com. bounding_box в Tasks —
  в ПИКСЕЛЯХ (делим на ширину кадра), а не в долях, как было в легаси.
- Кадры для детекта берём через **ffmpeg** (декодит AV1), НЕ `cv2.VideoCapture`
  (бандл-ffmpeg opencv может не уметь AV1). mypy: overrides `ignore_missing_imports`
  для `cv2`/`mediapipe` (нет строгих стабов).
- **Внешние сервисы задокументированы:** `docs/EXTERNAL_SERVICES.md` (что/где/чем свапнуть).

### Пост-Phase-0 улучшения (по запросу фаундера)
- **Reframe AUTO** (первый вариант): `decide_reframe_mode` + `build_vf_fit`. reframe_<clip>.json
  был `{mode, crop}` (одно значение на весь сегмент).
  ⛔ **ПОЛНОСТЬЮ ЗАМЕНЕНО R1** (per-shot модель, см. R1-секции ниже). `decide_reframe_mode`,
  `build_vf_fit`, `build_vf_fill`, `build_ffmpeg_cmd`, `shot_centers`, `detect_cuts` (основной путь)
  — все УДАЛЕНЫ. `reframe_<clip>.json` теперь `{shots:[{t0,t1,mode,center}…]}`.
  Текущий код: `stage3_reframe.py` (pure) + `stage5_render.py` (один проход).
- **Промпт вынесен в файл:** `services/worker/prompts/select_moments.v1.txt` (крутить без
  кода); `stage2_select.load_system_prompt()` грузит его, fallback — `DEFAULT_SYSTEM_PROMPT`.

### Итерация качества (после Phase 0, по фидбеку фаундера; gate «сначала качество»)
- **K3 авто-язык СДЕЛАН рано** (RU не работал на en): Deepgram `detect_language` (язык=None),
  `transcript.language`=detected. Коммит `9af07ec`. Comedy01 (RU, Щербаков) → 7949 слов.
- **Больше кандидатов:** `max_clips=8` (config) + промпт «surface ALL strong, до N» + cap top-N
  по score в postprocess. Коммит `b8e078d`. comedy01: было 2 → стало 8 клипов.
- **eval-харнесс:** `app/eval.py` (рубрика C1–C8, Q) + `docs/EVAL.md`. Коммит `358054d`.
- **План Phase 1 (K1 RQ-очередь) написан, исполнение ОТЛОЖЕНО** (выбрали «сначала качество»):
  `docs/superpowers/specs/2026-06-07-phase1-reliability-design.md` + `.../plans/...k1-queue.md`.
- **D — dynamic reframe (окно едет за лицом) СДЕЛАН.** Коммит `dabcdf6`. Трек кейфреймов
  вместо одного static-окна: `smooth_track` (PURE) = скользящее среднее (гасит дрожь) +
  dead-zone (статика → 1 окно, без дёрганья) + кап; `build_crop_x_expr`/`build_vf_dynamic`
  (PURE) = кусочно-линейное x(t) ffmpeg-выражение, `setpts` ПЕРВЫМ (crop видит клип-время
  0-based), запятые экранированы `\,` для filtergraph. render_clip: 1 окно→static build_vf,
  >1→динамика. +14 unit-тестов. Проверено comedy01 ($0, кэш): clip_01 kf=12 x 591→1020→632
  (span 429px), кадры t=2/4/14 — разный кадр с лицом; clip_06/08 kf=1 (без дрожи).
  ⚠️ Тюнинг-кандидаты: на жёстких склейках источника окно ПЛАВНО панит между планами
  (в идеале — мгновенный скачок на cut; детект склеек = Phase 1+). Бимодальный кадр
  (2 спикера) → MA усредняет к центру между ними (как и старая медиана). Кнобы:
  `smooth_track(win, dead_zone, max_keyframes)`, `sample_face_centers(fps)`.
- **D2 — наведение ПЕРЕДЕЛАНО на cut-aware «держим план + режем на склейке»** (фидбек
  фаундера: плавный пан «плавал/укачивал» на быстро-монтажном многокамерном шоу). Жёсткая
  проверка показала: clip_01 = 11 склеек за 21с, окно ехало путём 1739px при размахе 429px,
  в движении 96% времени. НОВАЯ модель: `detect_cuts` (ffmpeg scene, thr 0.3, клип-relative) →
  `build_shots` (PURE) интервалы планов → `shot_centers` (PURE, медиана лиц/план; нет лица →
  держим предыдущий) → ОДНО окно на план; `build_crop_x_step_expr` (PURE) = СТУПЕНЬКА (held
  внутри плана, мгновенный скачок на склейке) вместо линейной интерполяции. Удалены
  `smooth_track`/`build_crop_x_expr`. Проверено comedy01 ($0, кэш): clip_01 12 планов, 0px
  движения внутри плана, 8 скачков ТОЛЬКО на склейках; кадры t=14/17 (один план) — одинаковый
  кроп (держим), t=11 (др. план) — другой (скачок). +тесты build_shots/shot_centers/step_expr.
  ⚠️ thr=0.3 иногда ПРОПУСКАЕТ склейку (в clip_01 ~t15-16 контент сменился внутри «плана» →
  окно держит старый кадр). Кноб: `detect_cuts(threshold=)`. Active-speaker (кто говорит, а не
  крупнейшее лицо) — Phase 1+.
- **C — clean-start СДЕЛАН** (баг «Антимошенника»). `snap_start_index` теперь 3-уровневый,
  backward-first: (1) предыдущее слово завершило предложение → старт чистый (СОХРАНЯЕМ
  короткие хуки); (2) назад к началу текущего предложения; (3) если оно недостижимо назад →
  старт в ХВОСТЕ → уходим ВПЕРЁД к началу следующего предложения. +2 unit-теста.
  Доказано на реальном comedy01 (детерминированно, $0): clip_01 был idx127 «антимошенника.»
  (t=64.0) → стал idx128 «Сегодня у меня в гостях…» (t=66.0). Чистый старт предложения.
  ⚠️ Кэш: comedy01/segments.json хранит СТАРЫЙ снэп — новый снэп применяется при свежем
  select (перегенерация ниже / новые прогоны).
- **B — курирование в UI СДЕЛАН.** (1) Выбор количества: степпер −/+ (1–10, дефолт 6) в
  SourceForm → `max_clips` в POST /jobs (CreateJobBody, Field ge=1 le=10) → run_pipeline →
  select_segments. PURE `resolve_max_clips(requested, default, lo, hi)` (None→дефолт, кламп) —
  +4 теста. (2) Курирование: чекбокс на каждом ClipCard (selected→рамка-акцент, снят→приглушён),
  ClipGrid — стейт выбора (по умолчанию ВСЕ выбраны; `key={job.id}` сбрасывает на новый прогон,
  без эффектов), бар «Выбрано N из M» + «Выбрать/Снять все» + «Скачать выбранные (N)»
  (последовательные скачивания). just check + next build зелёные. Проверено скриншотами (mock):
  степпер в форме; грид с чекбоксами; снятый клип приглушается, счётчик/кнопки обновляются.
- **Active-speaker reframe (наведение на ГОВОРЯЩЕГО) — СДЕЛАН за флагом** (фидбек: «почти норм,
  но следить надо за нужным человеком»; ресёрч готовых решений). Спайк (BENCHMARKS §6): репо
  LR-ASD как есть = 170с/15с-клип на CPU (узкое место — S3FD 22.5M, 129с); наш MediaPipe-детект
  в ~42× быстрее → lean-путь 15с/15с-клип. Модель ASD 0.84M (вендорена в `app/asd/_vendor`, MIT).
  Инкременты: (1) вендоринг ядра + `app/asd/scorer.py` (ленивый torch, опц. группа `asd`);
  (2) PURE `build_tracks` (IOU, numpy) + `pick_speaker_centers` (argmax speak/план) +8 тестов;
  (3) `app/pipeline/asd_reframe.speaker_windows` (MediaPipe@25fps→tracks→crop+ASD→центр) за
  флагом `REFRAME_SPEAKER` (off→largest-face D2; torch не нужен). Коммиты `5f1011f`/`70f02b1`/`7e1690b`.
  Прогон comedy01 (флаг on, $0): 5 клипов ~374с (~2× длительности на CPU), трек ≠ largest-face,
  кадры — лицо в центре. Послал фаундеру на оценку. ⚠️ ОТКРЫТО: качество «тот ли человек» —
  судит фаундер визуально; `reframe_speaker_crop_scale=0.55` тюним под MediaPipe-кропы (модель
  обучена на S3FD; score сжат). Воркер на :8000 по умолчанию БЕЗ флага (UI-прогоны = largest-face).

### R1 — Reframe 2.0 (per-shot), СДЕЛАН 2026-06-08 (флеши by-design убраны)
Главная боль фаундера: «флеши» (смена кропа мимо склейки на кадр) + b-roll режется узким
слайсом («трава вместо широко»). Корень в коде: (1) сырой ffmpeg scene-порог; (2) кроп
ВЫРАЖЕНИЕМ ВО ВРЕМЕНИ `crop=…:if(lt(t,T),x0,x1)` — T-float не попадает на PTS кадра-склейки;
(3) режим fill/fit решался ОДИН раз на сегмент. Переписано на **per-shot** (как Opus/Vizard):
- **R1.1** `352284c` — PySceneDetect ContentDetector (frame-accurate) вместо ffmpeg-порога.
  pure `scenes_to_clip_cuts` (офсет −start) + I/O `detect_scene_cuts`. ⚠️ scenedetect НЕ был в
  депах (доки врали) → добавлен в БАЗОВЫЕ; шкала порога ~27 (НЕ ffmpeg 0..1). comedy01 clip_01:
  14 склеек vs 8 у ffmpeg@0.4.
- **R1.2** `29460ad` — pure `build_shot_plan` + `ShotPlan`: режим РЕШАЕТСЯ НА ШОТ (лицо→fill+центр;
  нет лица→fit широко).
- **R1.3a** `1019d40` — pure-билдеры: `build_vf_fill`/`build_vf_fit_shot` (без субтитров),
  `build_concat_list`/`build_concat_burn_cmd`, `merge_shot_plan` (слить равные планы: статика→1
  кодировка, tolerance=dead_zone сравн. с ДЕРЖИМЫМ центром), `windows_to_shot_plan` (speaker-адаптер).
- **R1.3b** `d234b92` — `render_clip`/`reframe_segment`/`run.py` ПЕРЕПИСАНЫ на per-shot: каждый
  план = отдельный ffmpeg-сегмент (cut + static-crop|fit-blur) → concat-демуксер → burn субтитров
  2-м проходом (не рвутся на границе шота). Удалён time-expr (`build_vf_dynamic`/`build_crop_x_step_expr`).
  config `reframe_scene_threshold`/`reframe_min_scene_sec`. reframe_<clip>.json → {shots:[…]}.
- **DoD** ✅: comedy01 (5 валидных mp4 1080×1920, длительности сходятся, temp вычищены, clip_01
  5 fit-шотов из 11 vs 0 раньше). Comedians-in-Cars 300–330с (13 склеек): fit-перебивки широко
  (t=17 пейзаж целиком), reframe следит за говорящим (Обама 0.35 / Сайнфелд 0.74), граница
  t=21.655 чистая (нет кадра-флеша). Скрины фаундеру. 150 unit-тестов, just check зелёный.
- ⚠️ Грабли: `uv sync` (без `--extra asd`) УДАЛЯЕТ torch → mypy падает на `app/asd/scorer.py`
  (subclass nn.Module=Any). Держать `uv sync --extra asd`. Comedians целиком через UI не прогнан —
  Deepgram 408 SLOW_UPLOAD (upload 37МБ wav, сетевое); reframe тестился напрямую (`tmp/test_reframe_comedians.py`).
- ⚠️ Тюнинг-кандидаты (фаундер судит по скринам): короткие fit-перебивки могут быть ложными
  (детект-промах лица на быстром плане) → `reframe_min_scene_sec`/`reframe_scene_threshold`;
  speaker-путь ещё на ffmpeg detect_cuts (R1 перевёл только largest-face путь).

### R1b — «широко vs тайт» по геометрии лиц + УРОК про воркер, 2026-06-08 (`e8437e6`)
Фаундер протестил R1 на новом видео (Kanye/Elon дипфейк) → «слишком близко / не тот человек /
нет широкого вида / полная хуйня». РАЗБОР (systematic-debugging):
- **Корень «не видно изменений» = воркер не перезапущен** (uvicorn без --reload, старт 11:06,
  R1-коммиты 13:57+). Фаундер тестил ДО-R1 код. Доказано: reframe-json его джоба старого формата
  `{mode,crop}`. Урок в HANDOFF §3 (⚠️ перезапускать воркер после правок). Воркер перезапущен.
- **Старый код реально плох** на этом видео: одно статичное окно largest-face на весь сегмент →
  clip_01 чёрный кадр (окно на тёмной пустоте), clip_04 затылок (не говорящий). Новый per-shot
  трекает лицо по склейкам → лицо в кадре (показал before/after).
- **Но fit включался только при ОТСУТСТВИИ лиц** → видео с лицами всегда тайт-fill. Фикс R1b:
  `sample_faces` (ВСЕ лица кадра: cx+ширина) + pure `shot_is_wide` (2+ разнесённых лица, размах >
  ширины 9:16 → широко) + `build_shot_plan` по геометрии (нет лиц→fit; разнесённые→fit; одно/
  кластер→fill на крупнейшем). Удалён мёртвый shot_centers/decide_reframe_mode. 157 тестов.
- **Продуктовые решения фаундера** (AskUserQuestion): 2 человека → широко обоих (fit, не active-
  speaker); одиночка → full-bleed БЕЗ блюр-рамок. ⚠️ Физика: close-up на 16:9 + full-bleed = тайт
  (fill = полная высота = минимальный зум full-bleed; меньше зума без рамок нельзя). MEDIUM-режим
  (кроп шире лица + лёгкие рамки, как OpusClip) прототипирован и ПОКАЗАН, но фаундер выбрал
  full-bleed → не внедрял. Если «слишком близко» останется болью — вернуться к MEDIUM (нужны рамки).
- ⚠️ Находки: двойные субтитры (видео с вшитыми субтитрами → жжём поверх); 2-face-wide НЕ
  срабатывает, когда второй человек затылком/в профиль (MediaPipe видит 1 лицо) — частый кейс интервью.

### R1c — ОДИН проход рендера (фикс флешей + ПОДЛАГА АУДИО), 2026-06-08 (`91fbc14`)
Фаундер: флеши/чёрные кадры на переходах ВСЁ ЕЩЁ есть + ПОДЛАГ ЗВУКА на стыках (видео с многими
склейками). «Вдруг у нас тупое решение». Да — было тупое. Разбор (systematic-debugging, покадрово
на его видео): per-shot рендер (R1.3b) резал клип на N ОТДЕЛЬНЫХ ФАЙЛОВ + concat-демуксер. ДВА бага:
- **АУДИО**: каждый AAC-сегмент при склейке добавляет priming → на 13 стыках +0.25с (clip_02 аудио
  31.82 vs 31.57) = рассинхрон/подлаг. (ffprobe duration — быстрый детектор.)
- **ЧЁРНЫЙ КАДР**: реальная склейка на кадре 645, старт клипа на ДРОБНОМ кадре 594.12 → кроп
  переключался на 1 кадр мимо → 1 кадр НОВЫЙ контент со СТАРЫМ кропом (тёмный край) = «флеш».
  (Доказано: непрерывный single-crop рендер того же сегмента — БЕЗ чёрного; source-склейка чистая.)
Решение — ОДИН проход декода (stage5 переписан): аудио непрерывным `-map 0:a` (НЕ режем → ноль
подлагов); видео `[0:v]split=N` → per-shot `trim=start_frame:end_frame` (frame-exact) + crop/fit +
`setsar=1` (иначе concat падает: fill/fit разный SAR) → `concat`-фильтр (стыкует декодир. кадры, нет
дыр → нет чёрных). Старт `-ss` ВЫРОВНЕН на границу кадра (round(seg_start*fps)/fps) → trim-кадры =
реальные склейки. Выпилены build_vf_fill/_fit_shot/concat_list/concat_burn_cmd/ffmpeg_cmd. +билдеры
build_reframe_filter/build_single_pass_cmd (10 тестов). Рендер ~2.5× быстрее (нет двойной кодировки).
- Грабли: (1) fit-лейблы `[bg][fg]` ГЛОБАЛЬНЫ в filtergraph → уникализировать по шоту `[bg{i}]`,
  иначе коллизия на 2+ fit. (2) concat-фильтр требует одинаковый SAR → `setsar=1` на каждом сегменте.
- ⚠️ ОТКРЫТО: ждём вердикт фаундера (флеши/звук ушли?). Двойные субтитры — отдельно.

### R1d — анти-флеш (короткие шоты держат кадр), 2026-06-08 (`f6bd15c`)
Фаундер: флеши ВСЁ ЕЩЁ есть. Разбор (покадрово comedy01): R1c убрал чёрные кадры/подлаг, но
осталось рапидное чередование fill↔fit на КОРОТКИХ шотах (0.43/0.66/0.76с) + скачки центра →
кадр мигал тайт-кроп↔весь-кадр-в-рамках каждые ~0.5с. Фикс — pure `stabilize_plan(min_hold_sec)`:
шот короче min_hold (дефолт 1.5с) НЕ переключает кадр, ПОГЛОЩАЕТСЯ предыдущим (держим mode+center).
В reframe_segment после merge: `merge(stabilize(plan))`. config `reframe_min_hold_sec`. +5 тестов.
Доказано: comedy01 clip_01 11 шотов(5 fit)→5(1 fit); зона t=4.5-9.7 раньше мигала, стала стабильной
(скрин tmp/flash_ba.png). 156 тестов зелёные.
- **Дизайн след. захода зафиксирован** (brainstorming + AskUserQuestion, фаундер выбрал «сначала
  флеши», потом «тот человек»): гибрид — детект ЛЮДЕЙ (тело, НЕ лицо: фронтальный=главный, влезает
  целиком) + Gemini для спорных «широко vs фокус»/«кто главный»; держать фокус per shot, БЕЗ зума
  (чистый вертикальный кроп), широко=fit-рамки только для существенных планов. См. этот журнал.

### V2 Continuous Reframe, 2026-06-09 (`5b59f2e`) → **ЗАМЕНЁН** cut-aligned path
Был написан как «замена R1» (EMA непрерывного слежения вместо per-shot). Два движка A/B.
Главная идея: `smooth_centers(alpha=0.15)` непрерывно сглаживает cx лица; `classify_frame` на
каждый 5fps-сэмпл → `build_trajectory` → `build_regions` группирует consecutive-mode регионы.
Проблема вскрылась сразу: границы режима падают на сетку 5fps (кратно 0.2с), не совпадая со
склейками → флеш при каждом fill↔fit переходе. V2 НИГДЕ в production не вызывается (основной путь
в `reframe_segment` переключён на cut-aligned — см. ниже). Функции `build_trajectory`/`build_regions`
оставлены для обратной совместимости (legacy). Engine A/B рендер — оба живы и рабочие.

### Flash Fix — Cut-Aligned Reframe, 2026-06-09 (коммиты `35e7f4d`…`5659e5b`)
**Проблема диагностирована** Opus-планнером на реальном кэше `comedy01`: V2-граница `fill→fit`
стояла на t=11.6с (сетка 0.2), ближайшая склейка — t=10.44с, рассинхрон **+29 кадров**. В окне
±1с склеек нет вообще. Доказательство: `tmp/proof_montage.png` (6 кадров до/после 11.6 — непрерывный
план, никаких склеек). Решение: как у Google AutoFlip / OpusClip — режим **один раз на план**.

**Новые PURE-функции в `stage3_reframe.py`:**
- `samples_in_shot(raw, t0, t1)` — фильтр сэмплов в полуинтервал [t0,t1). Тривиальная, но явная.
- `decide_shot_mode(shot_samples, *, crop_w_frac, mode_setting, wide_ratio=0.5)` — majority-vote
  `classify_frame` по плану → `"fill"` / `"fit"`. mode_setting override. Нет сэмплов → fit.
- `build_shot_trajectory(shot_samples, smoothing)` — EMA cx внутри плана; **init = первый реальный
  cx** (не 0.5 — ключевой фикс: старый код давал пан от центра в начале каждого плана).
- `build_regions_from_shots(shots, raw, ...)` — собирает `TrackRegion` по планам + `merge_short_regions`.
  Граница региона = граница плана = реальная склейка → флеш физически невозможен.

**Изменения в `reframe_segment`:** старый `build_trajectory → build_regions` заменён на
`detect_cuts → build_shots → build_regions_from_shots`. Новый config-кноб `REFRAME_WIDE_RATIO=0.5`.
`run.py` пробрасывает `wide_ratio=s.reframe_wide_ratio`.

**Верификация:** `tmp/verify_newregions.py` → все 3 границы режима comedy01/clip_01: Δ = **0 кадров**.

**180 unit-тестов** (было 167), `just check` зелёный.

**⚠️ GATED Task 6** — плавный zoom-переход (~0.3с) для intra-shot wide-reveal. Делать только
после вердикта фаундера «основные флеши ушли». Plan in `docs/superpowers/plans/2026-06-09-reframe-cut-snap-flash-fix.md`.

### Editor v3 — ночная автономная сессия (ветка feat/editor-v3), 2026-06-13
Запрос фаундера: «редактор выглядит уебански → сделать как в нормальных редакторах,
финальный вид, до готового»; ответы (AskUserQuestion): страница (возврат безупречный),
AI-карта полная, split авто+вручную, субтитры всё. Спека+план в docs/superpowers.
- **Сначала**: main запушен (на remote была развилка с **youtube-куками в коммите 59d07b4** —
  смержена без кук; ⚠️ куки в истории GitHub → фаундеру перевыпустить). Доки спасены.
- **Бэкенд**: Chapter/ChaptersData + CropOverride.center_b + HighlightStyle.animation
  (контракты → just types); общая retry-обёртка `call_gemini_structured` (select+chapters);
  `editor/chapters.py` (postprocess PURE + Gemini + кэш) + `GET /chapters` (pending→фон→done);
  анимации слов pop/bounce (`word_animation_tags`, \t от начала СТРОКИ, animation="none"
  отключает караоке целиком — primary остаётся цветом текста); 12 пресетов (E–L);
  **split**: `_split_pair` (ровно 2 трека покрытием ≥60% шота) в plan_regions (границы
  регионов НЕ двигаются — инвариант цел), `_region_chain` (общий fit/fill/split для обоих
  билдеров, лейблы [pa{i}][pb{i}]), points_b по всему пути, ручной override center+center_b,
  mode="auto" снимает override; fontsdir в subtitles-фильтре.
- **Фронт**: страница `/edit/[jobId]/[clipId]` (прямой URL работает; ‹ › клипы; возврат
  `/?job=`), PreviewPlayer (свои контролы: скраб клипа, fullscreen НА КОНТЕЙНЕРЕ),
  он-видео правка (клик=textarea на месте; драг по Y=позиция с гайдом), табы Субтитры/
  Стиль(12 пресетов+кастомизация)/Кадр(Авто/Тайт/Широко/Split), TimelineV2 (полоса глав+
  зум/пан), модалка и старый TimelineEditor удалены.
- **🔑 «Worker error: {}» РАСКРЫТ** (живой дебаг, перехват ErrorEvent): (1) октопус грузит
  fallback-шрифт `default.woff2` РЯДОМ С ВОРКЕРОМ — не хостился → воркер падал → ТИХИЙ
  CSS-фолбэк (фаундер никогда не видел libass!); фикс fallbackFont=Montserrat.ttf.
  (2) video-режим позиционирует канвас по object-CONTAIN геометрии, у нас cover →
  канвас 342×192 мимо кадра; фикс: **canvas-режим** (свой канвас на весь 9:16 контейнер,
  ResizeObserver+resize(), время вручную setCurrentTime в rAF). Бонус: смена интервала
  не пересоздаёт WASM.
- **Кодген-грабля**: `_strip_titles` в export_schema удалял ПОЛЕ модели с именем "title"
  (Chapter.title пропал из TS) — внутри "properties" ключи теперь не зачищаются + тест.
- **Шрифты**: Unbounded/Rubik (+Montserrat) в public/libass/fonts И services/worker/fonts;
  ffmpeg `subtitles=:fontsdir=` относительным путём (без экранирования C:).
- **DoD**: just check 297 тестов зелёный; next build зелёный; fps-grid Δ=0.00000
  (tmp/verify_grid_fix.py, ⚠️ нужен PYTHONIOENCODING=utf-8 на Windows-консоли);
  split-рендер напрямую: 1080×1920, кадр=два стэка-кропа (tmp/split_frame.png);
  e2e живьём: libass рисует (канвас 342×610), пресет Hormozi применился live, рендер
  из UI → mp4 с зелёным караоке (tmp/render_styled.png), возврат восстановил грид,
  AI-карта comedy01 = 16 реальных глав. Скрины tmp/editor_v3_*.png.
- ⚠️ Открыто: split кликом в UI не проверен глазами (бэкенд доказан); полировка вида —
  вердикт фаундера; PowerShell-консоль cp1251 душит Δ-печать (utf-8 env).

### Editor v3 — фиксы по живому фидбеку фаундера (та же ночь, `8370d4e` + `5352bff`)
Фаундер тестил параллельно. Три волны фидбека → корни и фиксы:
- **«Субтитры дёргаются / слово прыгает на 2-ю строку»**: (а) \fscx в анимациях менял
  ШИРИНУ строки → libass перепереносил её на каждом кадре → анимации стали только
  вертикальными (\fscy118 pop / 115-96-100 bounce) + тест-запрет \fscx; (б) \t в ASS
  действует на ВЕСЬ последующий текст → анимация 1-го слова дёргала всю строку, у
  следующих «не работала» → каждый блок сбрасывает \fscy100 перед своим \t (стандарт
  караоке-шаблонов). +тест на сброс.
- **Нестабильный драг интервала**: refetchAfter стал атомарным (analysis+ASS до
  setState одним батчем — убрано окно «старый ASS с новым оффсетом», мигали не те
  слова); refreshAss секвенсирован (seq-токен); TimelineV2 блокирует новый драг пока
  сохраняется предыдущий (блок «сохраняю…» + pulse).
- **Правки на ходу** (видео играет, юзер кликает): ВСЕ мутации субтитров (PATCH стиль/
  цвет/анимация/текст + apply-preset) — через единую очередь промисов (editRef со
  свежей версией на момент исполнения) → больше никаких 409 → reload. PresetStrip
  переведён на onApply-проп (сам не зовёт API). Стресс при воспроизведении: 4 пресета
  + 2 анимации подряд → 0 конфликтов, версия монотонна.
- **«Дефолт жёлтый, а не оранжевый»**: default_caption_track брал HighlightStyle()
  (#FFE000) вместо пресета A → теперь style+highlight из seed preset_a (коралл
  #FF5A3D, box). Фолбэки фронта приведены. Старые жёлтые edit-стейты comedy01
  смигрированы apply-preset'ом (нетронутые: clip_01 Hormozi, clip_04 уже коралл).
- **Индикатор «Правки не в рендере»**: dirty-стейт на всех мутациях → жёлтый чип в
  хедере + точка на кнопке Рендер (тултип «превью уже показывает, файл старый»);
  сбрасывается на render done. LibassLayer rAF-синк затроттлен до 30Гц (targetFps 24).
- Гейт: 298 тестов, tsc/eslint зелёные. Ветка смержена в main по запросу фаундера.

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

### Editor Core (MVP) — СДЕЛАН 2026-06-09 (E0→E6)
Не-деструктивный редактор поверх batch-пайплайна. ClipEdit = SourceInterval[] + CaptionTrack + CropOverride[].
Новый пакет `app/editor/`: timemap, replies, defaults, ops, reframe_cache, captions_v2, store, presets.
REST-эндпоинты: GET/PATCH /edit, trim/add-section/extend/crop/render/analysis, presets.
Мульти-интервальный рендер: `render_timeline` → asplit→atrim→concat в filtergraph (нет AAC priming).
Ленивое создание edit-state на первый GET (нет эагерной связи run.py→БД).
Optimistic-lock: version mismatch → HTTP 409.
Доказано E6: comedy01/clip_01 trim→2 интервала, expected=19.77s video=19.76s audio=19.78s render=9.88s.
Правки = $0 (нет Deepgram/Gemini). 218 unit-тестов, just check зелёный.

### Reframe v3 — единый ASD-путь + DoD Δ=0, 2026-06-10 (коммиты `76e5132`…`9a14660`)
**Задача**: убрать флеши окончательно + всегда следить за ГОВОРЯЩИМ (не largest-face).
Итерации R1–R1d убрали большинство флешей, но использовали ffmpeg scene-порог (float, не frame-
accurate) и форк `if reframe_speaker:` — два отдельных пути с разными багами.

**Архитектурные изменения:**
- **torch/ASD → базовые зависимости** (был `[project.optional-dependencies] asd` → `uv sync` без
  флага удалял torch → ASD молча не работал). Теперь `uv sync` без флагов = рабочий ASD.
- **face_fps=25.0** (было 5.0). LR-ASD обучена на 4:1 audio/video (25fps видео). При 5fps модель
  даёт случайные speak-score → fallback на largest-face. Фикс в config.py.
- **SpeakerTrack** dataclass: f0/f1 (кадры), cx (tuple центров по кадрам), width, speak (mean ASD).
  Заменяет CropWindow — содержит всю инфу для планировщика.
- **score_tracks_in_segment** (`asd_reframe.py`) → `list[SpeakerTrack]` вместо `list[CropWindow]|None`.
- **build_shots_frames** (PURE) — кадры-склейки из PySceneDetect → список интервалов `(f0, f1)`.
  Целые числа на всём пути: PySceneDetect → `trim=start_frame=` в ffmpeg — float-округление исключено.
- **plan_regions** (PURE) — единый планировщик: ASD score → говорящий/largest-face; геометрия →
  fill/fit; границы = реальные кадры-склейки. Нет форка `if reframe_speaker:`.
- **Жёсткий cut** (stage5): xfade между fill/fit удалён (`build_smooth_filter`, `build_timeline_filter`).
  Кроссфейд тайт↔широкий сам был zoom-вспышкой.
- **Мёртвый код удалён**: ShotPlan, aggregate_center, build_trajectory, build_regions,
  shot_plan_to_regions, windows_to_shot_plan, pick_speaker_centers, apply_dead_zone.
- **Windows file-lock**: PySceneDetect держит lock на temp .mp4 → `vid.capture.release()` перед
  выходом из TemporaryDirectory.

**DoD — `tmp/dod_reframe_direct.py`** (без Deepgram/Gemini, прямо на 3 сегментах dod01):
- seg_A (60–180с): 30 склеек → 28 регионов, 27 границ — все Δ=0 ✅
- seg_B (300–420с): 15 склеек → 15 регионов, 14 границ — все Δ=0 ✅
- seg_C (600–720с): 26 склеек → 24 региона, 23 границы — все Δ=0 ✅
- **ИТОГО: 64 границы режима, max Δ = 0 кадров** → флеш физически невозможен.

`just check` зелёный (все unit-тесты + mypy + ruff + tsc + anti-drift).

⚠️ Грабли: Deepgram WriteTimeout на длинных видео (>30мин, WAV >80МБ).
`httpx.post()` с дефолтным write_timeout=5с не успевает загрузить. Нужно `write=None` (без таймаута)
или `httpx.Client(timeout=httpx.Timeout(connect=10, write=None, read=300, pool=10))` в stage1.
Это фикс на следующую сессию (DoD dod01 обойдён прямым reframe-тестом без транскрипции).

### Ночь лаунч-MVP (ветка `feat/mvp-launch`), 2026-06-13 — scope T1–T6 (LAUNCH_BRIEF)
Автономная ночь: довести ядро до продаваемого MVP. Отвёл `feat/mvp-launch` от HEAD main.

- **T1/T2 — хук (топ-текст) + богатый reasoning. СДЕЛАНО** (коммиты `0aa94c6`, `c6a4368`).
  Объяснимость = наш отличитель vs Vizard. **Решение хранения хука: `CaptionTrack.hook:
  HookOverlay`** (бриф разрешал top-overlay в CaptionTrack) — даёт ОГРОМНУЮ экономию: хук
  компилится в ТОТ ЖЕ ASS, что субтитры → `compile_ass(track)` читает `track.hook` →
  автоматом в libass-превью (`/ass`) И ffmpeg-экспорте (`render_edit_to_file` →
  `write_caption_ass`), БЕЗ новых эндпоинтов/threading; фронтовый `patchCaptions` (PATCH
  всего captions) уже персистит хук; `apply_preset` сохраняет hook (трогает только style/
  highlight). PURE `build_hook_event` (TDD) = ASS top-event (alignment 8, окно весь клип|
  первые N сек, бренд-плашка). Gemini-схема `_LlmSegment` + промпт расширены `hook`/
  `why_works`; `postprocess` пробрасывает (старый raw → None, обратная совместимость).
  Модель: `HookOverlay` + `Segment/ClipOut.hook/why_works` (опц. → старый кэш валиден),
  `just types`. Фронт: таб «Хук» (текст/вкл/весь-клип|первые-N), `ClipCard` структурный
  reasoning (хук + «Почему сработает» + уверенность), мок-роут демонстрирует.
  **Грабля (найдена реальным рендером):** libass `BorderStyle=3` (opaque box) заливает
  плашку цветом **OutlineColour**, НЕ BackColour → `box_color` в OutlineColour (с альфой).
  **DoD:** `tmp/dod_hook.py` — реальный ffmpeg-mp4: хук «ВОТ ПОЧЕМУ ВСЕ МОЛЧАТ» коралл-
  плашка сверху, субтитры снизу, не пересекаются (`tmp/hook_dod_frame.png`, послан фаундеру).
  `just check` зелёный, +25 тестов (test_hook.py + postprocess passthrough).
  ⚠️ `clip_kind` из брифа НЕ добавлял отдельным полем — у нас уже `type: ClipType`
  (hook/emotional_peak/complete_thought/strong_quote) = clip_kind; не плодлю таксономию.
  ⚠️ Локально НЕТ кэша comedy01/sample01 (data/ gitignored, не синхронизирован) → DoD на
  синтетическом тёмном источнике (изолирует именно прожиг хука; шрифт/ASS/ffmpeg реальные).

- **T3 — сочные субтитры (keyword-highlight). СДЕЛАНО** (коммит `7da8cfb`). PURE
  `pick_keyword_positions` (числа + длинные контентные ≥6 букв, без стоп-слов; до 2/реплику —
  иначе «подсвечено всё»). compile_ass: явные emphasis_refs > авто-keyword (emphasis_color +
  emphasis_auto) > пусто. Модель `CaptionStyle.emphasis_auto`. Пресет «Поп-слова» (preset_m,
  коралл-emphasis без караоке) + контрол в StyleTab. DoD `tmp/dod_emphasis.py`: реальный mp4
  «Я ЗАРАБОТАЛ 1000000 РУБЛЕЙ» — keyword'ы [1,2] коралл, остальные белые (tmp/emph_dod_frame.png).
  **Эмодзи descope:** libass color-emoji ненадёжен между wasm-превью и ffmpeg → сломал бы WYSIWYG
  (hard-констрейнт). Нужен NotoColorEmoji в оба места + кросс-стек верификация — follow-up.
- **T4 — баги §0.1. ЧАСТИЧНО** (коммит `73113e3`). #4 scale: `highlight.scale` вертикальным
  \fscy-папом активного слова (без \fscx → без реврапа); ⚠️ per-word `box` НЕ реализуем в
  libass (нет примитива фона под спан) — задокументировано. #9 retry глав: GET /chapters?retry=true
  + кнопка «Повторить» (failed→pending). #8 двойные субтитры: `CaptionTrack.burn` (False →
  compile_ass без нижних реплик, хук остаётся) + тогл в CaptionsTab — НАДЁЖНЫЙ ручной тогл
  вместо хрупкого CV-автодетекта. #2 (превью-кадр после драга) ПРОПУЩЕН — косметика (финальный
  рендер корректен; нужен live-reframe эндпоинт). +6 тестов.
- **T5 — соотношения сторон 9:16/1:1/4:5/16:9. СДЕЛАНО** (коммит `7d598a7`). ⛔ ЧИСТО
  пространственно: temporal-сетка (cuts/shots/regions/trim) НЕ ТРОНУТА → Δ=0 инвариант цел
  по построению (флеши не вернулись). PURE `aspect_to_dims` + `fill_crop_dims` (height-limited
  портрет = слежение; width-limited ландшафт = полный кадр). compile_ass(play_w,play_h): PlayRes
  ASS = размеры выхода — ИНАЧЕ libass анаморфно растянет субтитры. out_w/out_h через
  render_clip/render_timeline; POST /edit/aspect; селектор в FrameTab + динамич. аспект превью.
  Регионы (cx) переносятся — reframe НЕ пересчитывается. DoD `tmp/dod_aspect.py`: ffprobe всех 4
  верны (1080x1920/1080x1080/1080x1350/1920x1080), субтитры не растянуты (tmp/aspect_1_1.png,
  aspect_16_9.png). +10 тестов. ⚠️ Engine B (не дефолт) fill остаётся 9:16; split+16:9 вырожден.
- **T6 — прайсинг/лимиты + Supabase-ready. СДЕЛАНО** (коммит `94c0f38`). БЕЗ секретов/аккаунтов.
  `app/billing.py` PURE: PLANS (free 2видео/20мин/watermark/720p; starter $12 20/200/1080;
  pro $29 100/1000/приоритет), check_quota (видео→минуты, честная RU-причина), resolve_plan
  (→free дефолт), current_month. Лимиты в КОДЕ (не БД). `db.py` usage-адаптер record_usage/
  get_monthly_usage (SQLite, тот же интерфейс → Postgres). `migrations/0001_init_billing.sql`:
  profiles/jobs/usage_events + RLS (TO authenticated + ownership; UPDATE USING+WITH CHECK;
  триггер handle_new_user search_path=''; план/usage пишет ТОЛЬКО сервер). `docs/SUPABASE_SETUP.md`
  — что вписать фаундеру (ключи + куда, 🔴 service_role не в NEXT_PUBLIC, гейт квоты, вебхук
  Lemon→plan). +14 тестов. Провод auth/квоты/оплаты — follow-up (нужны секреты).

> ✅ **ИТОГ НОЧИ T1–T6:** все шесть задач закрыты (T4 частично: #4 scale без box, #2 пропущен).
> just check зелёный (388 тестов). 7 коммитов на `feat/mvp-launch`. Отчёт — docs/OVERNIGHT_REPORT_2026-06-13.md.