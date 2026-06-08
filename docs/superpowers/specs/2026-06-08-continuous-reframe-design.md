# Continuous Reframe V2 — Design Spec
**Date:** 2026-06-08  
**Status:** Approved  
**Replaces:** R1 per-shot model (PySceneDetect + ShotPlan)

---

## Problem

R1 per-shot reframe has two root failures:

1. **Wrong person** — режим и центр фиксируются на ВЕСЬ шот (медиана лиц за 2fps). Если лицо
   движется или меняется в середине шота — камера не реагирует.
2. **Flash на fill↔fit** — короткие шоты (0.4–0.8с) вызывают рапидное чередование режимов
   даже после R1d `stabilize_plan`. Корень: дискретное shot-based решение.

Прототип (AI-Youtube-Shorts-Generator local/clipper.py) решает оба через **непрерывное
покадровое следование**: exponential smoothing (0.15) + крупнейшее лицо per-frame. Мы
адаптируем эту идею с нашей инфраструктурой (MediaPipe вместо Haar, ffmpeg-рендер).

---

## Goals

- Плавное непрерывное следование за лицом (как прототип), без shot-based решений
- Умный fit-слой: нет лиц → широкий экран; 2+ разнесённых → широкий; кластер/одно → тайт
- Два движка рендера (A и B) для бенчмарка скорости vs качества
- Документация + бенчмарки в BENCHMARKS.md

## Non-Goals

- ASD speaker-режим (остаётся на старом ShotPlan, не трогаем)
- Изменение stage0–2, stage4, web UI, worker
- Замена MediaPipe на Haar cascade

---

## Architecture

```
reframe_segment(video, start, end)
        │
        ▼
sample_faces_continuous(fps=5.0)     ← ffmpeg кадры + MediaPipe Tasks API
        │ list[(t, [(cx, w_frac), ...])]
        ▼
build_trajectory(smoothing=0.15)     ← smooth + classify_frame per sample
        │ list[TrackPoint(t, mode, cx)]
        ▼
build_regions(min_hold_sec=1.5)      ← группировка + merge_short_regions
        │ list[TrackRegion(t0, t1, mode, points)]
        ▼
reframe_<clip_id>.json               ← {regions: [...]}
        │
        ├──► Engine A: build_smooth_filter()   ← ffmpeg if()-expression per fill-регион
        │              build_single_pass_cmd() ← ОДИН проход, аудио -map 0:a
        │
        └──► Engine B: render_frame_by_frame() ← cv2.VideoCapture → pipe → ffmpeg
                       (pipe raw BGR → ffmpeg stdin + аудио + субтитры)
```

---

## Data Types

### TrackPoint
```python
@dataclass(frozen=True)
class TrackPoint:
    t: float        # клип-относительные секунды (0-based)
    mode: str       # "fill" | "fit"
    cx: float | None  # fill: центр X (доля кадра); fit: None
```

### TrackRegion
```python
@dataclass(frozen=True)
class TrackRegion:
    t0: float
    t1: float
    mode: str                          # "fill" | "fit"
    points: tuple[TrackPoint, ...]     # tuple (не list) — frozen dataclass. fill-регионы:
                                       # cx значимые; fit-регионы: пустой tuple.
```

### JSON-контракт (reframe_<clip>.json)
```json
{
  "regions": [
    {"t0": 0.0, "t1": 4.2, "mode": "fill", "points": [
      {"t": 0.0, "mode": "fill", "cx": 0.52},
      {"t": 0.2, "mode": "fill", "cx": 0.53},
      ...
    ]},
    {"t0": 4.2, "t1": 6.8, "mode": "fit",  "points": []},
    ...
  ]
}
```

**Обратная совместимость:** `ShotPlan` остаётся в models.py для ASD-пути (speaker=True).
`TrackPoint`/`TrackRegion` добавляются рядом. `just types` перегенерирует TS.

---

## Stage 3 — Pure Functions

### `smooth_centers(samples, smoothing=0.15) → list[float | None]`
Exponential smoothing по оси X как у прототипа. Вход: список `cx | None` (None = нет лица).
Нет лица → держим последний сглаженный центр (или 0.5 если ни одного ещё не было).

```
cx_smooth[i] = cx_smooth[i-1] + smoothing * (cx_raw[i] - cx_smooth[i-1])
```

### `classify_frame(all_faces, crop_w_frac) → "fill" | "fit"`
Переиспользует `shot_is_wide` логику на уровне одного кадра:
- `not all_faces` → `"fit"`
- `shot_is_wide([[cx for cx,_ in all_faces]], crop_w_frac=crop_w_frac)` → `"fit"`
- иначе → `"fill"` (крупнейшее лицо)

### `build_trajectory(raw_samples, smoothing, crop_w_frac) → list[TrackPoint]`
Для каждого сэмпла: classify → cx_raw (крупнейшее лицо или None) → smooth_centers → `TrackPoint`.

### `build_regions(trajectory, min_hold_sec) → list[TrackRegion]`
1. Группируем consecutive одинакового mode в регионы
2. `merge_short_regions`: регион < `min_hold_sec` поглощается предыдущим (держим его mode)
3. Возвращаем финальные регионы с их point-траекторией

### `merge_short_regions(regions, min_hold_sec) → list[TrackRegion]`
Аналог `stabilize_plan` но на уровне регионов, не шотов. Поглощает с предыдущим.

---

## Stage 5 — Engine A (ffmpeg expression)

### `build_fill_crop_expr(points, t0_offset, src_w, src_h) → str`
Строит piecewise-constant if()-выражение для ffmpeg `crop` X-координаты.
`t` в выражении — PTS-STARTPTS (0-based после trim), поэтому `t_expr = t - t0`.

```
if(lt(t,0.20),312,if(lt(t,0.40),315,...,320))
```

Запятые экранируются `\,` для filtergraph (как в существующем коде fit-лейблов).

### `build_smooth_filter(regions, src_w, src_h, fps, ass_name) → str`
filter_complex строка:
```
[0:v]setpts=PTS-STARTPTS,split=N[a0][a1]...;
[a{i}]trim=start_frame=F0:end_frame=F1,setpts=PTS-STARTPTS,
  {fill: crop=W:H:EXPR:0,scale=1080:1920:flags=lanczos |
   fit:  split=2[bg{i}][fg{i}];...overlay...},setsar=1[s{i}];
[s0][s1]...concat=n=N:v=1[cv];[cv]subtitles=ASS[outv]
```

### `build_single_pass_cmd(...)` — без изменений (уже в R1c)

---

## Stage 5 — Engine B (cv2 pipe)

### `render_frame_by_frame(source, aligned_start, dur, regions, src_w, src_h, fps, ass_name, out_name, data_dir)`

1. `cv2.VideoCapture(source)` → seek к `aligned_start`
2. Для каждого кадра по номеру:
   - `t = frame_idx / fps`
   - Находим активный регион по `t`
   - **fill**: интерполируем `cx` между ближайшими TrackPoint (линейно), `compute_crop_window` → `x0`; вырезаем `frame[0:src_h, x0:x0+crop_w]`; scale 1080×1920
   - **fit**: scale весь кадр 1080×1920 + gblur overlay (через отдельный cv2-паст или ffmpeg-сегмент)
   - Пишем кадр в subprocess-пайп ffmpeg (`-f rawvideo -pix_fmt bgr24 -s WxH -r fps -i pipe:0`)
3. ffmpeg получает raw-видео по stdin, аудио из source (`-i source`), жжёт субтитры (`-vf subtitles=ASS`)
4. Выходной кодек: libx264 crf 20 (не mp4v — важно для сравнения качества в бенчмарке)

**Fit-регионы в Engine B**: для каждого fit-кадра: `cv2.resize(frame, (1080, 1920))` (background,
stretch) + `cv2.GaussianBlur(bg, (blur_k, blur_k), 0)` + `cv2.resize(frame, fit_size)` (foreground,
letterbox) + overlay по центру (numpy slice). Всё в Python, нет второго ffmpeg-процесса.

---

## Benchmark Harness (`app/benchmark.py`)

```python
def benchmark_engines(
    video: Path, clip_id: str, start: float, end: float, *,
    regions: list[TrackRegion], src_w: int, src_h: int, fps: float,
    ass_name: str, data_dir: Path,
) -> dict
```

Прогоняет A и B на одном сегменте, измеряет:
- `render_sec` — wall-clock
- `file_size_mb` — размер выходного mp4
- `fps_render` — кадров/с рендера

Выводит сравнительную таблицу в консоль и дописывает строку в `docs/BENCHMARKS.md §7`:
```
| 2026-06-08 | comedy01/clip_01 | A | 3.2s | 8.1 MB | 95 fps |
| 2026-06-08 | comedy01/clip_01 | B | 41s  | 8.3 MB | 7 fps  |
```

---

## Configuration Knobs

| Переменная | Дефолт | Описание |
|------------|--------|----------|
| `REFRAME_ENGINE` | `A` | `A` = ffmpeg expression; `B` = cv2 pipe |
| `REFRAME_FACE_FPS` | `5.0` | Сэмплирование лиц (выше = точнее, медленнее) |
| `REFRAME_SMOOTHING` | `0.15` | Exponential smoothing коэф (0=без; 1=no smooth) |
| `REFRAME_MIN_HOLD_SEC` | `1.5` | Мин. длина региона (анти-мигание) |
| `REFRAME_DEAD_ZONE` | `0.12` | Не используется в V2 (удалён) |
| `REFRAME_SCENE_THRESHOLD` | — | Удалён (PySceneDetect выпилен) |

---

## What's Removed

- `PySceneDetect` / `detect_scene_cuts` / `scenes_to_clip_cuts`
- `build_shots` / `build_shot_plan` / `stabilize_plan` / `merge_shot_plan`
- `ShotPlan` (остаётся только для ASD-пути)
- `REFRAME_SCENE_THRESHOLD`, `REFRAME_MIN_SCENE_SEC`, `REFRAME_DEAD_ZONE` из config
- `detect_cuts` (ffmpeg scene-detect обёртка) — не нужна

---

## What's Kept

- `sample_faces` → переименовывается в `sample_faces_continuous` + выше fps
- `compute_crop_window`, `aggregate_center`, `shot_is_wide` — переиспользуются
- ASD-путь (`speaker=True`, `stage3_speaker.py`, `asd_reframe.py`) — не трогаем
- `build_reframe_filter` в stage5 → переписывается для TrackRegion (Engine A)
- `build_single_pass_cmd`, `_run_ffmpeg`, `render_clip` — сохраняются

---

## Test Plan

**Unit (pure-функции):**
- `smooth_centers`: smoothing=0 → pass-through; нет лиц → держит последний; первый кадр без лица → 0.5
- `classify_frame`: нет лиц → fit; 2 разнесённых → fit; одно лицо → fill
- `build_trajectory`: корректная последовательность mode+cx
- `merge_short_regions`: короткий регион < 1.5с поглощается; длинный остаётся
- `build_fill_crop_expr`: правильный if() для N точек; запятые экранированы

**Integration (реальный видеофайл):**
- Engine A: ffmpeg --version + прогон comedy01/clip_01 → mp4 1080×1920, аудио в sync
- Engine B: аналогично
- Benchmark: оба прогнаны, BENCHMARKS.md дополнен

---

## Documentation

- `docs/REFRAME_V2.md` — архитектурная документация, data flow диаграмма, параметры, как выбрать engine
- HANDOFF.md §2 обновляется: R1 → V2 статус
- BENCHMARKS.md §7 — новый раздел Engine A vs B
