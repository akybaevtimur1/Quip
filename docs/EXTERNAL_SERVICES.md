# Внешние сервисы и зависимости ClipFlow

Здесь — все СТОРОННИЕ сервисы/API, которые трогает проект: зачем, где, сколько стоит,
и **на что можно свапнуть**. Цель — чтобы было видно точки замены провайдеров.

> Принцип проекта: каждый платный провайдер изолирован за интерфейсом (одна функция/
> модуль), переключение — через env (`*_PROVIDER`/`*_MODEL`) без правок downstream.

## Активные (Phase 0)

| Сервис | Где / зачем | Тип | Env / ключ | Стоимость | Чем свапнуть |
|---|---|---|---|---|---|
| **YouTube + yt-dlp** | Stage 0 import: скачать ролик | инструмент (free) | — | $0 | file-upload (всегда доступен), любой другой загрузчик |
| **FFmpeg / FFprobe** | Stage 0/5: аудио 16k, ffprobe meta, cut+encode | локальный бинарь (free) | — | $0 | — (стандарт; альтернатив для Phase 0 не нужно) |
| **Deepgram** (Nova) | Stage 1: транскрипция word-level | платный API | `DEEPGRAM_API_KEY`, `TRANSCRIPTION_PROVIDER=deepgram` | ~$0.0043/мин (~$0.258/час) | **AssemblyAI** (тот же интерфейс), self-host **WhisperX** (ради маржи) |
| **LLM** (Google Gemini) | Stage 2 select + хуки + chat-agent: structured output | платный API | `GEMINI_API_KEY` | зависит от модели | **swappable** концептуально: Gemini ↔ Anthropic ↔ OpenAI. Сейчас → **Gemini, запинён на `gemini-2.5-flash`** (`config.pin_llm_model` коэрсит любой `*-latest`/`gemini-3*` в пин; fallback chat → `gemini-2.5-flash-lite`). Anthropic/OpenAI — потенциальная замена, НЕ подключены |
| **MediaPipe** (Face Detection) | Stage 3: reframe 9:16 (детект лица) | локальная либа Google (free) | — | $0 | center-crop fallback; др. детекторы лица; Pyannote для 2+ спикеров (позже) |
| **GitHub** | хостинг репо `Varenik-vkusny/Quip` (private) | dev-инфра | `gh` auth | free | GitLab/любой git-хостинг |

## Инфраструктура (ЖИВАЯ в проде)

> Всё ниже отгружено и работает в проде. Детали реальности/деплоя — `docs/README.md` (источник правды).

| Сервис | Где / зачем | Статус | Чем свапнуть |
|---|---|---|---|
| **Cloudflare R2** | хранение клипов/артефактов, CDN `cdn.quip.ink` | **LIVE** (`storage.py` put/get/url; >100MB → multipart) | S3, Backblaze B2 (тот же интерфейс) |
| **Modal** `quip-worker` | хостинг воркера (web + run/upload/render/reframe/preview джобы + Cron cleanup) | **LIVE** — заменил Railway | Railway/Fly.io/Render (+GPU для self-host ML) |
| **Vercel** `quip-app` | хостинг web (`apps/web`), автодеплой на push в `main` | **LIVE** | Netlify, Cloudflare Pages |
| **Supabase** | Postgres (проект `qiagetbnsssvbiowuxpp`) + Auth, миграции 0001–0014 | **LIVE** | Neon + любой auth |
| **Polar** | биллинг (планы + PAYG-кредиты, webhook `POST /webhooks/polar`) | **LIVE** — заменил Stripe | Paddle, Stripe, LemonSqueezy |

## Заметки по свапу LLM (Stage 2)
- Контракт ответа модели — JSON Schema (см. план §4.2): `segments[]` с
  `{start_word_index, end_word_index, reason, score, type}`. Любой провайдер обязан
  поддержать structured output / JSON-schema-режим — тогда downstream не меняется.
- Изоляция: вся работа с LLM живёт в `app/pipeline/stage2_select.py` + ключ/модель из
  `app/config.py`. Свап провайдера = новая ветка по `LLM_PROVIDER` + правильный SDK-вызов.
