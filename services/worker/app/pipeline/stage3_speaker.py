"""Pure-логика active-speaker reframe: IOU-трекинг лиц.

Детект лиц (MediaPipe) и speaking-score (app.asd.scorer) — это I/O-обёртки в asd_reframe.py.
Здесь только детерминированная математика (только numpy) → гоняется в базовом гейте без asd-экстры.

build_tracks: per-frame face detections → IOU-треки с интерполяцией дыр (жадный).
"""

from __future__ import annotations

from typing import Any

import numpy as np


def should_score_asd(n_tracks: int) -> bool:
    """Нужен ли ASD speak-score для этого сегмента. PURE (perf #2).

    ASD-скор используется ТОЛЬКО для выбора говорящего СРЕДИ нескольких дорожек
    (``_pick_target`` max-speak, ``_is_wide_shot`` и ``wide_speak_min`` — все требуют ≥2 active
    дорожки в шоте). При 0–1 дорожке говорящий однозначен → дорогой crop+torch-форвард не влияет
    на регионы (и max-speak, и fallback-by-width вернут ту же единственную дорожку). Пропуская
    его, экономим ~половину времени reframe на одно-спикерных клипах. НЕ трогает геометрию
    (склейки/шоты/границы) — инвариант docs/REFRAME_FPS_GRID_INVARIANT.md цел.
    """
    return n_tracks >= 2


def _iou(a: list[float], b: list[float]) -> float:
    """IOU двух bbox [x1,y1,x2,y2]."""
    x_a, y_a = max(a[0], b[0]), max(a[1], b[1])
    x_b, y_b = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x_b - x_a) * max(0.0, y_b - y_a)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter + 1e-9)


def build_tracks(
    frame_faces: list[list[dict[str, Any]]],
    *,
    num_failed_det: int = 10,
    min_track: int = 10,
    min_face: int = 1,
    iou_thres: float = 0.5,
) -> list[dict[str, Any]]:
    """Per-frame детекты лиц → дорожки (жадный IOU-трекинг + интерполяция дыр bbox).

    frame_faces: по кадрам, каждый — список {"frame": int, "bbox": [x1,y1,x2,y2]}.
    Возвращает дорожки {"frame": np.ndarray(int), "bbox": np.ndarray(N,4)}. Логика 1:1 как в
    LR-ASD (track_shot), но scipy.interp1d заменён numpy.interp (без scipy в базовом гейте).
    """
    scene = [list(ff) for ff in frame_faces]  # мутируем копию
    tracks: list[dict[str, Any]] = []
    while True:
        track: list[dict[str, Any]] = []
        for frame in scene:
            for face in frame:
                if not track:
                    track.append(face)
                    frame.remove(face)
                elif face["frame"] - track[-1]["frame"] <= num_failed_det:
                    if _iou(face["bbox"], track[-1]["bbox"]) > iou_thres:
                        track.append(face)
                        frame.remove(face)
                else:
                    break
        if not track:
            break
        if len(track) <= min_track:
            continue
        fn = np.array([f["frame"] for f in track])
        bb = np.array([f["bbox"] for f in track], dtype=float)
        fi = np.arange(fn[0], fn[-1] + 1)
        bbi = np.stack([np.interp(fi, fn, bb[:, j]) for j in range(4)], axis=1)
        if max((bbi[:, 2] - bbi[:, 0]).mean(), (bbi[:, 3] - bbi[:, 1]).mean()) > min_face:
            tracks.append({"frame": fi, "bbox": bbi})
    return tracks
