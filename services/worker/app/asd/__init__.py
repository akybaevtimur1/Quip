"""Active-speaker detection (ASD): кто из лиц на экране говорит.

`_vendor/` — ядро модели LR-ASD (MIT, https://github.com/Junhua-Liao/LR-ASD, см. LICENSE),
0.84M параметров, обучено на AVA-ActiveSpeaker. `scorer.py` — наша тонкая инференс-обёртка.
Детект лиц делаем СВОИМ MediaPipe (не вендорим тяжёлый S3FD — см. docs/BENCHMARKS.md §6).
Используется только при REFRAME_SPEAKER=on (ленивый импорт torch).
"""
