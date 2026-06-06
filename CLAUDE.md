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
- [ ] **A6** — `justfile` + `models.py` (источник типов) + codegen контракта; `just check` зелёный.
- [ ] **B1/B2** — Import: yt-dlp + аудио 16k mono + meta.json.
- [ ] **C1** — Транскрипция Deepgram → transcript.json (секунды).
- [ ] **D1/D2** — Выбор моментов (Claude, structured output) + пост-обработка → segments.json. ГЛАВНЫЙ GATE КАЧЕСТВА.
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