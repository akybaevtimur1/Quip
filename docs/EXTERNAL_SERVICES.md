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
| **LLM (выбор моментов)** | Stage 2: выбор клипов, structured output | платный API | `LLM_PROVIDER`, `LLM_MODEL`, `*_API_KEY` | зависит от модели | **swappable**: Gemini ↔ Anthropic ↔ OpenAI. Сейчас → **Gemini** (нет Anthropic-ключа); план целился в Claude Opus 4.8 |
| **MediaPipe** (Face Detection) | Stage 3: reframe 9:16 (детект лица) | локальная либа Google (free) | — | $0 | center-crop fallback; др. детекторы лица; Pyannote для 2+ спикеров (позже) |
| **GitHub** | хостинг репо `Varenik-vkusny/clipflow` (private) | dev-инфра | `gh` auth | free | GitLab/любой git-хостинг |

## Отложенные (Phase 1+, пока НЕ подключены)

| Сервис | Зачем | Когда | Чем свапнуть |
|---|---|---|---|
| **Cloudflare R2** | хранение клипов/артефактов (вместо local-fs) | после GO-gate | S3, Backblaze B2 (интерфейс `storage.py` put/get/url) |
| **Railway** | хостинг воркера (REST + SQLite + диск) | деплой Phase 0/1 | Modal (+GPU для self-host ML), Fly.io, Render |
| **Vercel** | хостинг web (`apps/web`) | деплой | Netlify, Cloudflare Pages |
| **Supabase** (Postgres + Auth) | БД/аккаунты (вместо SQLite) | Phase 3 | Neon + любой auth |
| **Stripe** | оплата per-video | Phase 3 | Paddle, LemonSqueezy |

## Заметки по свапу LLM (Stage 2)
- Контракт ответа модели — JSON Schema (см. план §4.2): `segments[]` с
  `{start_word_index, end_word_index, reason, score, type}`. Любой провайдер обязан
  поддержать structured output / JSON-schema-режим — тогда downstream не меняется.
- Изоляция: вся работа с LLM живёт в `app/pipeline/stage2_select.py` + ключ/модель из
  `app/config.py`. Свап провайдера = новая ветка по `LLM_PROVIDER` + правильный SDK-вызов.
