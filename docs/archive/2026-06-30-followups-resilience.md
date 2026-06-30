# Follow-ups: resilience + checkpoints (deferred 2026-06-30)

> Founder asked to record these for later (chose NOT to do them this night). Root-caused via
> read-only recon 2026-06-30. The REPORTED incident ("lost connection with the worker, tried 3×")
> is fixed separately by the frontend reconnect work (calm "bad internet" banner + auto-resume
> polling + don't abandon the live job) — see JOURNAL 2026-06-30. The items below are the BIGGER,
> not-yet-done hardening.

## D — Backend pipeline checkpoints (resume after a WORKER crash)  [DEFERRED — founder's #2]
Different failure mode than the reported one: if a Modal container OOMs / times out / is preempted
mid-pipeline, **nothing restarts it and nothing reaps it** today. Evidence:
- `run_job` / `upload_job` have **`retries` unset → Modal default 0** (no retry/watchdog/stale-job
  reaper anywhere in `services/worker` or `deploy/modal/worker.py`). A crashed job's row stays frozen
  at its last status (e.g. `rendering`, progress 80) forever; the frontend polls a non-terminal status
  indefinitely (spinner that never resolves).
- Even if restarted, `run_pipeline` (`run.py:288`) re-enters at Stage 0 on empty ephemeral disk. Only
  Stage 1 transcript is durable (content-addressed Postgres `transcript_cache`, `run.py:478-524`).
  **Select (Gemini) and reframe would re-run** — Stage 2 writes `segments` to `job_artifacts`
  (`run.py:556`) but `run_pipeline` reads DISK, not the DB, on a fresh container.

**Plan (effort L):**
1. **Trigger a restart:** set `retries=` on `run_job`/`upload_job` (`deploy/modal/worker.py:220-284`)
   AND/OR a scheduled stale-job watchdog that re-dispatches jobs stuck non-terminal past a deadline.
2. **Resume from durable stores:** teach `run_pipeline` to READ BACK what's already persisted instead
   of only ephemeral disk — source from R2 (`run.py:591`), segments from `job_artifacts` (`run.py:556`),
   transcript from the hash-cache (already resumes), and skip already-`set_clip_ready` clips
   (`db.py:245`). Then a restart skips download/transcribe/select and only re-renders missing clips.
- Files: `deploy/modal/worker.py:220-284`, `services/worker/app/run.py:327-573`, `services/worker/app/db.py`.

## C — Upload resilience (resume multipart from completed parts)  [DEFERRED]
Today an upload has **no per-part retry and no resume**: `putPart` rejects immediately on `xhr.onerror`
(`api.ts:114-144`); any one of the 6 parallel parts failing rejects the whole batch; the catch fires
`upload-abort` which **deletes already-uploaded parts from R2** (`api.ts:257-262` → `main.py:466` →
`storage.py:307-316`); `upload_id`+ETags live only in an in-memory closure with **no DB job row until
upload-complete** (`main.py:426`) → a drop or reload = upload from 0%.

**Plan (effort M-L):**
1. Cheap + high value: **per-part retry with backoff** in `putPart`/`uploadParts` (don't abort the whole
   upload because one part blipped).
2. True resume: stop deleting parts on every drop; persist `{job_id, upload_id, part_size, completed[]}`
   (localStorage + ideally a DB row created at `upload-url`); on retry use R2 `ListParts` (new
   `storage.list_parts` helper) to skip parts that already landed.
- Files: `apps/web/lib/api.ts:114-265`, `services/worker/app/main.py:341-446`, `services/worker/app/storage.py:254-316`.

## Minor — Kazakh display-font look (2 weak slots)
`LOOK_MATCH_FOR_CYRILLIC` substitutes are legible everywhere; 2 are weak on LOOK only:
**Archivo Black → Inter** (too thin; try a heavier weight / better Cyrillic-capable black grotesque)
and **Luckiest Guy → Nunito Black** (loses the comic personality; Kazakh-capable comic faces are rare
on permissive licenses). Being addressed in the 2026-06-30 polish pass; if no clearly-better
Kazakh-capable (18/18 glyph) option exists, keep current (legible) and leave this note.
