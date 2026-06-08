"""Pure-логика active-speaker reframe: IOU-трекинг лиц + выбор ГОВОРЯЩЕЙ дорожки на план.

Детект лиц (MediaPipe) и speaking-score (app.asd.scorer) — это I/O-обёртки в stage3_reframe.
Здесь только детерминированная математика (только numpy) → гоняется в базовом гейте без asd-экстры.

Граница с D2: shots приходят из detect_cuts/build_shots; здесь на каждый план выбираем
дорожку с макс. speaking-score → её центр (вместо «самого крупного лица»). Опора на argmax,
а не на абсолютный порог — нам нужен лишь «кто из лиц говорит громче» в плане.
"""

from __future__ import annotations

from typing import Any

import numpy as np


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


def pick_speaker_centers(
    tracks: list[tuple[float, float, float, float]],
    shots: list[tuple[float, float]],
    *,
    default: float = 0.5,
) -> list[tuple[float, float]]:
    """Дорожки (t_start, t_end, center_x_frac, speak) + планы (s0,s1) → [(shot_start, center)].

    На каждый план берём дорожку с МАКС. speak среди пересекающих план → её центр (кадрируем
    на говорящего, а не на крупнейшего). Нет дорожек в плане → держим центр предыдущего плана
    (первый без дорожек → default). Совместимо с D2: даём по одному центру на план.
    """
    out: list[tuple[float, float]] = []
    prev = default
    for s0, s1 in shots:
        cands = [(c, sp) for (t0, t1, c, sp) in tracks if t0 < s1 and t1 > s0]
        center = max(cands, key=lambda cs: cs[1])[0] if cands else prev
        out.append((s0, center))
        prev = center
    return out
