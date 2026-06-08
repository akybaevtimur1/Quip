"""Инференс active-speaker: дорожка лица (кропы 224×224 BGR @25fps) + аудио → speaking-score.

Логика форварда 1:1 повторяет проверенный спайком путь (BENCHMARKS §6). torch и тяжёлые
либы — ЛЕНИВЫЙ импорт: нужны только при REFRAME_SPEAKER=on; базовый воркер их не тянет.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

_WEIGHT = Path(__file__).resolve().parent / "weights" / "pretrain_AVA.model"
# Несколько временных окон усредняем — стабильнее (как в оригинале LR-ASD).
_DURATIONS = (1, 1, 1, 2, 2, 2, 3, 3, 4, 5, 6)


@lru_cache(maxsize=1)
def _load_net() -> Any:
    """ASD-сеть (model + lossAV + lossV), веса AVA, на CPU. Кэш — грузим один раз на процесс."""
    import torch  # noqa: PLC0415
    from torch import nn  # noqa: PLC0415

    from app.asd._vendor.loss import lossAV, lossV  # noqa: PLC0415
    from app.asd._vendor.Model import ASD_Model  # noqa: PLC0415

    class _Net(nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self.model = ASD_Model()
            self.lossAV = lossAV()
            self.lossV = lossV()

    net = _Net()
    state = net.state_dict()
    loaded = torch.load(str(_WEIGHT), map_location="cpu", weights_only=True)
    for name, param in loaded.items():
        key = name if name in state else name.replace("module.", "")
        if key in state:
            state[key].copy_(param)
    net.eval()
    return net


def score_track(faces224: np.ndarray, audio: np.ndarray) -> np.ndarray:
    """Кропы лица (N,224,224,3 BGR @25fps) + аудио 16kHz mono → speaking-score/кадр (>0=говорит).

    Пустой/слишком короткий вход → нули. Скоры по нескольким окнам усреднены.
    """
    import cv2  # noqa: PLC0415
    import python_speech_features  # noqa: PLC0415
    import torch  # noqa: PLC0415

    if faces224.shape[0] == 0:
        return np.zeros(0, dtype=float)
    vf = np.array([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)[56:168, 56:168] for f in faces224])
    af = python_speech_features.mfcc(audio, 16000, numcep=13, winlen=0.025, winstep=0.010)
    length = min((af.shape[0] - af.shape[0] % 4) / 100, vf.shape[0])
    if length < 1:
        return np.zeros(vf.shape[0], dtype=float)
    af = af[: int(round(length * 100)), :]
    vf = vf[: int(round(length * 25)), :, :]

    net = _load_net()
    all_score = []
    for dur in _DURATIONS:
        batch = int(math.ceil(length / dur))
        sc: list[float] = []
        with torch.no_grad():
            for i in range(batch):
                a = torch.FloatTensor(af[i * dur * 100 : (i + 1) * dur * 100, :]).unsqueeze(0)
                v = torch.FloatTensor(vf[i * dur * 25 : (i + 1) * dur * 25, :, :]).unsqueeze(0)
                embed_a = net.model.forward_audio_frontend(a)
                embed_v = net.model.forward_visual_frontend(v)
                out = net.model.forward_audio_visual_backend(embed_a, embed_v)
                sc.extend(net.lossAV.forward(out, labels=None))
        all_score.append(sc)
    averaged: np.ndarray = np.round(np.array(all_score, dtype=float).mean(axis=0), 1)
    return averaged
