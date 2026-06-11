# Reframe Flash Fix — Cut-Snap + Per-Shot Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать «флеш» при переключении вертикального кадра (`fill`) ↔ широкого вида (`fit`), привязав смену режима к реальным склейкам и решая режим один раз на план (shot), а не на каждый 5fps-сэмпл.

**Architecture:** Корень флеша доказан (см. «Контекст» ниже): границы смены режима в V2 стоят на сетке семплирования лиц (кратно 0.2с) и расцеплены с реальными склейками — на `comedy01` clip_01 граница `fill→fit` стоит на 11.6с, а ближайшая склейка на 10.44с (рассинхрон **29 кадров**), причём в окне ±1с склеек нет вообще. Фикс (как у Google AutoFlip / OpusClip): детектим frame-accurate склейки → режем клип на планы → решаем `fill`/`fit` **один раз на план** (мажоритарно по геометрии лиц) → внутри `fill`-плана сохраняем плавный пан V2 (`smooth_centers`). Смена режима теперь происходит ТОЛЬКО на склейке, где она невидима (контент и так меняется). Правка локализована в построении регионов (`stage3_reframe.py`); оба движка рендера (A и B) берут регионы готовыми и чинятся апстримом.

**Tech Stack:** Python 3.12, pytest, ffmpeg scene-detect (уже в кодовой базе — `detect_cuts`), MediaPipe (уже есть). Новых зависимостей НЕТ.

---

## Контекст (прочитать перед стартом)

- **Диагноз доказан** планнером (Opus) 2026-06-09 на реальном кэше `comedy01`:
  - V2-границы режима `comedy01/reframe_clip_01.json`: `fill 0→11.6`, `fit 11.6→13.6` — кратны 0.2 (5fps-сетка).
  - Реальные склейки (ffmpeg scene): `…10.44, 12.8, 18.04…`. Граница 11.6 → рассинхрон **+29 кадров** от склейки 10.44; в окне 11.6±1.0с склеек нет → режим прыгает **посреди непрерывного плана** = флеш.
  - Визуальный пруф: `services/worker/tmp/proof_montage.png`.
- **Что НЕ трогаем:** плавный пан внутри `fill` (`smooth_centers` 0.15 — он хороший), выбор моментов (Gemini), субтитры, UI, ASD speaker-путь (`asd_reframe.py` + `shot_plan_to_regions`).
- **Целевой движок для финальной визуальной проверки — Engine B** (`REFRAME_ENGINE=B`, cv2 per-frame), по просьбе фаундера. Но фикс Tasks 1-5 чинит и Engine A тоже (правка в построении регионов).
- **Правила репо (CLAUDE.md):** TDD на pure-логике; PURE отделена от I/O; `JobError` вместо тихих фолбэков; `just check` зелёный перед каждым коммитом; коммиты — conventional, ТОЛЬКО из PowerShell с PATH-refresh (см. HANDOFF §3).
- **После правки кода воркера — перезапустить воркер** (uvicorn без `--reload`).

### Команды окружения (PowerShell, каждый вызов)
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
```
Тесты одного модуля: `uv run pytest tests/unit/test_stage3_reframe.py -v`
Гейт перед коммитом (из корня репо): `just check`

### Карта файлов
- **Modify:** `services/worker/app/pipeline/stage3_reframe.py` — добавить PURE `samples_in_shot`, `decide_shot_mode`, `build_shot_trajectory`, `build_regions_from_shots`; переписать standard-ветку в `reframe_segment`.
- **Modify:** `services/worker/app/config.py` — добавить `reframe_wide_ratio`.
- **Modify:** `services/worker/app/run.py:133-140` — пробросить `wide_ratio`.
- **Test:** `services/worker/tests/unit/test_stage3_reframe.py` — новые классы тестов.
- **Verify (временный):** `services/worker/tmp/verify_newregions.py` — интеграционная проверка выравнивания.
- **Task 6 (enhancement, gated):** `stage3_reframe.py` (поле `transition_in`) + `stage5_render.py` (`render_frame_by_frame` zoom).

---

## Task 1: PURE `samples_in_shot` — сэмплы лиц внутри интервала плана

**Files:**
- Modify: `services/worker/app/pipeline/stage3_reframe.py` (добавить функцию после `build_shots`, ~строка 268)
- Test: `services/worker/tests/unit/test_stage3_reframe.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в конец `tests/unit/test_stage3_reframe.py`:
```python
class TestSamplesInShot:
    def test_filters_to_interval_half_open(self) -> None:
        from app.pipeline.stage3_reframe import samples_in_shot

        raw = [(0.0, [(0.5, 0.1)]), (0.2, [(0.4, 0.1)]), (0.4, []), (0.6, [(0.7, 0.1)])]
        # интервал [0.2, 0.6): берём t=0.2 и t=0.4, НЕ берём 0.0 и 0.6
        got = samples_in_shot(raw, 0.2, 0.6)
        assert [t for t, _ in got] == [0.2, 0.4]

    def test_empty_when_no_samples_in_range(self) -> None:
        from app.pipeline.stage3_reframe import samples_in_shot

        assert samples_in_shot([(0.0, []), (5.0, [])], 1.0, 2.0) == []
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestSamplesInShot -v`
Expected: FAIL с `ImportError: cannot import name 'samples_in_shot'`

- [ ] **Step 3: Реализовать**

Вставить в `stage3_reframe.py` сразу после функции `build_shots` (после строки ~268):
```python
def samples_in_shot(
    raw_samples: list[tuple[float, list[tuple[float, float]]]], t0: float, t1: float
) -> list[tuple[float, list[tuple[float, float]]]]:
    """Сэмплы лиц (t, faces), попадающие в полуинтервал плана [t0, t1). PURE."""
    return [(t, faces) for (t, faces) in raw_samples if t0 <= t < t1]
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestSamplesInShot -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Коммит** (из PowerShell, см. HANDOFF про кодировку сообщений)

```powershell
git add services/worker/app/pipeline/stage3_reframe.py services/worker/tests/unit/test_stage3_reframe.py
git commit -m "feat(reframe): samples_in_shot — сэмплы лиц внутри плана (PURE)"
```

---

## Task 2: PURE `decide_shot_mode` — один режим на весь план

**Files:**
- Modify: `services/worker/app/pipeline/stage3_reframe.py` (после `samples_in_shot`)
- Test: `services/worker/tests/unit/test_stage3_reframe.py`

**Замысел:** для плана решаем `fill`/`fit` ОДИН раз. План широкий (`fit`), если доля кадров с широкой геометрией (по `classify_frame`) ≥ `wide_ratio`. Нет лиц вообще → `fit`. `mode_setting` `fit`/`fill` — глобальный оверрайд.

- [ ] **Step 1: Написать падающий тест**

```python
class TestDecideShotMode:
    def test_no_samples_is_fit(self) -> None:
        from app.pipeline.stage3_reframe import decide_shot_mode

        assert decide_shot_mode([], crop_w_frac=0.3) == "fit"

    def test_single_face_cluster_is_fill(self) -> None:
        from app.pipeline.stage3_reframe import decide_shot_mode

        # одно лицо в каждом кадре → fill
        samples = [(0.0, [(0.5, 0.1)]), (0.2, [(0.52, 0.1)]), (0.4, [(0.48, 0.1)])]
        assert decide_shot_mode(samples, crop_w_frac=0.3) == "fill"

    def test_two_spread_faces_majority_is_fit(self) -> None:
        from app.pipeline.stage3_reframe import decide_shot_mode

        # 2 разнесённых лица (размах 0.6 > crop_w_frac 0.3) в большинстве кадров → fit
        wide = [(0.1, 0.1), (0.7, 0.1)]
        samples = [(0.0, wide), (0.2, wide), (0.4, [(0.5, 0.1)])]
        assert decide_shot_mode(samples, crop_w_frac=0.3) == "fit"

    def test_mode_setting_overrides(self) -> None:
        from app.pipeline.stage3_reframe import decide_shot_mode

        wide = [(0.1, 0.1), (0.7, 0.1)]
        assert decide_shot_mode([(0.0, wide)], crop_w_frac=0.3, mode_setting="fill") == "fill"
        assert decide_shot_mode([(0.0, [(0.5, 0.1)])], crop_w_frac=0.3, mode_setting="fit") == "fit"
```

- [ ] **Step 2: Запустить — падает**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestDecideShotMode -v`
Expected: FAIL (`cannot import name 'decide_shot_mode'`)

- [ ] **Step 3: Реализовать** (вставить после `samples_in_shot`)

```python
def decide_shot_mode(
    shot_samples: list[tuple[float, list[tuple[float, float]]]],
    *,
    crop_w_frac: float,
    mode_setting: str = "auto",
    wide_ratio: float = 0.5,
) -> str:
    """Один режim ("fill"|"fit") на весь план по геометрии лиц. PURE.

    План = "fit", если доля кадров с широкой геометрией (classify_frame) ≥ wide_ratio.
    Нет сэмплов → "fit". mode_setting "fit"/"fill" — глобальный оверрайд.
    """
    if mode_setting in ("fill", "fit"):
        return mode_setting
    if not shot_samples:
        return "fit"
    fit_frames = sum(
        1 for _t, faces in shot_samples if classify_frame(faces, crop_w_frac) == "fit"
    )
    return "fit" if fit_frames >= wide_ratio * len(shot_samples) else "fill"
```

- [ ] **Step 4: Запустить — проходит**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestDecideShotMode -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Коммит**

```powershell
git add services/worker/app/pipeline/stage3_reframe.py services/worker/tests/unit/test_stage3_reframe.py
git commit -m "feat(reframe): decide_shot_mode — режим один на план (PURE)"
```

---

## Task 3: PURE `build_shot_trajectory` — плавный пан внутри плана (smoothing reset per shot)

**Files:**
- Modify: `services/worker/app/pipeline/stage3_reframe.py` (после `decide_shot_mode`)
- Test: `services/worker/tests/unit/test_stage3_reframe.py`

**Замысел:** внутри `fill`-плана строим сглаженную cx-траекторию `smooth_centers` крупнейшего лица. Важно: сглаживание начинается заново на каждый план (не «протекает» через склейку — иначе камера панит сквозь стык).

- [ ] **Step 1: Написать падающий тест**

```python
class TestBuildShotTrajectory:
    def test_returns_trackpoints_with_smoothed_cx(self) -> None:
        from app.pipeline.stage3_reframe import build_shot_trajectory

        samples = [(1.0, [(0.2, 0.1)]), (1.2, [(0.8, 0.1)])]
        pts = build_shot_trajectory(samples, smoothing=0.5)
        assert len(pts) == 2
        assert pts[0].t == 1.0 and pts[0].mode == "fill"
        # первый сэмпл: last(0.5) + 0.5*(0.2-0.5) = 0.35
        assert abs(pts[0].cx - 0.35) < 1e-9
        # второй: 0.35 + 0.5*(0.8-0.35) = 0.575
        assert abs(pts[1].cx - 0.575) < 1e-9

    def test_largest_face_chosen(self) -> None:
        from app.pipeline.stage3_reframe import build_shot_trajectory

        # два лица: крупнейшее (w=0.3) на cx=0.9 → к нему ведём
        pts = build_shot_trajectory([(0.0, [(0.1, 0.1), (0.9, 0.3)])], smoothing=1.0)
        assert abs(pts[0].cx - 0.9) < 1e-9

    def test_no_face_holds_last(self) -> None:
        from app.pipeline.stage3_reframe import build_shot_trajectory

        pts = build_shot_trajectory([(0.0, [(0.2, 0.1)]), (0.2, [])], smoothing=1.0)
        # второй сэмпл без лица → держим последний (0.2)
        assert abs(pts[1].cx - 0.2) < 1e-9
```

- [ ] **Step 2: Запустить — падает**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestBuildShotTrajectory -v`
Expected: FAIL (`cannot import name 'build_shot_trajectory'`)

- [ ] **Step 3: Реализовать** (после `decide_shot_mode`)

```python
def build_shot_trajectory(
    shot_samples: list[tuple[float, list[tuple[float, float]]]], smoothing: float
) -> tuple[TrackPoint, ...]:
    """Сглаженная cx-траектория ВНУТРИ одного fill-плана. PURE.

    smooth_centers сбрасывается на каждый план (стартует с 0.5) — пан не «протекает»
    сквозь склейку. cx берётся у КРУПНЕЙШЕГО лица; нет лица → держим последний.
    """
    cx_raws: list[float | None] = [
        max(faces, key=lambda f: f[1])[0] if faces else None for _t, faces in shot_samples
    ]
    cx_sm = smooth_centers(cx_raws, smoothing)
    return tuple(
        TrackPoint(t=t, mode="fill", cx=cx)
        for (t, _faces), cx in zip(shot_samples, cx_sm, strict=False)
    )
```

- [ ] **Step 4: Запустить — проходит**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestBuildShotTrajectory -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Коммит**

```powershell
git add services/worker/app/pipeline/stage3_reframe.py services/worker/tests/unit/test_stage3_reframe.py
git commit -m "feat(reframe): build_shot_trajectory — пан внутри плана, smoothing per-shot (PURE)"
```

---

## Task 4: PURE `build_regions_from_shots` — сборка cut-aligned регионов

**Files:**
- Modify: `services/worker/app/pipeline/stage3_reframe.py` (после `build_shot_trajectory`)
- Test: `services/worker/tests/unit/test_stage3_reframe.py`

**Замысел:** собрать `TrackRegion` по планам — на каждый план один режим, внутри `fill` траектория. В конце `merge_short_regions` (поглощает планы короче `min_hold` — гасит дрожь на рапид-монтаже). Заменяет grid-based `build_trajectory`+`build_regions`.

- [ ] **Step 1: Написать падающий тест**

```python
class TestBuildRegionsFromShots:
    def test_one_mode_per_shot_cut_aligned(self) -> None:
        from app.pipeline.stage3_reframe import build_regions_from_shots

        # 3 плана по реальным склейкам; средний — широкий (2 разнесённых лица)
        shots = [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0)]
        single = [(0.5, 0.1)]
        wide = [(0.1, 0.1), (0.8, 0.1)]
        raw = [
            (0.0, single), (1.0, single),          # план 1 → fill
            (2.0, wide), (3.0, wide),               # план 2 → fit
            (4.0, single), (5.0, single),           # план 3 → fill
        ]
        regions = build_regions_from_shots(
            shots, raw, crop_w_frac=0.3, smoothing=0.15, min_hold_sec=0.0
        )
        assert [(r.t0, r.t1, r.mode) for r in regions] == [
            (0.0, 2.0, "fill"), (2.0, 4.0, "fit"), (4.0, 6.0, "fill")
        ]
        # границы режима = границы планов (= реальные склейки), НЕ сетка сэмплов
        assert regions[0].points and regions[2].points  # fill-планы имеют траекторию
        assert regions[1].points == ()                   # fit-план без траектории

    def test_short_shot_absorbed_by_min_hold(self) -> None:
        from app.pipeline.stage3_reframe import build_regions_from_shots

        # короткий средний план (0.3с < min_hold 1.5) поглощается предыдущим → нет дрожи
        shots = [(0.0, 2.0), (2.0, 2.3), (2.3, 4.0)]
        single = [(0.5, 0.1)]
        wide = [(0.1, 0.1), (0.8, 0.1)]
        raw = [(0.0, single), (2.0, wide), (2.3, single)]
        regions = build_regions_from_shots(
            shots, raw, crop_w_frac=0.3, smoothing=0.15, min_hold_sec=1.5
        )
        assert all(r.mode == "fill" for r in regions)  # короткий fit съеден

    def test_fill_without_faces_has_fallback_point(self) -> None:
        from app.pipeline.stage3_reframe import build_regions_from_shots

        # mode_setting=fill форсит fill даже без лиц → должна быть точка-фолбэк (cx=0.5)
        regions = build_regions_from_shots(
            [(0.0, 2.0)], [(0.0, [])], crop_w_frac=0.3, smoothing=0.15,
            min_hold_sec=0.0, mode_setting="fill",
        )
        assert regions[0].mode == "fill"
        assert regions[0].points and abs(regions[0].points[0].cx - 0.5) < 1e-9
```

- [ ] **Step 2: Запустить — падает**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestBuildRegionsFromShots -v`
Expected: FAIL (`cannot import name 'build_regions_from_shots'`)

- [ ] **Step 3: Реализовать** (после `build_shot_trajectory`)

```python
def build_regions_from_shots(
    shots: list[tuple[float, float]],
    raw_samples: list[tuple[float, list[tuple[float, float]]]],
    crop_w_frac: float,
    smoothing: float,
    min_hold_sec: float,
    *,
    mode_setting: str = "auto",
    wide_ratio: float = 0.5,
) -> list[TrackRegion]:
    """Cut-aligned регионы: ОДИН режим на план, пан внутри fill-плана. PURE.

    Заменяет grid-based build_trajectory+build_regions. Границы режима = границы планов
    (= реальные склейки) → смена режима только на склейке → нет флеша. merge_short_regions
    в конце гасит планы короче min_hold (рапид-монтаж).
    """
    regions: list[TrackRegion] = []
    for t0, t1 in shots:
        seg = samples_in_shot(raw_samples, t0, t1)
        mode = decide_shot_mode(
            seg, crop_w_frac=crop_w_frac, mode_setting=mode_setting, wide_ratio=wide_ratio
        )
        if mode == "fill":
            pts = build_shot_trajectory(seg, smoothing)
            if not pts:
                pts = (TrackPoint(t=t0, mode="fill", cx=0.5),)
            regions.append(TrackRegion(t0=t0, t1=t1, mode="fill", points=pts))
        else:
            regions.append(TrackRegion(t0=t0, t1=t1, mode="fit", points=()))
    return merge_short_regions(regions, min_hold_sec)
```

- [ ] **Step 4: Запустить — проходит**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestBuildRegionsFromShots -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Коммит**

```powershell
git add services/worker/app/pipeline/stage3_reframe.py services/worker/tests/unit/test_stage3_reframe.py
git commit -m "feat(reframe): build_regions_from_shots — cut-aligned регионы, режим на план (PURE)"
```

---

## Task 5: Wire-in — переключить `reframe_segment` на cut-aligned путь + интеграционная проверка

**Files:**
- Modify: `services/worker/app/config.py:60-74` (добавить `reframe_wide_ratio`)
- Modify: `services/worker/app/pipeline/stage3_reframe.py` — `reframe_segment` (строки ~456-457) + сигнатура
- Modify: `services/worker/app/run.py:133-140` (пробросить `wide_ratio`)
- Create (временный): `services/worker/tmp/verify_newregions.py`

- [ ] **Step 1: Добавить config-кноб**

В `app/config.py` после строки `reframe_min_hold_sec: float = 1.5` (строка 71) добавить:
```python
    # cut-aligned режим: план "широкий" (fit), если доля широких кадров ≥ wide_ratio.
    reframe_wide_ratio: float = 0.5
```

- [ ] **Step 2: Расширить сигнатуру `reframe_segment`**

В `stage3_reframe.py` в сигнатуре `reframe_segment` (после `min_hold_sec: float = 1.5,`, строка ~419) добавить параметр:
```python
    wide_ratio: float = 0.5,
```

- [ ] **Step 3: Переписать standard-ветку построения регионов**

В `reframe_segment` заменить ДВЕ строки (~456-457):
```python
    trajectory = build_trajectory(face_frames, smoothing, crop_w_frac, mode_setting=mode_setting)
    regions = build_regions(trajectory, min_hold_sec, duration=duration)
```
на:
```python
    cuts = detect_cuts(video, start, end, threshold=cut_threshold)
    shots = build_shots(cuts, duration)
    regions = build_regions_from_shots(
        shots, face_frames, crop_w_frac, smoothing, min_hold_sec,
        mode_setting=mode_setting, wide_ratio=wide_ratio,
    )
```
(`detect_cuts`, `build_shots` уже есть в модуле. Старые `build_trajectory`/`build_regions` остаются для тестов/совместимости — НЕ удалять в этом таске.)

- [ ] **Step 4: Пробросить `wide_ratio` из run.py**

В `app/run.py` в вызове `reframe_segment` (строки 133-140) добавить в строку с `min_hold_sec=...`:
```python
            min_hold_sec=s.reframe_min_hold_sec, wide_ratio=s.reframe_wide_ratio,
```

- [ ] **Step 5: Прогнать ВЕСЬ unit-набор + just check**

Run (из `services/worker`): `uv run pytest tests/unit -q`
Expected: все зелёные (167 прежних + новые из Tasks 1-4).
Run (из корня репо): `just check`
Expected: lint + mypy + tsc + test-unit + anti-drift зелёные.

- [ ] **Step 6: Интеграционная проверка — границы теперь совпадают со склейками**

Создать `services/worker/tmp/verify_newregions.py`:
```python
"""Интеграционная проверка фикса: новые границы режима совпадают с реальными склейками.

Перегенерирует регионы comedy01 clip_01 свежим cut-aligned путём (кэш source, $0) и
сверяет каждую границу режима с ближайшей реальной склейкой. DoD: Δ ≤ 1 кадра.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from app.pipeline.stage3_reframe import detect_cuts, reframe_segment  # noqa: E402

SRC = Path("data/comedy01/source.mp4")
START, END, FPS = 66.005005, 86.74, 25.0


def main() -> None:
    regions, _ = reframe_segment(
        SRC, 1920, 1080, START, END,
        clip_id="verify_newregions", out_dir=Path("tmp"), mode_setting="auto",
    )
    cuts = detect_cuts(SRC, START, END, threshold=0.3)
    print(">> Новые регионы (cut-aligned):")
    for r in regions:
        print(f"     {r.mode:4} {r.t0:7.3f} -> {r.t1:7.3f}")
    print(f">> Реальные склейки: {[round(c, 3) for c in cuts]}\n")
    boundaries = sorted({r.t0 for r in regions if r.t0 > 0.01})
    ok = True
    for b in boundaries:
        nearest = min(cuts, key=lambda c: abs(c - b)) if cuts else 0.0
        df = round((b - nearest) * FPS)
        verdict = "OK" if abs(df) <= 1 else "MISALIGNED"
        if abs(df) > 1:
            ok = False
        print(f"     boundary {b:7.3f}  <-> склейка {nearest:7.3f}  Δ {df:+d} кадров  [{verdict}]")
    print("\n>>", "PASS — все границы на склейках" if ok else "FAIL — есть рассинхрон")


if __name__ == "__main__":
    main()
```
Run (из `services/worker`):
```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
uv run python tmp/verify_newregions.py
```
Expected: каждая граница режима с Δ ≤ 1 кадра от реальной склейки → `PASS`.
**Если FAIL** (детект пропустил склейку → план слишком длинный → граница висит в воздухе): понизить порог — повторить с `REFRAME_CUT_THRESHOLD=0.25`. Если всё ещё мажет — это сигнал, что ffmpeg-scene недостаточно точен; эскалировать (fallback: вернуть PySceneDetect ContentDetector через `uv add scenedetect`, заменить тело `detect_cuts` на scenedetect — но только если ffmpeg-путь не вытянул).

- [ ] **Step 7: Визуальный пруф — рендер Engine B + кадры на границе**

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
$env:REFRAME_ENGINE="B"
uv run python -m app.run comedy01
```
Затем извлечь кадры выходного clip_01 вокруг каждой границы режима (значения t0 из вывода Step 6) и собрать монтаж — убедиться, что на стыке нет кадра со старым кропом (флеша). Пример (подставить реальную границу `B`):
```powershell
$clip = "data\comedy01\clips\clip_01.mp4"
foreach ($t in @(($B-0.08),($B-0.04),$B,($B+0.04),($B+0.08))) {
  ffmpeg -y -loglevel error -ss $t -i $clip -frames:v 1 -vf "scale=360:640" "tmp\b_$([math]::Round($t*1000)).png"
}
```
Глазами свериться по PNG: переход fill↔fit происходит ровно на склейке (контент меняется одновременно с кадрированием), промежуточного «обычного вида» нет.
**DoD:** Δ всех границ ≤ 1 кадра (Step 6 = PASS) И визуально нет флеша на стыке. Показать фаундеру монтаж до/после (`tmp/proof_montage.png` = «до», новый = «после»).

- [ ] **Step 8: Коммит**

```powershell
git add services/worker/app/config.py services/worker/app/pipeline/stage3_reframe.py services/worker/app/run.py
git commit -m "feat(reframe): cut-aligned режим на план — фикс флеша fill<->fit"
```
(`tmp/` в .gitignore — не коммитим.)

---

## Task 6: (ENHANCEMENT, gated) Плавный зум-переход для wide-reveal без склейки

> ⚠️ **ВОРОТА:** Делать ТОЛЬКО после того, как Tasks 1-5 провалидированы фаундером и
> подтверждено, что основной флеш ушёл. Это выбор фаундера (AskUserQuestion) для редкого
> кейса: широкий план нужен ПОСРЕДИ непрерывного шота (нет склейки — напр. объект на весь
> экран во время речи). Tasks 1-5 такой кейс отдают одним режимом на план (без флеша, но
> возможно неоптимально); этот таск делает переход плавным зумом ~0.3с.

**Files:**
- Modify: `services/worker/app/pipeline/stage3_reframe.py` — поле `transition_in` в `TrackRegion`; внутри плана строить под-регионы (старый `build_regions` per-shot) и помечать intra-shot границы как `"zoom"`.
- Modify: `services/worker/app/pipeline/stage5_render.py` — `render_frame_by_frame` интерполирует zoom на `"zoom"`-границе.
- Test: `services/worker/tests/unit/test_stage3_reframe.py`

**Замысел данных:** `TrackRegion` получает `transition_in: str = "hard"`. Inter-shot границы (= склейки) → `"hard"` (мгновенно, невидимо). Intra-shot границы (режим меняется внутри непрерывного плана) → `"zoom"` (анимируем). Поле внутреннее (НЕ в `models.py`, codegen не нужен) — пишется в `reframe_<clip>.json` как есть.

- [ ] **Step 1: Тест на разметку transition_in**

```python
class TestTransitionMarking:
    def test_intra_shot_boundary_is_zoom_inter_shot_is_hard(self) -> None:
        from app.pipeline.stage3_reframe import build_regions_with_transitions

        # один план 0..6 с устойчивой сменой fill->fit ВНУТРИ (без склейки) →
        # граница помечается zoom; стартовый регион — hard.
        shots = [(0.0, 6.0)]
        single = [(0.5, 0.1)]
        wide = [(0.1, 0.1), (0.8, 0.1)]
        raw = [(t / 5, single if t < 15 else wide) for t in range(30)]  # 0..6с, смена на 3с
        regions = build_regions_with_transitions(
            shots, raw, crop_w_frac=0.3, smoothing=0.15, min_hold_sec=1.0
        )
        assert regions[0].transition_in == "hard"
        assert any(r.transition_in == "zoom" for r in regions[1:])
```

- [ ] **Step 2: Запустить — падает**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestTransitionMarking -v`
Expected: FAIL (`cannot import name 'build_regions_with_transitions'`)

- [ ] **Step 3: Добавить поле + функцию**

В `stage3_reframe.py` в `TrackRegion` добавить поле (после `points`):
```python
    transition_in: str = "hard"  # "hard" (склейка, мгновенно) | "zoom" (intra-shot, плавно)
```
Обновить `_write_reframe_json` — добавить `"transition_in": r.transition_in` в dict региона.
Добавить функцию:
```python
def build_regions_with_transitions(
    shots: list[tuple[float, float]],
    raw_samples: list[tuple[float, list[tuple[float, float]]]],
    crop_w_frac: float,
    smoothing: float,
    min_hold_sec: float,
    *,
    mode_setting: str = "auto",
    wide_ratio: float = 0.5,
) -> list[TrackRegion]:
    """Как build_regions_from_shots, но допускает СМЕНУ режима внутри плана с пометкой "zoom".

    Внутри каждого плана строим под-регионы по покадровой геометрии (старый build_regions на
    траектории плана). Границы МЕЖДУ планами (склейки) → transition_in="hard"; границы ВНУТРИ
    плана → "zoom" (рендер анимирует переход). PURE.
    """
    out: list[TrackRegion] = []
    for t0, t1 in shots:
        seg = samples_in_shot(raw_samples, t0, t1)
        traj = build_trajectory(seg, smoothing, crop_w_frac, mode_setting=mode_setting)
        subs = build_regions(traj, min_hold_sec, duration=t1)
        for k, r in enumerate(subs):
            out.append(
                TrackRegion(
                    t0=r.t0, t1=r.t1, mode=r.mode, points=r.points,
                    transition_in="hard" if k == 0 else "zoom",
                )
            )
    return out
```

- [ ] **Step 4: Запустить — проходит**

Run: `uv run pytest tests/unit/test_stage3_reframe.py::TestTransitionMarking -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Engine B — анимировать zoom на "zoom"-границе**

В `stage5_render.py`, `render_frame_by_frame`, в основном цикле заменить выбор кадрирования так, чтобы на первых `round(0.3*fps)` кадрах региона с `transition_in=="zoom"` интерполировать между кадрированием ПРЕДЫДУЩЕГО региона и текущего по eased-параметру. Конкретная реализация (PURE-хелпер + применение):

Добавить PURE-хелпер в `stage5_render.py`:
```python
def ease_in_out(a: float) -> float:
    """Кубический ease-in-out для [0,1]. PURE."""
    a = max(0.0, min(1.0, a))
    return 4 * a * a * a if a < 0.5 else 1 - (-2 * a + 2) ** 3 / 2
```
Тест (в `tests/unit/test_stage5_render.py`, создать класс):
```python
class TestEaseInOut:
    def test_endpoints_and_midpoint(self) -> None:
        from app.pipeline.stage5_render import ease_in_out

        assert ease_in_out(0.0) == 0.0
        assert ease_in_out(1.0) == 1.0
        assert abs(ease_in_out(0.5) - 0.5) < 1e-9
        assert ease_in_out(-1) == 0.0 and ease_in_out(2) == 1.0
```
В цикле `render_frame_by_frame` (Engine B) после `region = _get_region_at(regions, t_clip)`:
```python
            # zoom-переход: первые 0.3с региона с transition_in="zoom" — интерполяция
            zoom_dur = 0.3
            prev = regions[regions.index(region) - 1] if regions.index(region) > 0 else None
            in_zoom = (
                getattr(region, "transition_in", "hard") == "zoom"
                and prev is not None
                and (t_clip - region.t0) < zoom_dur
            )
            if in_zoom and prev is not None:
                a = ease_in_out((t_clip - region.t0) / zoom_dur)
                out_frame = _render_blended(frame, prev, region, a, src_w, src_h, out_w, out_h, ksize)
            elif region.mode == "fit":
                ...  # существующий fit-код
            else:
                ...  # существующий fill-код
```
Добавить `_render_blended` (геометрическая интерполяция source-rect между режимами; PURE-математика окна + cv2-применение):
```python
def _render_blended(frame, prev, region, a, src_w, src_h, out_w, out_h, ksize):
    """Кадр на zoom-переходе: source-rect интерполируется prev->region по a∈[0,1].

    fill → rect = 9:16 окно (crop_w x src_h); fit → rect = весь кадр (src_w x src_h).
    Ширина rect растёт/падает по a; результат вписывается в out с блюр-letterbox по остатку.
    """
    import cv2  # noqa: PLC0415

    def rect_for(reg):
        if reg.mode == "fit":
            return 0.0, float(src_w)  # x, w (вся ширина)
        cx = reg.points[-1].cx if reg.points else 0.5
        c = compute_crop_window(src_w, src_h, cx if cx is not None else 0.5, t=0.0)
        return float(c.x), float(c.w)

    x0, w0 = rect_for(prev)
    x1, w1 = rect_for(region)
    w = w0 + a * (w1 - w0)
    x = x0 + a * (x1 - x0)
    x = max(0.0, min(x, src_w - w))
    sub = frame[0:src_h, int(round(x)) : int(round(x + w))]
    # вписать sub (w x src_h) в out_w x out_h с letterbox
    scale = min(out_w / w, out_h / src_h)
    fw = max(2, int(round(w * scale)));  fw -= fw % 2
    fh = max(2, int(round(src_h * scale)));  fh -= fh % 2
    bg = cv2.GaussianBlur(cv2.resize(frame, (out_w, out_h)), (ksize, ksize), 0)
    fg = cv2.resize(sub, (fw, fh))
    y_off = (out_h - fh) // 2;  x_off = (out_w - fw) // 2
    bg[y_off : y_off + fh, x_off : x_off + fw] = fg
    return bg
```

- [ ] **Step 6: Прогнать тесты + just check**

Run: `uv run pytest tests/unit -q`
Expected: зелёные.
Run (корень): `just check`
Expected: зелёные.

- [ ] **Step 7: Wire — переключить reframe_segment на transitions-вариант (опц.)**

Чтобы включить плавные переходы, в `reframe_segment` заменить вызов `build_regions_from_shots` на `build_regions_with_transitions` (та же сигнатура). Прогнать `REFRAME_ENGINE=B uv run python -m app.run comedy01`, извлечь кадры на intra-shot "zoom"-границе → убедиться, что переход плавный (нет резкого скачка масштаба), inter-shot границы по-прежнему мгновенные.
**DoD:** на видео с wide-reveal внутри плана — плавный отъезд ~0.3с; на склейках — мгновенно; флеша нет нигде. Вердикт — фаундер.

- [ ] **Step 8: Коммит**

```powershell
git add services/worker/app/pipeline/stage3_reframe.py services/worker/app/pipeline/stage5_render.py services/worker/tests/unit/
git commit -m "feat(reframe): плавный zoom-переход для intra-shot wide-reveal (Engine B)"
```

---

## Self-Review (выполнено планнером)

- **Покрытие спеки:** корень флеша (cut-расцепление) закрыт Tasks 1-5 (per-shot mode + cut-aligned границы); выбор фаундера (плавный zoom) — Task 6. ✓
- **Плейсхолдеры:** все шаги с кодом содержат реальный код и команды; «существующий fit/fill-код» в Task 6 Step 5 ссылается на уже присутствующие ветки в `render_frame_by_frame` (строки 217-234). ✓
- **Согласованность типов:** `samples_in_shot`/`decide_shot_mode`/`build_shot_trajectory`/`build_regions_from_shots` используют единый тип сэмплов `list[tuple[float, list[tuple[float, float]]]]` (как `sample_faces_continuous`); `TrackRegion`/`TrackPoint` — существующие. `decide_shot_mode` зовётся с keyword `crop_w_frac=` везде. ✓
- **Риск:** точность `detect_cuts` (ffmpeg-scene). Закрыт DoD Step 6 (Δ≤1 кадра) + явный fallback на PySceneDetect, если порог не вытянет. ✓
- **Граница кода:** вся новая логика PURE (тесты-первыми); I/O (`detect_cuts`) — существующая обёртка с `JobError`. Соответствует CLAUDE.md §«Границы кода». ✓
```
