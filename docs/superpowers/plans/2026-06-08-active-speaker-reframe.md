# Active-speaker reframe (LR-ASD) — план

**Цель:** кадрировать на ГОВОРЯЩЕЕ лицо (а не на самое крупное), сохранив cut-aware
модель D2 («держим план — скачок на склейке»). Поднимает нас с уровня Submagic
(largest-face) до уровня Opus Clip (active-speaker).

## Архитектурное решение (УТОЧНЕНО спайком 2026-06-08, см. BENCHMARKS §6)
Спайк показал: готовый S3FD-детектор LR-ASD = узкое место (129с/15с на CPU). Наш
**MediaPipe** делает детект в ~42× быстрее (3с). Поэтому НЕ вендорим S3FD — вендорим
ТОЛЬКО ядро ASD-модели (0.84M, ~376 строк, зависит лишь от torch) и кормим его НАШИМ
MediaPipe-детектом. Замер lean+MediaPipe: **15.3с/клип на CPU (~реалтайм)**.

Поток (FILL, флаг `REFRAME_SPEAKER=on`): извлечь кадры@25fps → MediaPipe-детект лиц
(быстро) → IOU-трекинг в дорожки → кроп лиц 112 in-memory + MFCC аудио → ASD-форвард →
speaking-score на дорожку. Поверх — наша cut-aware логика D2: на каждый план выбираем
дорожку с макс. speaking-score (argmax) → центр окна = её центр. Держим/скачок как D2.

**Вендорим (app/asd/):** model/Model.py, Encoder.py, Classifier.py, loss.py + вес
pretrain_AVA.model (3.4MB) из LR-ASD (MIT). Тонкий loader/scorer пишем сами (инференс-only,
без pandas/tqdm/sklearn/scenedetect/S3FD).

**Новые зависимости (опц. группа `asd`):** torch (CPU), python_speech_features. opencv +
mediapipe + numpy уже есть. scipy НЕ нужен (medfilt/interp заменяем numpy). Импорт torch —
ленивый; флаг off → torch не требуется.

**⚠️ Качество:** ASD обучена на S3FD-кропах; на MediaPipe-кропах score сжат (+0.1 vs +0.4).
Тюним: cropScale под MediaPipe + относительный argmax на план (нам нужен лишь «кто говорит
громче», не калибровка). Валидация — визуально на рендере. Fallback: S3FD@6fps (~48с/клип).

## Фазы

### Phase 0 — Спайк (валидация, БЕЗ интеграции)
Вендорим LR-ASD в `services/worker/vendor/lrasd`, ставим deps, гоняем его демо на ОДНОМ
клипе comedy01 на ЭТОЙ машине (Windows, CPU).
- **DoD:** реальный вывод модели на нашем клипе (кто говорит) + замер скорости (сек/клип)
  + формат выходных данных задокументирован.
- **Гейт:** если CPU неприемлемо медленно (напр. >30с/клип) → СТОП, обсуждаем fallback
  (Deepgram `diarize=true` + маппинг, или GPU-опция). Без угадывания.

### Phase 1 — pure-логика выбора спикера (TDD-first)
`pick_speaker_centers(tracks, shots, *, default=0.5) -> list[(shot_start, center_x)]`
(PURE): на каждый план выбрать дорожку с макс. speaking-score внутри плана → её центр;
нет говорящего в плане → держим предыдущий (как `shot_centers`).
- **DoD:** юнит-тесты на синтетических дорожках (один говорит — выбран он, не крупнейший;
  смена говорящего между планами; план без речи → carry-forward). pytest зелёный.

### Phase 2 — интеграция в stage3 (флаг)
Новый путь reframe за флагом `REFRAME_SPEAKER` (config, по умолчанию off → текущий
cut-aware largest-face, мгновенный откат). On → LR-ASD → дорожки+скоры →
`pick_speaker_centers` → окна (как D2, но центр = говорящий) → существующий рендер.
- **DoD:** `just check` зелёный; флаг off не меняет поведение (тесты D2 целы).

### Phase 3 — прогон + экономика + сравнение
comedy01 (кэш транскрипта; ASD добавит время) → клипы. Обновить `runs.jsonl` (латентность
ASD-стадии) + `docs/BENCHMARKS.md` (рост latency на клип — правило №12). Прислать фаундеру
до/после (largest-face vs active-speaker) на том же клипе.
- **DoD:** видео-сравнение + цифры latency/cost.

## Риски и fallback
- **CPU-скорость** — главный риск; Phase 0 спайк решает ДО интеграции.
- Если медленно: Deepgram `diarize=true` (аудио-спикер, уже платим за транскрипт) +
  маппинг спикер→лицо; либо GPU-опция; либо оставить cut-aware (флаг off).
- Откат мгновенный: `REFRAME_SPEAKER=off`.

## Не в скоупе (Phase 1+ дальше)
Плавное следование за лицом ВНУТРИ плана (сейчас держим центр плана); вертикаль/зум;
overlapped speech (двое говорят разом).
