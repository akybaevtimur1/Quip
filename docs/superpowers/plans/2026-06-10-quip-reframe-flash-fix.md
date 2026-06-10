# Quip Reframe — единый cut-aligned планировщик (0 флешей + говорящий) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать видимые артефакты перехода (флеши) при смене кадрирования вертикаль↔горизонталь и навести кадр на ГОВОРЯЩЕГО, слив largest-face и ASD пути в один cut-aligned планировщик.

**Architecture:** Двухпроходка. Pass 1 (`reframe_segment`): PySceneDetect → склейки как НОМЕРА КАДРОВ → шоты в кадрах → MediaPipe+ASD дорожки → pure `plan_regions` решает на каждый шот (fit-широкий / fill-говорящий / фолбэк largest-face) → `reframe_<clip>.json`. Pass 2 (`render_clip`): детерминированно применяет регионы, на границах шотов ЖЁСТКИЙ cut (xfade удалён). Граница режима = граница шота = кадр реальной склейки → флеш невозможен by construction.

**Tech Stack:** Python 3.12, pydantic, numpy, PySceneDetect (ContentDetector), MediaPipe Tasks FaceDetector, torch (LR-ASD, CPU), ffmpeg (libx264). Тесты: pytest. Гейт: `just check`.

**Глоссарий путей (все относительно корня репо `C:\Users\user\Desktop\ClipClow`):**
- Воркер-пакет: `services/worker/app/`
- Тесты: `services/worker/tests/unit/`
- Команды `uv`/`just`/`git` — из PowerShell с обновлением PATH (см. CLAUDE.md):
  ```powershell
  $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  ```
- pytest гоняем из `services/worker`: `uv run pytest tests/unit/<file>::<test> -v`
- Коммиты: сообщение в `services/worker/tmp/COMMIT_MSG.txt` (UTF-8, gitignored), `git commit -F`. Pre-commit гоняет `just check`.

---

## File Structure (что создаём/меняем)

| Файл | Ответственность | Действие |
|---|---|---|
| `services/worker/pyproject.toml` | депы | torch/scipy/python_speech_features → базовые; добавить `scenedetect` | Modify |
| `services/worker/app/pipeline/stage3_reframe.py` | reframe pure + I/O оркестратор | + `SpeakerTrack`, `build_shots_frames`, `plan_regions` (+хелперы), `detect_scene_cuts`; переписать `reframe_segment`; удалить мёртвое | Modify |
| `services/worker/app/pipeline/asd_reframe.py` | ASD I/O | `speaker_windows` → `score_tracks_in_segment` (возвращает `list[SpeakerTrack]`) | Modify |
| `services/worker/app/pipeline/stage5_render.py` | рендер | `_chain_video_segs` без xfade; `build_smooth_filter`/`build_timeline_filter` без `xfade_dur` | Modify |
| `services/worker/app/config.py` | кнобы | убрать `reframe_speaker`, `reframe_cut_threshold`; добавить `reframe_scene_threshold`, `reframe_speak_threshold` | Modify |
| `services/worker/app/run.py` | склейка | снять проброс удалённых флагов | Modify |
| `services/worker/tests/unit/test_stage3_reframe.py` | тесты reframe | + `build_shots_frames`, `plan_regions`; удалить тесты мёртвого | Modify |
| `services/worker/tests/unit/test_stage5_render.py` | тесты рендера | переписать xfade-тесты на hard-cut | Modify |
| `services/worker/tests/unit/test_timeline_filter.py` | тесты таймлайна | xfade-ассерт → concat | Modify |

---

## Task 1: Зависимости — ASD по дефолту + PySceneDetect

**Files:**
- Modify: `services/worker/pyproject.toml`

- [ ] **Step 1: Перенести asd-депы в базовые и добавить scenedetect**

В `pyproject.toml` блок `dependencies` (строки 7–19) — добавить три либы из `asd`-экстры и `scenedetect`. Итоговый `dependencies`:

```toml
dependencies = [
    "anthropic>=0.107.0",
    "deepgram-sdk>=7.3.1",
    "fastapi>=0.136.3",
    "google-genai>=2.8.0",
    "httpx>=0.28.1",
    "mediapipe>=0.10.35",
    "numpy>=2.4.6",
    "pydantic>=2.13.4",
    "pydantic-settings>=2.14.1",
    "scenedetect>=0.6.4",
    "scipy>=1.11",
    "python_speech_features>=0.6",
    "torch>=2.2",
    "uvicorn[standard]>=0.49.0",
    "yt-dlp>=2026.3.17",
]
```

Удалить блок `[project.optional-dependencies]` `asd = [...]` (строки 23–28) целиком — теперь они базовые. Комментарий про torch-CPU-колёса (строки 21–22) оставить над `dependencies` для памяти.

- [ ] **Step 2: Синхронизировать окружение**

Run (PowerShell, из `services/worker`):
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
uv sync
```
Expected: ставит `scenedetect`, torch/scipy/python_speech_features остаются (уже стояли через экстру). Без ошибок резолва.

- [ ] **Step 3: Проверить импорты**

Run:
```powershell
uv run python -c "import scenedetect, torch, scipy, python_speech_features; from scenedetect import detect, ContentDetector; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Anti-drift гейт зелёный (типы/линт не зависят, но прогоним)**

Run:
```powershell
uv run mypy app ; if ($?) { uv run ruff check app }
```
Expected: оба без ошибок (мы код ещё не трогали).

- [ ] **Step 5: Commit**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
git add services/worker/pyproject.toml services/worker/uv.lock
git commit -F services/worker/tmp/COMMIT_MSG.txt
```
(COMMIT_MSG.txt: `chore(worker): ASD-депы в базовые + scenedetect (reframe v3)`)

---

## Task 2: `build_shots_frames` (PURE) — шоты из кадров-склеек

**Files:**
- Modify: `services/worker/app/pipeline/stage3_reframe.py` (добавить функцию рядом с `build_shots`)
- Test: `services/worker/tests/unit/test_stage3_reframe.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в конец `test_stage3_reframe.py`:

```python
class TestBuildShotsFrames:
    def test_no_cuts_one_shot(self) -> None:
        from app.pipeline.stage3_reframe import build_shots_frames

        assert build_shots_frames([], total_frames=150) == [(0, 150)]

    def test_cuts_split_into_frame_intervals(self) -> None:
        from app.pipeline.stage3_reframe import build_shots_frames

        # склейки на кадрах 50 и 100 → 3 шота в КАДРАХ
        assert build_shots_frames([50, 100], total_frames=150) == [(0, 50), (50, 100), (100, 150)]

    def test_dedup_and_sort(self) -> None:
        from app.pipeline.stage3_reframe import build_shots_frames

        assert build_shots_frames([100, 50, 50], total_frames=150) == [(0, 50), (50, 100), (100, 150)]

    def test_cuts_at_bounds_ignored(self) -> None:
        from app.pipeline.stage3_reframe import build_shots_frames

        # склейка на 0 и на total — не порождают пустых шотов
        assert build_shots_frames([0, 150], total_frames=150) == [(0, 150)]

    def test_zero_total_empty(self) -> None:
        from app.pipeline.stage3_reframe import build_shots_frames

        assert build_shots_frames([10], total_frames=0) == []
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestBuildShotsFrames -v`
Expected: FAIL — `ImportError: cannot import name 'build_shots_frames'`

- [ ] **Step 3: Реализовать**

В `stage3_reframe.py`, сразу ПОСЛЕ функции `build_shots` (после строки ~268), добавить:

```python
def build_shots_frames(cuts: list[int], total_frames: int) -> list[tuple[int, int]]:
    """Номера кадров склеек (клип-относительные) → интервалы шотов [(f0, f1), …] в КАДРАХ. PURE.

    Frame-accurate замена build_shots (тот в секундах). Склейки на 0 и в конце игнорируем,
    дубликаты схлопываем. Пустой/нулевой total → []. Единица — КАДР (не float-секунда),
    чтобы граница шота попала ровно на кадр реальной склейки (нет рассинхрона в рендере).
    """
    if total_frames <= 0:
        return []
    pts = sorted({c for c in cuts if 0 < c < total_frames})
    bounds = [0, *pts, total_frames]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestBuildShotsFrames -v`
Expected: PASS (5 тестов)

- [ ] **Step 5: Commit**

```powershell
git add services/worker/app/pipeline/stage3_reframe.py services/worker/tests/unit/test_stage3_reframe.py
git commit -F services/worker/tmp/COMMIT_MSG.txt
```
(COMMIT_MSG.txt: `feat(reframe): build_shots_frames — шоты в кадрах (frame-accurate)`)

---

## Task 3: `SpeakerTrack` + `plan_regions` (PURE) — сердце планировщика

**Files:**
- Modify: `services/worker/app/pipeline/stage3_reframe.py` (добавить dataclass + функцию + хелперы)
- Test: `services/worker/tests/unit/test_stage3_reframe.py`

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `test_stage3_reframe.py`:

```python
class TestPlanRegions:
    """plan_regions: shots(кадры) + SpeakerTrack → TrackRegion, решение на шот."""

    def _track(self, f0, f1, cx, width, speak):
        from app.pipeline.stage3_reframe import SpeakerTrack

        n = f1 - f0
        return SpeakerTrack(f0=f0, f1=f1, cx=tuple([cx] * n), width=width, speak=speak)

    def test_single_speaker_fill_on_track(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        # один шот [0,30 кадров), один говорящий на cx=0.7
        tracks = [self._track(0, 30, 0.7, 0.12, 0.9)]
        regions = plan_regions(
            [(0, 30)], tracks, fps=30.0, crop_w_frac=0.32, smoothing=1.0, speak_threshold=0.0
        )
        assert len(regions) == 1
        assert regions[0].mode == "fill"
        assert regions[0].points  # есть траектория
        assert abs(regions[0].points[0].cx - 0.7) < 1e-9

    def test_two_spread_speakers_is_fit(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        tracks = [
            self._track(0, 30, 0.2, 0.1, 0.5),
            self._track(0, 30, 0.8, 0.1, 0.5),
        ]
        regions = plan_regions([(0, 30)], tracks, fps=30.0, crop_w_frac=0.32)
        assert regions[0].mode == "fit"
        assert regions[0].points == ()

    def test_picks_louder_speaker_not_largest(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        # ДВА лица КЛАСТЕРОМ (размах 0.15 < crop_w 0.32 → не широко). Крупнее (width 0.3) на
        # cx=0.45 молчит; говорит мелкое (width 0.1) на cx=0.60 → кадр на говорящего.
        tracks = [
            self._track(0, 30, 0.45, 0.3, 0.1),
            self._track(0, 30, 0.60, 0.1, 0.95),
        ]
        regions = plan_regions(
            [(0, 30)], tracks, fps=30.0, crop_w_frac=0.32, smoothing=1.0, speak_threshold=0.3
        )
        assert regions[0].mode == "fill"
        assert abs(regions[0].points[0].cx - 0.60) < 1e-9  # на говорящего, не на крупнейшего

    def test_asd_silent_falls_back_to_largest_face(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        # Кластер (не широко); никто не превышает порог → берём крупнейшее лицо (width 0.3, cx=0.45)
        tracks = [
            self._track(0, 30, 0.45, 0.3, 0.05),
            self._track(0, 30, 0.60, 0.1, 0.10),
        ]
        regions = plan_regions(
            [(0, 30)], tracks, fps=30.0, crop_w_frac=0.32, smoothing=1.0, speak_threshold=0.5
        )
        assert regions[0].mode == "fill"
        assert abs(regions[0].points[0].cx - 0.45) < 1e-9  # фолбэк на largest-face

    def test_no_tracks_is_fit(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        regions = plan_regions([(0, 30)], [], fps=30.0, crop_w_frac=0.32)
        assert regions[0].mode == "fit"

    def test_speaker_change_between_shots(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        # шот1 [0,30): говорит A(cx0.3); шот2 [30,60): говорит B(cx0.7)
        tracks = [
            self._track(0, 30, 0.3, 0.1, 0.9),
            self._track(30, 60, 0.7, 0.1, 0.9),
        ]
        regions = plan_regions(
            [(0, 30), (30, 60)], tracks, fps=30.0, crop_w_frac=0.32, smoothing=1.0, speak_threshold=0.0
        )
        assert len(regions) == 2
        assert abs(regions[0].points[0].cx - 0.3) < 1e-9
        assert abs(regions[1].points[0].cx - 0.7) < 1e-9
        # границы регионов = границы шотов в СЕКУНДАХ (кадр/fps)
        assert regions[0].t0 == 0.0 and regions[0].t1 == 1.0
        assert regions[1].t0 == 1.0 and regions[1].t1 == 2.0

    def test_mode_setting_fit_overrides(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        tracks = [self._track(0, 30, 0.5, 0.1, 0.9)]
        regions = plan_regions(
            [(0, 30)], tracks, fps=30.0, crop_w_frac=0.32, mode_setting="fit"
        )
        assert regions[0].mode == "fit"

    def test_mode_setting_fill_no_track_fallback_center(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        regions = plan_regions(
            [(0, 30)], [], fps=30.0, crop_w_frac=0.32, mode_setting="fill"
        )
        assert regions[0].mode == "fill"
        assert regions[0].points and abs(regions[0].points[0].cx - 0.5) < 1e-9
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestPlanRegions -v`
Expected: FAIL — `ImportError: cannot import name 'SpeakerTrack'`

- [ ] **Step 3: Реализовать dataclass + plan_regions + хелперы**

В `stage3_reframe.py`, в секции Dataclasses (после `TrackRegion`, ~строка 72), добавить:

```python
@dataclass(frozen=True)
class SpeakerTrack:
    """Дорожка лица с ASD-скором (выход Pass-1 анализа, вход plan_regions).

    f0/f1 — клип-относительные КАДРЫ (полуинтервал [f0, f1)). cx — per-frame X-центр (доля
    кадра), len == f1-f0. width — средняя ширина лица (доля; для largest-face фолбэка и wide).
    speak — средний ASD speak-score (>0 ≈ говорит).
    """

    f0: int
    f1: int
    cx: tuple[float, ...]
    width: float
    speak: float
```

В секции pure-математики (после `build_shots_frames` из Task 2) добавить:

```python
def _track_cx_in_shot(t: SpeakerTrack, f0: int, f1: int) -> list[float]:
    """cx дорожки t для кадров пересечения с шотом [f0, f1). PURE."""
    lo, hi = max(t.f0, f0), min(t.f1, f1)
    return [t.cx[f - t.f0] for f in range(lo, hi)]


def _is_wide_shot(active: list[SpeakerTrack], f0: int, f1: int, spread_min: float) -> bool:
    """2+ дорожек, разнесённых по X сильнее spread_min (доля кадра) → широкий план (fit). PURE."""
    reps: list[float] = []
    for t in active:
        cxs = _track_cx_in_shot(t, f0, f1)
        if cxs:
            reps.append(sum(cxs) / len(cxs))
    return len(reps) >= 2 and (max(reps) - min(reps)) > spread_min


def _pick_target(active: list[SpeakerTrack], speak_threshold: float) -> SpeakerTrack | None:
    """Выбрать дорожку в кадр: макс. speak; если ниже порога → макс. width (largest-face). PURE."""
    if not active:
        return None
    best = max(active, key=lambda t: t.speak)
    if best.speak < speak_threshold:
        best = max(active, key=lambda t: t.width)
    return best


def _track_trajectory(
    t: SpeakerTrack, f0: int, f1: int, fps: float, smoothing: float
) -> tuple[TrackPoint, ...]:
    """Сглаженная cx-траектория дорожки внутри шота → TrackPoint'ы (клип-время = кадр/fps). PURE.

    init = первый реальный cx (пан не «течёт» от центра). Нет пересечения → точка-фолбэк cx=0.5.
    """
    lo, hi = max(t.f0, f0), min(t.f1, f1)
    raw = [t.cx[f - t.f0] for f in range(lo, hi)]
    if not raw:
        return (TrackPoint(t=f0 / fps, mode="fill", cx=0.5),)
    sm = smooth_centers([c for c in raw], smoothing, init=raw[0])
    return tuple(
        TrackPoint(t=(lo + i) / fps, mode="fill", cx=c) for i, c in enumerate(sm)
    )


def plan_regions(
    shots: list[tuple[int, int]],
    tracks: list[SpeakerTrack],
    fps: float,
    *,
    crop_w_frac: float,
    smoothing: float = 0.15,
    speak_threshold: float = 0.0,
    wide_spread_min: float | None = None,
    mode_setting: str = "auto",
) -> list[TrackRegion]:
    """Cut-aligned планировщик: на КАЖДЫЙ шот один режим + траектория. Сердце Pass-1. PURE.

    shots — интервалы [(f0,f1)] в КАДРАХ (build_shots_frames). На шот:
      широкий (2+ разнесённых дорожек) → fit; иначе fill на говорящем (макс. speak), при
      молчании ASD (< speak_threshold) → фолбэк на крупнейшее лицо; нет дорожек → fit.
    mode_setting "fill"/"fit" — глобальный оверрайд. wide_spread_min дефолт = crop_w_frac.
    Границы регионов = границы шотов (= кадры склеек) → смена режима только на склейке.
    """
    spread_min = crop_w_frac if wide_spread_min is None else wide_spread_min
    regions: list[TrackRegion] = []
    for f0, f1 in shots:
        active = [t for t in tracks if t.f0 < f1 and t.f1 > f0]
        t0, t1 = f0 / fps, f1 / fps
        if mode_setting == "fit":
            regions.append(TrackRegion(t0=t0, t1=t1, mode="fit", points=()))
            continue
        if mode_setting != "fill" and (not active or _is_wide_shot(active, f0, f1, spread_min)):
            regions.append(TrackRegion(t0=t0, t1=t1, mode="fit", points=()))
            continue
        target = _pick_target(active, speak_threshold)
        pts = (
            _track_trajectory(target, f0, f1, fps, smoothing)
            if target is not None
            else (TrackPoint(t=t0, mode="fill", cx=0.5),)
        )
        regions.append(TrackRegion(t0=t0, t1=t1, mode="fill", points=pts))
    return regions
```

- [ ] **Step 4: Запустить — зелёный**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestPlanRegions -v`
Expected: PASS (8 тестов)

- [ ] **Step 5: Полный reframe-файл тестов зелёный**

Run: `uv run pytest tests/unit/test_stage3_reframe.py -v`
Expected: PASS (старые + новые)

- [ ] **Step 6: Commit**

```powershell
git add services/worker/app/pipeline/stage3_reframe.py services/worker/tests/unit/test_stage3_reframe.py
git commit -F services/worker/tmp/COMMIT_MSG.txt
```
(COMMIT_MSG.txt: `feat(reframe): plan_regions — cut-aligned решение на шот (говорящий+fit)`)

---

## Task 4: `detect_scene_cuts` (I/O) — PySceneDetect → кадры

**Files:**
- Modify: `services/worker/app/pipeline/stage3_reframe.py` (добавить I/O-функцию)

I/O нельзя честно покрыть unit-тестом без видео → проверяем на реальном сэмпле в Task 8 (DoD). Здесь — реализация + ручной прогон.

- [ ] **Step 1: Реализовать detect_scene_cuts**

В `stage3_reframe.py`, в I/O-секции (рядом с `detect_cuts`, ~строка 349), добавить:

```python
def detect_scene_cuts(
    video: Path, start: float, end: float, fps: float, *, threshold: float = 27.0
) -> list[int]:
    """Frame-accurate склейки сегмента (PySceneDetect ContentDetector), КЛИП-относительные КАДРЫ.

    Сегмент режется ffmpeg в temp h264 (декодит AV1, старт=0 → seek-точность), затем
    PySceneDetect на нём. Возвращает номера кадров склеек (0-based от старта сегмента).
    Нет склеек → []. JobError при сбое (№8).
    """
    from scenedetect import ContentDetector, SceneManager, open_video  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        seg = Path(td) / "seg.mp4"
        cut_cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", str(video),
            "-an", "-c:v", "libx264", "-preset", "ultrafast", "-r", str(fps), str(seg),
        ]  # fmt: skip
        try:
            proc = subprocess.run(cut_cmd, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise JobError(_STAGE, f"не найден ffmpeg: {e}") from e
        if proc.returncode != 0:
            raise JobError(_STAGE, f"ffmpeg seg код {proc.returncode}: {(proc.stderr or '')[-300:]}")
        try:
            vid = open_video(str(seg))
            sm = SceneManager()
            sm.add_detector(ContentDetector(threshold=threshold))
            sm.detect_scenes(vid)
            scenes = sm.get_scene_list()
        except Exception as e:  # PySceneDetect/OpenCV ошибки
            raise JobError(_STAGE, f"PySceneDetect сбой: {e}") from e
    # get_scene_list даёт [(start, end), …]; склейка = start КАДР каждой сцены, кроме первой (0).
    return [s.get_frames() for (s, _e) in scenes[1:]]
```

- [ ] **Step 2: mypy/ruff зелёные**

Run (из `services/worker`):
```powershell
uv run mypy app ; if ($?) { uv run ruff check app }
```
Expected: без ошибок. (Если mypy ругается на `scenedetect` без стабов — добавить override в `pyproject.toml` `[[tool.mypy.overrides]] module = ["scenedetect", "scenedetect.*"] ignore_missing_imports = true`, прогнать снова.)

- [ ] **Step 3: Ручной прогон на любом кэшированном source.mp4**

Run (PowerShell, из `services/worker`, подставь существующий job_id с `data/<id>/source.mp4`, напр. comedy01):
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
uv run python -c "from pathlib import Path; from app.pipeline.stage3_reframe import detect_scene_cuts; print(detect_scene_cuts(Path('data/comedy01/source.mp4'), 60.0, 80.0, 30.0))"
```
Expected: список int-кадров (напр. `[42, 91, 130]`) либо `[]`. НЕ исключение. Значения < (80-60)*30 = 600.

- [ ] **Step 4: Commit**

```powershell
git add services/worker/app/pipeline/stage3_reframe.py services/worker/pyproject.toml
git commit -F services/worker/tmp/COMMIT_MSG.txt
```
(COMMIT_MSG.txt: `feat(reframe): detect_scene_cuts — PySceneDetect → кадры склеек`)

---

## Task 5: `score_tracks_in_segment` (I/O) — MediaPipe+ASD → SpeakerTrack

**Files:**
- Modify: `services/worker/app/pipeline/asd_reframe.py` (заменить `speaker_windows` на `score_tracks_in_segment`)

- [ ] **Step 1: Заменить speaker_windows на score_tracks_in_segment**

В `asd_reframe.py`:
1. В импортах (строка 23) убрать `build_shots`, `detect_cuts` (больше не нужны тут): заменить
   ```python
   from app.pipeline.stage3_reframe import build_shots, compute_crop_window, detect_cuts
   ```
   на
   ```python
   from app.pipeline.stage3_reframe import SpeakerTrack
   ```
2. Убрать неиспользуемые импорты `apply_dead_zone, pick_speaker_centers` из строки 24 (оставить `build_tracks`):
   ```python
   from app.pipeline.stage3_speaker import build_tracks
   ```
3. Заменить ВСЮ функцию `speaker_windows` (строки 60–183) на:

```python
def score_tracks_in_segment(
    video: Path,
    src_w: int,
    src_h: int,
    start: float,
    end: float,
    fps: float,
    *,
    crop_scale: float = 0.55,
) -> list[SpeakerTrack]:
    """Сегмент → дорожки лиц с ASD speak-score (вход plan_regions). [] если лиц нет.

    Кадры@fps + аудио → MediaPipe-детект → build_tracks → crop+ASD на дорожку → SpeakerTrack
    (f0/f1 в КЛИП-кадрах @fps, cx per-frame, width средняя доля, speak средний скор).
    crop_scale тюним под MediaPipe-кропы (модель обучена на S3FD).
    """
    import cv2  # noqa: PLC0415
    import mediapipe as mp  # noqa: PLC0415
    from mediapipe.tasks import python as mp_python  # noqa: PLC0415
    from mediapipe.tasks.python import vision as mp_vision  # noqa: PLC0415
    from scipy.io import wavfile  # noqa: PLC0415

    from app.asd.scorer import score_track  # noqa: PLC0415
    from app.pipeline.stage3_reframe import _ensure_face_model  # noqa: PLC0415

    model = _ensure_face_model()
    with tempfile.TemporaryDirectory() as td:
        fdir = Path(td) / "f"
        fdir.mkdir()
        _ffmpeg(
            ["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", str(video),
             "-r", str(fps), "-f", "image2", str(fdir / "%06d.jpg"), "-loglevel", "panic"]
        )  # fmt: skip
        wav = str(Path(td) / "a.wav")
        _ffmpeg(
            ["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", str(video),
             "-ac", "1", "-vn", "-acodec", "pcm_s16le", "-ar", "16000", wav, "-loglevel", "panic"]
        )  # fmt: skip
        frames = []
        for fpath in sorted(glob.glob(str(fdir / "*.jpg"))):
            img = cv2.imread(fpath)
            if img is None:
                raise JobError(_STAGE, f"не прочитать кадр {fpath}")
            frames.append(img)
        if not frames:
            return []

        opts = mp_vision.FaceDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model)),
            min_detection_confidence=0.5,
        )
        frame_faces: list[list[dict[str, Any]]] = []
        with mp_vision.FaceDetector.create_from_options(opts) as det:
            for i, img in enumerate(frames):
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
                ff: list[dict[str, Any]] = []
                for d in res.detections:
                    b = d.bounding_box
                    ff.append(
                        {"frame": i, "bbox": [b.origin_x, b.origin_y,
                                              b.origin_x + b.width, b.origin_y + b.height]}
                    )
                frame_faces.append(ff)

        tracks = build_tracks(frame_faces)
        if not tracks:
            return []

        sr, audio = wavfile.read(wav)
        out: list[SpeakerTrack] = []
        for tr in tracks:
            faces224 = _crop_faces(tr, frames, crop_scale)
            a0 = int(tr["frame"][0] / fps * sr)
            a1 = int((tr["frame"][-1] + 1) / fps * sr)
            sc = score_track(faces224, audio[a0:a1])
            speak = float(np.mean(sc)) if sc.size else _SILENT
            cx_series = ((tr["bbox"][:, 0] + tr["bbox"][:, 2]) / 2 / src_w).tolist()
            width = float(((tr["bbox"][:, 2] - tr["bbox"][:, 0]) / src_w).mean())
            out.append(
                SpeakerTrack(
                    f0=int(tr["frame"][0]),
                    f1=int(tr["frame"][-1]) + 1,
                    cx=tuple(min(1.0, max(0.0, c)) for c in cx_series),
                    width=width,
                    speak=speak,
                )
            )
        return out
```

Примечание: `_FPS = 25` (строка 27) больше не используется как константа внутри — fps приходит параметром. Константу удалить (Task 7 cleanup проверит). `_crop_faces` остаётся как есть.

- [ ] **Step 2: mypy/ruff зелёные**

Run: `uv run mypy app ; if ($?) { uv run ruff check app }`
Expected: без ошибок. (Может ругнуться на неиспользуемый `_FPS` / импорты — удалить.)

- [ ] **Step 3: Commit**

```powershell
git add services/worker/app/pipeline/asd_reframe.py
git commit -F services/worker/tmp/COMMIT_MSG.txt
```
(COMMIT_MSG.txt: `feat(reframe): score_tracks_in_segment — дорожки+ASD → SpeakerTrack`)

---

## Task 6: Переписать `reframe_segment` на единый путь

**Files:**
- Modify: `services/worker/app/pipeline/stage3_reframe.py` (функция `reframe_segment`, строки 484–553)

- [ ] **Step 1: Переписать reframe_segment**

Заменить тело `reframe_segment` (484–553) на единый путь:

```python
def reframe_segment(
    video: Path,
    src_w: int,
    src_h: int,
    start: float,
    end: float,
    *,
    clip_id: str,
    out_dir: Path,
    fps: float,
    mode_setting: str = "auto",
    speaker_crop_scale: float = 0.55,
    face_fps: float = 25.0,
    smoothing: float = 0.15,
    min_hold_sec: float = 1.5,
    speak_threshold: float = 0.0,
    scene_threshold: float = 27.0,
) -> tuple[list[TrackRegion], bool]:
    """Сегмент → (cut-aligned регионы, face_found). Единый путь (ASD по дефолту).

    PySceneDetect → кадры склеек → build_shots_frames → score_tracks_in_segment (MediaPipe+ASD)
    → plan_regions → merge_short_regions. Пишет reframe_<clip_id>.json ({regions:[...]}).
    """
    from app.pipeline.asd_reframe import score_tracks_in_segment  # noqa: PLC0415

    duration = end - start
    total_frames = round(duration * fps)
    crop_w_frac = round(src_h * _ASPECT_W / _ASPECT_H) / src_w

    cuts = detect_scene_cuts(video, start, end, fps, threshold=scene_threshold)
    shots = build_shots_frames(cuts, total_frames)

    tracks = score_tracks_in_segment(
        video, src_w, src_h, start, end, face_fps, crop_scale=speaker_crop_scale
    )
    face_found = bool(tracks)

    regions = merge_short_regions(
        plan_regions(
            shots,
            tracks,
            face_fps,
            crop_w_frac=crop_w_frac,
            smoothing=smoothing,
            speak_threshold=speak_threshold,
            mode_setting=mode_setting,
        ),
        min_hold_sec,
    )
    if not regions:
        regions = [TrackRegion(t0=0.0, t1=duration, mode="fit", points=())]

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_reframe_json(out_dir, clip_id, regions)
    return regions, face_found
```

⚠️ Важно: `plan_regions` строит траектории в КЛИП-времени по `face_fps` (кадры дорожек @face_fps). Рендер (`render_clip`) использует `meta.fps` для trim. Регионы `t0/t1` уже в секундах (кадр/face_fps) → рендер пересчитает в свои кадры по `meta.fps`. Согласованность по СЕКУНДАМ, не по кадрам разных fps — это ок, т.к. границы регионов = секунды склеек.

- [ ] **Step 2: Обновить вызов в run.py**

В `services/worker/app/run.py` заменить блок вызова `reframe_segment` (строки 133–141) на:

```python
        regions, face_found = reframe_segment(
            out / "source.mp4", meta.width, meta.height, seg.start, seg.end,
            clip_id=clip_id, out_dir=out, fps=meta.fps, mode_setting=s.reframe_mode,
            speaker_crop_scale=s.reframe_speaker_crop_scale,
            face_fps=s.reframe_face_fps, smoothing=s.reframe_smoothing,
            min_hold_sec=s.reframe_min_hold_sec,
            speak_threshold=s.reframe_speak_threshold,
            scene_threshold=s.reframe_scene_threshold,
        )  # fmt: skip
```

(Кнобы `reframe_speak_threshold`/`reframe_scene_threshold` добавим в config в Task 8 — пока mypy на run.py может ругаться; зелёным станет после Task 8. Это нормально, коммитим связку в Task 8.)

- [ ] **Step 3: mypy на pipeline (run.py отложим до Task 8)**

Run: `uv run mypy app/pipeline`
Expected: без ошибок в `stage3_reframe.py`/`asd_reframe.py`. (run.py/config — в Task 8.)

- [ ] **Step 4: Commit (связка с Task 8 — коммитим после config)**

Пока НЕ коммитим отдельно (reframe_segment зовёт ещё не существующие настройки). Переходим к Task 7 (рендер, независим) и Task 8 (config), затем общий зелёный коммит. Если хочется чекпоинт — `git add -A && git stash` НЕ нужен; просто продолжаем.

---

## Task 7: Рендер — жёсткий cut (убрать xfade)

**Files:**
- Modify: `services/worker/app/pipeline/stage5_render.py` (`_chain_video_segs` 70–104, `build_smooth_filter` 107–164, `build_timeline_filter` 394–453)
- Test: `services/worker/tests/unit/test_stage5_render.py`, `services/worker/tests/unit/test_timeline_filter.py`

- [ ] **Step 1: Переписать тесты на hard-cut (сначала тест)**

В `test_stage5_render.py`:
- Удалить методы `test_fill_to_fit_uses_xfade`, `test_fit_to_fill_uses_xfade`, `test_multi_region_chain`(если завязан на xfade-счёт), `test_xfade_offset_calculation`, `test_xfade_zero_falls_back_to_concat` (строки ~129–161) и ВЕСЬ класс `TestChainVideoSegs` (строки ~169–205).
- Вместо них добавить:

```python
class TestChainVideoSegs:
    """_chain_video_segs: всегда попарный concat (жёсткий cut, без xfade)."""

    def test_two_segments_concat(self) -> None:
        parts = _chain_video_segs(["s0", "s1"], "cv")
        assert parts == ["[s0][s1]concat=n=2:v=1:a=0[cv];"]

    def test_three_segments_chain(self) -> None:
        parts = _chain_video_segs(["s0", "s1", "s2"], "cv")
        assert parts == [
            "[s0][s1]concat=n=2:v=1:a=0[ch1];",
            "[ch1][s2]concat=n=2:v=1:a=0[cv];",
        ]

    def test_never_uses_xfade(self) -> None:
        parts = _chain_video_segs(["s0", "s1", "s2"], "cv")
        assert all("xfade" not in p for p in parts)


class TestBuildSmoothFilterHardCut:
    def test_fill_to_fit_is_hard_cut(self) -> None:
        regions = [
            TrackRegion(0.0, 2.0, "fill", (TrackPoint(0.0, "fill", 0.5),)),
            TrackRegion(2.0, 4.0, "fit", ()),
        ]
        fc = build_smooth_filter(regions, 1920, 1080, 30.0, "c.ass")
        assert "xfade" not in fc
        assert "concat=n=2" in fc
```

В `test_timeline_filter.py` строки 38–39 заменить:
```python
    # fill→fit mode change: жёсткий cut (concat), без xfade
    assert "xfade" not in fc
    assert "concat=n=2:v=1:a=0" in fc
```

- [ ] **Step 2: Запустить — падает (старый код ещё с xfade)**

Run: `uv run pytest tests/unit/test_stage5_render.py::TestChainVideoSegs tests/unit/test_stage5_render.py::TestBuildSmoothFilterHardCut -v`
Expected: FAIL (сигнатура `_chain_video_segs` старая 5-арг; xfade присутствует).

- [ ] **Step 3: Переписать _chain_video_segs (без xfade)**

Заменить функцию `_chain_video_segs` (строки 70–104) на:

```python
def _chain_video_segs(seg_labels: list[str], final_label: str) -> list[str]:
    """Chain N≥2 видео-сегментов попарным concat (жёсткий cut на границе шота). PURE.

    Граница = реальная склейка источника → жёсткий cut невидим (контент и так прыгает).
    xfade удалён намеренно: кроссфейд тайт↔широкий сам читался как зум-вспышка.
    """
    parts: list[str] = []
    current = seg_labels[0]
    for i in range(1, len(seg_labels)):
        is_last = i == len(seg_labels) - 1
        out_label = final_label if is_last else f"ch{i}"
        parts.append(f"[{current}][{seg_labels[i]}]concat=n=2:v=1:a=0[{out_label}];")
        current = out_label
    return parts
```

- [ ] **Step 4: Обновить build_smooth_filter — убрать xfade_dur + durations**

В `build_smooth_filter` (107–164):
1. Из сигнатуры убрать параметр `xfade_dur: float = 0.15` (строка 117).
2. Убрать строку `durations: list[float] = []` (строка 133) и `durations.append((f1 - f0) / fps)` (строка 137).
3. Заменить вызов цепочки (строки 158–162) на:
```python
        parts.extend(_chain_video_segs([f"s{i}" for i in range(n)], "cv"))
```

- [ ] **Step 5: Обновить build_timeline_filter — то же**

В `build_timeline_filter` (394–453):
1. Из сигнатуры убрать `xfade_dur: float = 0.15` (строка 404).
2. Убрать `durations: list[float] = []` (строка 419) и `durations.append((s.src_f1 - s.src_f0) / fps)` (строка 421).
3. Заменить блок (строки 443–448):
```python
    sv_labels = [f"sv{i}" for i in range(n)]
    if n == 1:
        parts.append(f"[sv0]subtitles={ass_name}[outv];")
    else:
        parts.extend(_chain_video_segs(sv_labels, "cv"))
        parts.append(f"[cv]subtitles={ass_name}[outv];")
```
(переменная `modes` больше не нужна — удалить её строку, если осталась.)

- [ ] **Step 6: Запустить — зелёный**

Run: `uv run pytest tests/unit/test_stage5_render.py tests/unit/test_timeline_filter.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add services/worker/app/pipeline/stage5_render.py services/worker/tests/unit/test_stage5_render.py services/worker/tests/unit/test_timeline_filter.py
git commit -F services/worker/tmp/COMMIT_MSG.txt
```
(COMMIT_MSG.txt: `fix(render): жёсткий cut на границе шота (убран xfade-пластырь)`)

---

## Task 8: Config + кнобы + связочный зелёный

**Files:**
- Modify: `services/worker/app/config.py` (строки 60–75)
- Modify: `services/worker/app/run.py` (уже поправлен в Task 6)

- [ ] **Step 1: Обновить настройки reframe**

В `config.py` заменить блок reframe-настроек (строки 60–75) на:

```python
    reframe_mode: Literal["auto", "fill", "fit"] = "auto"
    # active-speaker: тюнинг кропа лица под MediaPipe (модель ASD обучена на S3FD).
    reframe_speaker_crop_scale: float = 0.55
    # движок рендера: A = ffmpeg piecewise expr (быстрый); B = cv2 per-frame (точный).
    reframe_engine: str = "A"
    # сэмплирование лиц/ASD @fps (25 = как обучен ASD; выше = точнее/медленнее).
    reframe_face_fps: float = 25.0
    reframe_smoothing: float = 0.15  # exponential smoothing коэф (0=без; 1=нет сглаж.)
    # анти-флеш: регион < min_hold НЕ переключает режим, поглощается предыдущим.
    reframe_min_hold_sec: float = 1.5
    # порог ASD: speak < threshold → фолбэк на largest-face. Рычаг «тот человек vs безопасно».
    reframe_speak_threshold: float = 0.0
    # PySceneDetect ContentDetector: чувствительность детекта склеек (~27 шкала контента).
    reframe_scene_threshold: float = 27.0
```

Удалены: `reframe_speaker`, `reframe_cut_threshold`, `reframe_dead_zone`, `reframe_wide_ratio` (больше не используются — plan_regions берёт wide_spread_min=crop_w_frac по дефолту).

- [ ] **Step 2: Полный mypy/ruff/anti-drift**

Run (из `services/worker`):
```powershell
uv run mypy app ; if ($?) { uv run ruff check app }
```
Expected: без ошибок (run.py теперь видит новые настройки).

- [ ] **Step 3: Полный unit-прогон**

Run: `uv run pytest tests/unit -q`
Expected: PASS (все, кроме намеренно удалённых).

- [ ] **Step 4: Commit (связка Task 6 + 8)**

```powershell
git add services/worker/app/config.py services/worker/app/run.py services/worker/app/pipeline/stage3_reframe.py
git commit -F services/worker/tmp/COMMIT_MSG.txt
```
(COMMIT_MSG.txt: `feat(reframe): единый reframe_segment + кнобы (scene/speak threshold)`)

---

## Task 9: Удалить мёртвый код (largest-face sample-путь + legacy)

**Files:**
- Modify: `services/worker/app/pipeline/stage3_reframe.py`
- Modify: `services/worker/tests/unit/test_stage3_reframe.py`

После единого пути устарели: `detect_cuts` (ffmpeg), `build_shots` (секунды), sample-based `build_regions_from_shots`, `decide_shot_mode`, `build_shot_trajectory`, `samples_in_shot`, `build_trajectory`, `build_regions`, `classify_frame`, `shot_plan_to_regions`, `windows_to_shot_plan`, `ShotPlan`, `TrackPoint`-legacy-helpers. **Удаляем ТОЛЬКО подтверждённо-неиспользуемое.**

- [ ] **Step 1: Найти реальных потребителей каждого кандидата (grep-driven, НЕ угадывать)**

Run (из корня репо). Кандидаты — ВСЁ, что мог осиротить рефактор, включая `stage3_speaker.py`:
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
foreach ($n in "detect_cuts","build_shots","build_regions_from_shots","decide_shot_mode","build_shot_trajectory","samples_in_shot","build_trajectory","build_regions","classify_frame","shot_is_wide","aggregate_center","shot_plan_to_regions","windows_to_shot_plan","ShotPlan","sample_faces_continuous","pick_speaker_centers","apply_dead_zone","_iou") { Write-Host "== $n =="; Select-String -Path services/worker/app/**/*.py -Pattern $n | Where-Object { $_.Line -notmatch "def $n" -and $_.Line -notmatch "^\s*#" } }
```
Правило: имя удаляем, ТОЛЬКО если все его вхождения вне `def`/комментариев лежат внутри функций, которые мы тоже удаляем (транзитивно). Если хоть один живой потребитель — оставляем.

Гарантированно ЖИВЫЕ (НЕ трогать): `compute_crop_window`, `smooth_centers` (зовёт `_track_trajectory`), `merge_short_regions` (зовёт `reframe_segment`), `_is_wide_shot`/`_pick_target`/`_track_trajectory`/`_track_cx_in_shot` (зовёт `plan_regions`), `plan_regions`, `build_shots_frames`, `detect_scene_cuts`, `TrackPoint`, `TrackRegion`, `SpeakerTrack`, `_ensure_face_model` (зовёт `score_tracks_in_segment`), `build_tracks` (зовёт `score_tracks_in_segment`).

Ожидаемо МЁРТВЫЕ после рефактора (подтвердить grep'ом перед удалением): `detect_cuts`, `build_shots`, `build_regions_from_shots`, `decide_shot_mode`, `build_shot_trajectory`, `samples_in_shot`, `build_trajectory`, `build_regions`, `classify_frame`, `shot_is_wide`, `aggregate_center`, `shot_plan_to_regions`, `windows_to_shot_plan`, `ShotPlan`, `sample_faces_continuous` (в `stage3_reframe.py`); `pick_speaker_centers`, `apply_dead_zone` (в `stage3_speaker.py` — их потребитель `speaker_windows` удалён в Task 5; `build_tracks`/`_iou` остаются живыми через `score_tracks_in_segment`).

- [ ] **Step 2: Удалить подтверждённо-мёртвые определения + их тесты**

Из `stage3_reframe.py` удалить определения, подтверждённые Step 1 как мёртвые (см. список выше). Из `stage3_speaker.py` удалить `pick_speaker_centers` и `apply_dead_zone`, если Step 1 не нашёл живых потребителей (`build_tracks`/`_iou` оставить).

Удалить соответствующие тест-классы:
- В `test_stage3_reframe.py`: классы тестов удалённых функций — ожидаемо `TestBuildTrajectory`, `TestBuildRegions`, `TestShotPlanToRegions`, `TestWindowsToShotPlan`, `TestSamplesInShot`, `TestDecideShotMode`, `TestBuildShotTrajectory`, `TestBuildRegionsFromShots`, `TestClassifyFrame`, `TestShotIsWide`, `TestAggregateCenter`. Оставить `TestComputeCropWindow`, `TestSmoothCenters`, `TestMergeShortRegions`, `TestBuildShotsFrames`, `TestPlanRegions`.
- В `test_stage3_speaker.py`: удалить тесты `pick_speaker_centers`/`apply_dead_zone`, если они удалены из кода; оставить тесты `build_tracks`.

Из импортов `test_stage3_reframe.py` (строки 12–26) убрать имена всех удалённых функций/классов (иначе ImportError). Импорт-блок должен ссылаться только на оставленные имена.

- [ ] **Step 3: Полный гейт зелёный**

Run (из `services/worker`):
```powershell
uv run pytest tests/unit -q ; if ($?) { uv run mypy app } ; if ($?) { uv run ruff check app }
```
Expected: всё зелёное, нет «imported but unused», нет «defined but never used».

- [ ] **Step 4: Commit**

```powershell
git add services/worker/app/pipeline/stage3_reframe.py services/worker/tests/unit/test_stage3_reframe.py
git commit -F services/worker/tmp/COMMIT_MSG.txt
```
(COMMIT_MSG.txt: `refactor(reframe): удалить мёртвый largest-face sample-путь и legacy`)

---

## Task 10: Полный `just check` + реальный DoD-прогон

**Files:** нет правок кода (верификация). Тестовое видео — фаундер даёт ссылку/файл.

- [ ] **Step 1: Зелёный гейт целиком**

Run (PowerShell, из корня репо):
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
just check
```
Expected: lint + mypy + tsc + test-unit + anti-drift — всё зелёное.

- [ ] **Step 2: Реальный прогон на DoD-видео**

Получить от фаундера talking-head видео (1–2 спикера, статичные планы). Прогон:
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
uv run python -m app.run dod01 "<youtube_url_от_фаундера>"
```
Expected: 5–10 клипов в `data/dod01/clips/`, `job.json` валиден.

- [ ] **Step 3: Доказать Δ=0 (граница режима = склейка)**

Написать `services/worker/tmp/verify_flash.py`: для каждого клипа прочитать `reframe_<clip>.json`, для каждой границы региона (t1 предыдущего) найти ближайшую склейку `detect_scene_cuts` и посчитать Δ в кадрах. Вывести max Δ по всем границам.
Run: `uv run python tmp/verify_flash.py dod01`
Expected: max Δ = 0 кадров на всех границах режима.

- [ ] **Step 4: Глазами — 0 флешей + кадр на говорящем**

Открыть 2–3 клипа, на каждой смене плана покадрово (любой плеер с покадровой перемоткой) убедиться: нет «дёрнулось и переключилось», нет чёрного края/зум-вспышки; в fill-планах кадр на ГОВОРЯЩЕМ. Сделать скрин до/после границы → показать фаундеру.

- [ ] **Step 5: Зафиксировать результат в журнале**

Дописать в `CLAUDE.md` (журнал прогресса) строку «что сделано + чем доказано» по аналогии с предыдущими (коммит, Δ=0, скрин). Это контекст для следующей сессии.

- [ ] **Step 6: Финальный commit**

```powershell
git add CLAUDE.md
git commit -F services/worker/tmp/COMMIT_MSG.txt
```
(COMMIT_MSG.txt: `docs: reframe v3 DoD — 0 флешей (Δ=0) + кадр на говорящем, прогон dod01`)

---

## Что будет калиброваться ПОСЛЕ (вкус фаундера, не в этом плане)

`reframe_speak_threshold` («тот человек vs безопасный largest-face») и `reframe_scene_threshold`
(чувствительность склеек). Дефолты заданы; финальная подкрутка — на реальных прогонах по скринам.
$0 по деньгам (transcript/segments из кэша), цена — только CPU-время (ASD ~2× длительности клипа).
