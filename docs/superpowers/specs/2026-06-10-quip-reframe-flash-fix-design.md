# Дизайн: Quip reframe — единый cut-aligned планировщик (0 флешей + наведение на говорящего)

Дата: 2026-06-10
Статус: согласован (brainstorming), ожидает review перед planning

## Контекст и проблема

Главная боль фаундера и Quip MVP-брифа: **видимые артефакты перехода («флеши»)** при смене
кадрирования вертикаль↔горизонталь, плюс кадр не всегда на нужном (говорящем) человеке.

Сверка брифа с РЕАЛЬНЫМ кодом (не журналом — журнал местами устарел) показала: архитектурно
пайплайн уже почти идентичен брифу. Двухпроходка (`reframe_segment` → `reframe_<clip>.json` →
детерминированный `render_clip`), решение-раз-на-шот (`decide_shot_mode`), буферизация шота,
debounce (`merge_short_regions`), EMA-сглаживание, letterbox для широких — всё уже есть.

Расходимся с брифом в **3 узких местах**, и ровно они дают флеши/«не тот человек»:

1. **Склейки не frame-accurate.** Главный путь детектит склейки ffmpeg scene-threshold
   (`detect_cuts`, thr 0.4), а не PySceneDetect. Журнал утверждает обратное, но `scenedetect`
   нет ни в коде, ни в `pyproject.toml`. Граница режима не попадает на кадр склейки → флеш.
2. **xfade-пластырь.** Последний коммит добавил `xfade=fade` 150мс на fill↔fit. Кроссфейд
   тайт↔широкий сам читается как зум-вспышка; 150мс > рекомендации брифа 80–120мс.
3. **Наведение на largest-face, не на говорящего.** Главный путь = крупнейшее лицо. ASD
   (active-speaker) есть, но за флагом `REFRAME_SPEAKER` и тоже на ffmpeg-склейках.

Корень флешей механический: если граница региона (смена fill↔fit + xfade) не лежит на
покадровой склейке источника — переход происходит посреди непрерывного плана и виден глазу.

## Решение (Подход 1: единый cut-aligned планировщик)

Сливаем два пути (largest-face и ASD) в ОДИН. Закрываем все 3 гэпа одним дизайном.

### Принцип единицы времени
Склейка **рождается как номер кадра** (PySceneDetect) и живёт номером кадра до самого
`trim=start_frame=` в рендере. Ни одного float-округления между детектом и рендером →
рассинхрон границы режима и склейки = **0 кадров by construction**.

### Pass 1 — анализ (offline), `reframe_segment` переписан

```
detect_scene_cuts(video, start, end)   # PySceneDetect ContentDetector → [номера кадров]
build_shots_frames(cuts, total_frames) # [(f0, f1)] в КАДРАХ (PURE)
score_tracks_in_segment(video, seg)    # MediaPipe@25 → дорожки + ASD-скор на дорожку (I/O)
plan_regions(shots, tracks, fps, knobs)# PURE — решение на шот ↓
merge_short_regions(regions, min_hold) # debounce
→ write reframe_<clip>.json; return regions
```

`plan_regions`, на каждый шот:
```
active = дорожки, пересекающие шот
если shot_is_wide(active)              → TrackRegion(fit)            # 2+ разнесённых → letterbox
иначе:
   target = argmax speak_score(active)
   если speak_score(target) < speak_threshold:
      target = largest_face(active)                                 # ASD молчит → фолбэк (без флага)
   points = smooth(cx(target) внутри шота)                          # EMA-пан или статика
   → TrackRegion(fill, points)
```

Границы регионов = границы шотов = кадры реальных склеек → смена fill↔fit и сброс пана только
на склейке → флеш невозможен.

### Pass 2 — рендер, `stage5_render` упрощён

- `_chain_video_segs`: удалить ветку `xfade`, оставить только попарный `concat=n=2` (**жёсткий
  cut**). Убрать параметр `xfade_dur` из `_chain_video_segs` / `build_smooth_filter` /
  `build_timeline_filter`.
- На границе-склейке жёсткий cut невидим: контент источника там и так прыгает.
- Один проход ffmpeg, аудио непрерывным `-map 0:a` (нулевой подлаг — уже решено R1c). `setsar=1`
  оставляем (concat требует одинаковый SAR). Engine A дефолт; Engine B (cv2) не трогаем.

## Карта модулей

| Файл | Изменение |
|---|---|
| `app/pipeline/stage3_reframe.py` | Новый I/O `detect_scene_cuts` (PySceneDetect → кадры). Новые PURE `build_shots_frames` + **сердцевина `plan_regions(...) → list[TrackRegion]`** (fit-широкий / fill-говорящий / фолбэк largest-face / траектория) — рядом с `TrackRegion`, чтобы избежать циклического импорта. `reframe_segment` на единый путь. Удалить ffmpeg `detect_cuts`, форк `speaker`, legacy `build_trajectory`/`build_regions`. |
| `app/pipeline/stage3_speaker.py` (PURE) | ASD-специфичная чистая математика (`build_tracks`, `pick_speaker_centers`, `apply_dead_zone` — уже есть). При надобности — хелперы выбора говорящего/largest-face per shot (возвращают индексы/cx, НЕ `TrackRegion`). |
| `app/pipeline/asd_reframe.py` (I/O) | Рефактор `speaker_windows` → `score_tracks_in_segment`: возвращает данные (дорожки + ASD-скоры + геометрия), не готовые окна. |
| `app/pipeline/stage5_render.py` | Убрать xfade-ветку → только `concat`. Тоже в `build_timeline_filter`. |
| `app/config.py` | Убрать `reframe_speaker`, `reframe_cut_threshold`, xfade-кноб. Добавить `reframe_scene_threshold` (~27), `reframe_speak_threshold`. |
| `pyproject.toml` | `torch`/`scipy`/`python_speech_features`: optional `asd` → базовые депы (ASD по дефолту; убирает грабли «uv sync удаляет torch»). Вернуть `scenedetect` в базовые. |
| `app/run.py` | Снять проброс удалённых флагов. |

## Тюнинг-рычаги (config, дефолты + калибровка фаундером)

- `reframe_speak_threshold` — порог уверенности ASD, ниже → держим largest-face. Рычаг «тот
  человек vs безопасный кадр».
- `reframe_wide_ratio` — когда 2 лица = «широко/letterbox», а когда фокус на одном.
- `reframe_scene_threshold` (~27) — чувствительность детекта склеек.

Дефолты в коде; финальная калибровка — за фаундером на реальных прогонах (визуальный суд).

## Границы (PURE / I/O)

- PURE (unit-тесты): `build_shots_frames`, `plan_regions`, `shot_is_wide`, траектория,
  `merge_short_regions`, билдеры фильтров рендера.
- I/O (обёртки, JobError №8): `detect_scene_cuts`, `score_tracks_in_segment`, запуск ffmpeg.

## Тестирование

**Unit (тест-первым, правило №3):**
- `build_shots_frames` — границы из кадров-склеек (пусто/крайние/дубликаты).
- `plan_regions` — широкий→fit; один говорящий→fill на нём; ASD молчит→фолбэк largest-face;
  смена говорящего между шотами; debounce коротких.
- `_chain_video_segs` — assert: подстроки `xfade` НЕТ, только `concat`; цепочка N≥3.
- Снести/переписать тесты на `xfade` и старый `detect_cuts`.

**DoD (реальный прогон, доказательство показываем, правило №4):**
- Тестовое видео: talking-head подкаст/интервью 1–2 спикера, статичные планы — **фаундер даёт
  ссылку/файл** (comedy01 — стресс-кейс, не цель брифа).
- Каждая граница режима Δ = 0 кадров до ближайшей склейки (скрипт верификации).
- Покадровый монтаж до/после каждой смены плана → 0 видимых флешей.
- Кадр на говорящем (не largest-face) — визуальная проверка скринами.
- Субтитры ±80мс; `just check` зелёный.

## Вне скоупа (осознанно отложено)

- Pyannote-диаризация (ASD решает «кто говорит» визуально без неё).
- Замена Deepgram→WhisperX, Gemini-выбор моментов — к флешам/«тому человеку» отношения нет,
  выкинуло бы оплаченную инфру.
- Бренд-шаблоны, b-roll, мультистиль субтитров, f-cam — Phase 1+.
- GATED Task 6 (плавный intra-shot zoom-reveal) из прошлого flash-fix плана — только после
  вердикта «основные флеши ушли».

## Риски

- PySceneDetect на AV1-в-mp4 (YouTube): проверить, что декодит (ffmpeg-бэкенд PySceneDetect).
  Если нет — фолбэк на покадровый ffmpeg-extract (уже умеем) + детект на PNG.
- torch в базовых депах раздувает образ воркера (CPU-колёса). Принято фаундером (CPU, ASD on).
- Многокамерный рапид-монтаж (comedy01) остаётся трудным — короткие шоты debounce-ятся; это
  ожидаемо и не блокирует talking-head DoD.
