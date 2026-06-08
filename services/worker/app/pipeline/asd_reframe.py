"""I/O active-speaker reframe: MediaPipe@25fps → дорожки → crop+ASD → центр ГОВОРЯЩЕГО/план.

Lean-путь (BENCHMARKS §6): наш быстрый MediaPipe-детект (не S3FD) кормит 0.84M ASD-модель.
Тяжёлые либы (torch/scipy/mediapipe/cv2/python_speech_features) — ЛЕНИВЫЙ импорт: модуль
импортируется без asd-экстры, но speaker_windows() требует её (REFRAME_SPEAKER=on).

Чистая математика (build_tracks, pick_speaker_centers) — в stage3_speaker (unit-тесты).
Здесь только обёртки I/O; JobError при сбое (правило №8).
"""

from __future__ import annotations

import glob
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from app.errors import JobError
from app.models import CropWindow
from app.pipeline.stage3_reframe import build_shots, compute_crop_window, detect_cuts
from app.pipeline.stage3_speaker import build_tracks, pick_speaker_centers

_STAGE = "reframe"
_FPS = 25
_SILENT = -9.0  # speak-score для дорожки без валидного скора


def _ffmpeg(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise JobError(_STAGE, f"ffmpeg код {proc.returncode}: {(proc.stderr or '')[-300:]}")


def _crop_faces(track: dict[str, Any], frames: list[Any], crop_scale: float) -> np.ndarray:
    """Дорожка → стек кадров лица 224×224 (BGR), in-memory. Логика 1:1 как crop_video LR-ASD."""
    import cv2  # noqa: PLC0415
    from scipy import signal  # noqa: PLC0415

    s = signal.medfilt(np.array([max(d[3] - d[1], d[2] - d[0]) / 2 for d in track["bbox"]]), 13)
    y = signal.medfilt(np.array([(d[1] + d[3]) / 2 for d in track["bbox"]]), 13)
    x = signal.medfilt(np.array([(d[0] + d[2]) / 2 for d in track["bbox"]]), 13)
    out = []
    for i, fr in enumerate(track["frame"]):
        bs = s[i]
        bsi = int(bs * (1 + 2 * crop_scale))
        pad = ((bsi, bsi), (bsi, bsi), (0, 0))
        img = np.pad(frames[int(fr)], pad, "constant", constant_values=110)
        my, mx = y[i] + bsi, x[i] + bsi
        face = img[
            int(my - bs) : int(my + bs * (1 + 2 * crop_scale)),
            int(mx - bs * (1 + crop_scale)) : int(mx + bs * (1 + crop_scale)),
        ]
        out.append(cv2.resize(face, (224, 224)))
    return np.array(out)


def speaker_windows(
    video: Path,
    src_w: int,
    src_h: int,
    start: float,
    end: float,
    *,
    crop_scale: float = 0.55,
) -> list[CropWindow] | None:
    """Сегмент → окна 9:16 по ГОВОРЯЩЕМУ лицу на план (или None, если лиц нет → caller на fallback).

    Шаги: кадры@25fps + аудио → MediaPipe-детект → build_tracks → crop+ASD-score на дорожку →
    detect_cuts/build_shots (D2) → pick_speaker_centers → окна. crop_scale тюним под MediaPipe.
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
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-to",
                str(end),
                "-i",
                str(video),
                "-r",
                str(_FPS),
                "-f",
                "image2",
                str(fdir / "%06d.jpg"),
                "-loglevel",
                "panic",
            ]
        )
        wav = str(Path(td) / "a.wav")
        _ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-to",
                str(end),
                "-i",
                str(video),
                "-ac",
                "1",
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                wav,
                "-loglevel",
                "panic",
            ]
        )
        frames = []
        for fpath in sorted(glob.glob(str(fdir / "*.jpg"))):
            img = cv2.imread(fpath)
            if img is None:
                raise JobError(_STAGE, f"не прочитать кадр {fpath}")
            frames.append(img)
        if not frames:
            return None

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
                        {
                            "frame": i,
                            "bbox": [
                                b.origin_x,
                                b.origin_y,
                                b.origin_x + b.width,
                                b.origin_y + b.height,
                            ],
                        }
                    )
                frame_faces.append(ff)

        tracks = build_tracks(frame_faces)
        if not tracks:
            return None

        sr, audio = wavfile.read(wav)
        scored: list[tuple[float, float, float, float]] = []
        for tr in tracks:
            faces224 = _crop_faces(tr, frames, crop_scale)
            a0, a1 = int(tr["frame"][0] / _FPS * sr), int((tr["frame"][-1] + 1) / _FPS * sr)
            sc = score_track(faces224, audio[a0:a1])
            speak = float(np.mean(sc)) if sc.size else _SILENT
            cx = float(((tr["bbox"][:, 0] + tr["bbox"][:, 2]) / 2).mean() / src_w)
            t0 = float(tr["frame"][0]) / _FPS
            t1 = float(tr["frame"][-1] + 1) / _FPS
            scored.append((t0, t1, cx, speak))

        shots = build_shots(detect_cuts(video, start, end), end - start)
        centers = pick_speaker_centers(scored, shots)
        return [compute_crop_window(src_w, src_h, c, t=t0) for (t0, c) in centers]
