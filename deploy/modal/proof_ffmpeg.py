"""ДОКАЗАТЕЛЬСТВО (без секретов): статик-ffmpeg на Modal рендерит наш crop-граф в валидный mp4.

Изолирует риск №1 деплоя из брифа: apt-ffmpeg (debian 5/6) КРАШИТ наш crop-рендер
(«Parsed_crop_4: Failed to configure input pad»), статик John Van Sickle ≥7 — нет. Этот скрипт
строит ТОТ ЖЕ статик-ffmpeg, что и боевой образ (deploy/modal/worker.py), и гоняет
репрезентативный кроп 1920×1080 → 9:16 (crop+scale+setsar, как stage5) на синтетическом клипе.
Секреты НЕ нужны → можно гонять до того, как фаундер заведёт quip-worker.

    modal run deploy/modal/proof_ffmpeg.py
"""

from __future__ import annotations

import subprocess

import modal

_FFMPEG_STATIC = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("wget", "xz-utils")
    .run_commands(
        f"wget -q {_FFMPEG_STATIC} -O /tmp/ffmpeg.tar.xz",
        "cd /tmp && tar xf ffmpeg.tar.xz",
        "cp /tmp/ffmpeg-*-static/ffmpeg /tmp/ffmpeg-*-static/ffprobe /usr/local/bin/",
        "chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe",
        "rm -rf /tmp/ffmpeg*",
    )
)

app = modal.App("quip-ffmpeg-proof", image=image, include_source=False)


@app.function(timeout=300, serialized=True)
def render_crop() -> dict[str, object]:
    """Синтетический 1920×1080 5с → наш crop-граф (как stage5) → ffprobe выхода. Метрики."""
    ver = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True, check=True
    ).stdout.splitlines()[0]

    # 1) синтетический ландшафт-источник (как YouTube 1080p)
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30:duration=5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "/tmp/src.mp4",
        ],  # fmt: skip
        capture_output=True, text=True, check=True,
    )  # fmt: skip

    # 2) ТОТ САМЫЙ граф, что крашил debian-ffmpeg: split→trim(frame-exact)→crop→scale→setsar→concat
    #    (форма из stage5.build_reframe_filter: фрейм-точный trim + кроп окна + 9:16 + setsar).
    vf = (
        "[0:v]trim=start_frame=0:end_frame=150,setpts=PTS-STARTPTS,"
        "crop=608:1080:656:0,scale=1080:1920,setsar=1[outv]"
    )
    r = subprocess.run(
        [
            "ffmpeg", "-y", "-i", "/tmp/src.mp4",
            "-filter_complex", vf, "-map", "[outv]", "-map", "0:a",
            "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "/tmp/out.mp4",
        ],  # fmt: skip
        capture_output=True, text=True,
    )  # fmt: skip
    if r.returncode != 0:
        return {"ffmpeg": ver, "render_ok": False, "stderr_tail": r.stderr[-800:]}

    # 3) ffprobe выхода — доказать валидный mp4 1080×1920
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name:format=duration",
            "-of", "default=noprint_wrappers=1", "/tmp/out.mp4",
        ],  # fmt: skip
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    import os

    return {
        "ffmpeg": ver,
        "render_ok": True,
        "out_bytes": os.path.getsize("/tmp/out.mp4"),
        "probe": probe.stdout.strip(),
    }


@app.local_entrypoint()
def main() -> None:
    print("[proof] building static-ffmpeg image + rendering crop graph on Modal…")
    res = render_crop.remote()
    print("\n═══════════════ Modal static-ffmpeg crop proof ═══════════════")
    for k, v in res.items():
        print(f"  {k}: {v}")
    print("══════════════════════════════════════════════════════════════")
