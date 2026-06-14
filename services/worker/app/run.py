"""CLI E2E: Stage 0→5 для одного источника → клипы + job.json + runs.jsonl.

Запуск:
  uv run python -m app.run <job_id> [<youtube_url>]
  - есть data/<job_id>/source.mp4 → import пропускается (кэш);
  - есть transcript.json/segments.json → стадии 1/2 берутся из кэша (не платим повторно).

Это склейка (план §4А F): вся логика — в pure-функциях стадий, здесь только оркестрация
+ запись статуса/телеметрии. Артефакты — в data/<job_id>/ (см. README).
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from app import db, storage
from app.config import get_settings
from app.errors import JobError
from app.models import ClipOut, Job, JobStatus, Metrics, Segment, Transcript, Word
from app.pipeline.stage0_import import SourceMeta, import_youtube
from app.pipeline.stage1_transcribe import DEEPGRAM_NOVA_USD_PER_MIN, transcribe_to_file
from app.pipeline.stage2_select import select_segments
from app.pipeline.stage3_reframe import reframe_segment
from app.pipeline.stage4_captions import words_in_segment
from app.pipeline.stage5_render import render_clip
from app.transcript_cache import audio_sha, cache_key, evict, get_cached, put_cached

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"  # services/worker/data

# Gemini flash (прибл.): input $0.30/M, output (вкл. thoughts) $2.50/M.
_GEMINI_IN_USD_PER_TOK = 0.30 / 1_000_000
_GEMINI_OUT_USD_PER_TOK = 2.50 / 1_000_000


def _snippet(words: list[Word], start: float, end: float, limit: int = 240) -> str:
    return " ".join(w.text for w in words_in_segment(words, start, end))[:limit]


def _gemini_cost(usage: dict[str, int]) -> float:
    if not usage:
        return 0.0
    out_tok = usage.get("output", 0) + usage.get("thoughts", 0)
    return round(
        usage.get("prompt", 0) * _GEMINI_IN_USD_PER_TOK + out_tok * _GEMINI_OUT_USD_PER_TOK, 4
    )


def run_pipeline(
    job_id: str,
    source_url: str | None = None,
    on_status: Callable[[JobStatus, int], None] | None = None,
    *,
    max_clips: int | None = None,
    on_meta: Callable[[SourceMeta], None] | None = None,
) -> Job:
    """Прогнать весь конвейер для job_id. Возвращает Job (также пишет job.json/runs.jsonl).

    on_status(status, progress) (опц.) вызывается на границах стадий — для статуса в БД (J1).
    max_clips (опц.) — сколько клипов запросил юзер (UI-степпер); None → дефолт из настроек.
    on_meta(meta) (опц.) — вызывается СРАЗУ после импорта (известна реальная длина), ДО
    транскрипции. Поднимет JobError → джоб падает до оплаты Deepgram (гейт квоты по длине).
    """
    s = get_settings()  # fail-fast на отсутствии ключей; также берём reframe_mode
    out = DATA_ROOT / job_id
    out.mkdir(parents=True, exist_ok=True)
    stages: dict[str, float] = {}
    t_start = time.perf_counter()

    def emit(status: JobStatus, progress: int) -> None:
        if on_status is not None:
            on_status(status, progress)

    # ── Stage 0: Import (кэш по наличию source.mp4 + meta.json) ──
    emit(JobStatus.downloading, 10)
    t0 = time.perf_counter()
    meta_path = out / "meta.json"
    if (out / "source.mp4").exists() and meta_path.exists():
        meta = SourceMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
        print(f"[0] import: cached ({meta.duration:.0f}s {meta.width}x{meta.height})")
    elif source_url:
        meta = import_youtube(
            source_url, out, job_id=job_id,
            cookies_browser=s.ytdlp_cookies_browser,
            cookies_file=s.ytdlp_cookies_file,
        )  # fmt: skip
        print(f"[0] import: {meta.duration:.0f}s {meta.width}x{meta.height}")
    else:
        raise JobError("import", f"нет data/{job_id}/source.mp4 и не передан URL")
    stages["download"] = round(time.perf_counter() - t0, 2)

    # ── Гейт квоты по РЕАЛЬНОЙ длине (до оплаты транскрипции). Поднимет JobError → failed,
    #    БЕЗ списания (record_usage идёт только после set_done). ──
    if on_meta is not None:
        on_meta(meta)

    # ── Stage 1: Transcribe (уровень 1: job-local transcript.json; уровень 2: hash-кэш) ──
    emit(JobStatus.transcribing, 35)
    t0 = time.perf_counter()
    tr_path = out / "transcript.json"
    transcribe_cost = 0.0
    cache_dir = DATA_ROOT / "_cache" / "transcripts"

    if tr_path.exists():
        # Level 1: job-local cache (same job_id re-run)
        transcript = Transcript.model_validate_json(tr_path.read_text(encoding="utf-8"))
        print(f"[1] transcribe: cached/local ({len(transcript.words)} words)")
    else:
        wav_path = out / "source.wav"
        # Level 2: content-addressed cache (same audio, different job_id).
        # cloud (Postgres transcript_cache) durable между Modal-контейнерами; локально диск.
        cached_tr: Transcript | None = None
        sha: str | None = None
        ck: str | None = None
        if s.transcript_cache_enabled:
            sha = audio_sha(wav_path)
            ck = cache_key(sha, s.transcription_provider, s.deepgram_model)
            cloud_tr = db.get_cached_transcript(sha, s.transcription_provider, s.deepgram_model)
            cached_tr = (
                Transcript.model_validate(cloud_tr)
                if cloud_tr is not None
                else get_cached(cache_dir, ck)
            )

        if cached_tr is not None:
            transcript = cached_tr
            tr_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
            print(f"[1] transcribe: cached/hash ({len(transcript.words)} words, $0)")
        else:
            transcript = transcribe_to_file(wav_path, tr_path)
            transcribe_cost = round(transcript.duration / 60 * DEEPGRAM_NOVA_USD_PER_MIN, 4)
            print(f"[1] transcribe: {len(transcript.words)} words (${transcribe_cost})")
            if s.transcript_cache_enabled and ck is not None:
                put_cached(cache_dir, ck, transcript)
                evict(
                    cache_dir,
                    max_entries=s.transcript_cache_max_entries,
                    max_age_days=s.transcript_cache_max_age_days,
                )
            if s.transcript_cache_enabled and sha is not None:
                db.put_cached_transcript(
                    sha, s.transcription_provider, s.deepgram_model, transcript.model_dump()
                )
    stages["transcription"] = round(time.perf_counter() - t0, 2)

    # ── Stage 2: Select (кэш по segments.json) ──
    emit(JobStatus.selecting, 60)
    t0 = time.perf_counter()
    seg_path = out / "segments.json"
    usage: dict[str, int] = {}
    if seg_path.exists():
        segments = [
            Segment.model_validate(x) for x in json.loads(seg_path.read_text(encoding="utf-8"))
        ]
        print(f"[2] select: cached ({len(segments)} segments)")
    else:
        segments = select_segments(transcript, meta.title, max_clips=max_clips, usage_sink=usage)
        seg_path.write_text(
            json.dumps([s.model_dump() for s in segments], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[2] select: {len(segments)} segments")
    stages["llm_select"] = round(time.perf_counter() - t0, 2)
    select_cost = _gemini_cost(usage)

    # ── Stages 3–5: per-clip (reframe → captions → render) ──
    emit(JobStatus.rendering, 80)
    clips: list[ClipOut] = []
    reframe_t = 0.0
    render_t = 0.0
    ttfc: float | None = None
    for i, seg in enumerate(segments, start=1):
        clip_id = f"clip_{i:02d}"
        t0 = time.perf_counter()
        regions, face_found = reframe_segment(
            out / "source.mp4", meta.width, meta.height, seg.start, seg.end,
            clip_id=clip_id, out_dir=out, fps=meta.fps, mode_setting=s.reframe_mode,
            speaker_crop_scale=s.reframe_speaker_crop_scale,
            face_fps=s.reframe_face_fps, smoothing=s.reframe_smoothing,
            min_hold_sec=s.reframe_min_hold_sec,
            speak_threshold=s.reframe_speak_threshold,
            scene_threshold=s.reframe_scene_threshold,
            split_enabled=s.reframe_split_enabled,
        )  # fmt: skip
        reframe_t += time.perf_counter() - t0
        lat = render_clip(
            out, "source.mp4", seg.start,
            f"clips/{clip_id}.mp4",
            regions=regions, src_w=meta.width, src_h=meta.height, fps=meta.fps,
            engine=s.reframe_engine,
        )  # fmt: skip
        render_t += lat
        if ttfc is None:
            ttfc = round(time.perf_counter() - t_start, 2)
        clips.append(
            ClipOut(
                id=clip_id,
                start=seg.start,
                end=seg.end,
                duration=round(seg.end - seg.start, 2),
                reason=seg.reason,
                type=seg.type,
                score=seg.score,
                # local → "clips/<id>.mp4" (раздаётся на /media); r2 → публичный/presigned URL.
                video_url=storage.upload_clip(out / "clips" / f"{clip_id}.mp4", job_id, clip_id),
                thumbnail_url=None,
                transcript=_snippet(transcript.words, seg.start, seg.end),
                words=words_in_segment(transcript.words, seg.start, seg.end),
                hook=seg.hook,
                why_works=seg.why_works,
            )
        )
        n_fit = sum(1 for r in regions if r.mode == "fit")
        print(
            f"  {clip_id}: {seg.start:.1f}-{seg.end:.1f} face={face_found} "
            f"regions={len(regions)} fit={n_fit} render={lat}s"
        )
    stages["reframe"] = round(reframe_t, 2)
    stages["render"] = round(render_t, 2)

    # ── persist для облака (Modal): источник в R2 (редактор-рендер на другом контейнере) +
    #    артефакты (meta/segments/transcript) в Postgres job_artifacts. Локально оба = no-op. ──
    storage.upload_source(out / "source.mp4", job_id)
    db.put_job_artifacts(
        job_id,
        meta.model_dump(),
        [seg.model_dump() for seg in segments],
        transcript.model_dump(),
    )

    # ── job.json (wire-контракт) ──
    total_sec = round(time.perf_counter() - t_start, 2)
    total_usd = round(transcribe_cost + select_cost, 4)
    job = Job(
        id=job_id,
        status=JobStatus.done,
        stage=JobStatus.done,
        progress=100,
        source_kind=meta.source,
        clips=clips,
        metrics=Metrics(cost_usd=total_usd, duration_sec=meta.duration, elapsed_sec=total_sec),
    )
    (out / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")

    # ── runs.jsonl (телеметрия экономики) ──
    run_line = {
        "run_id": job_id,
        "source_minutes": round(meta.duration / 60, 2),
        "stages": stages,
        "total_sec": total_sec,
        "total_usd": total_usd,
        "n_clips": len(clips),
        "time_to_first_clip_sec": ttfc,
    }
    with (DATA_ROOT / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(run_line, ensure_ascii=False) + "\n")

    print(f"\nDONE: {len(clips)} clips, total ${total_usd}, {total_sec}s -> data/{job_id}/")
    return job


def main() -> None:
    args = sys.argv[1:]
    job_id = args[0] if args else "sample01"
    source_url = args[1] if len(args) > 1 else None
    run_pipeline(job_id, source_url)


if __name__ == "__main__":
    main()
