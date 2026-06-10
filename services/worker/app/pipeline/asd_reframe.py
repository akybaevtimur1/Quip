"""I/O active-speaker reframe: MediaPipe@fps → дорожки → crop+ASD → SpeakerTrack[].

Lean-путь (BENCHMARKS §6): наш быстрый MediaPipe-детект (не S3FD) кормит 0.84M ASD-модель.
Тяжёлые либы (torch/scipy/mediapipe/cv2/python_speech_features) — ЛЕНИВЫЙ импорт: модуль
импортируется без asd-экстры, но score_tracks_in_segment() требует её (REFRAME_SPEAKER=on).

Чистая математика (build_tracks) — в stage3_speaker (unit-тесты).
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
from app.pipeline.stage3_reframe import SpeakerTrack
from app.pipeline.stage3_speaker import build_tracks

_STAGE = "reframe"
_SILENT: float = -9.0  # speak-score для дорожки без валидного скора


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
                str(fps),
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
