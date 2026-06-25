"use client";

import { Plus } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { AppHeader } from "@/components/app/AppHeader";
import { PromoRedeem } from "@/components/app/PromoRedeem";
import { RecentProjects } from "@/components/app/RecentProjects";
import { UsageMeter } from "@/components/app/UsageMeter";
import { ClipGrid } from "@/components/ClipGrid";
import { CoWatchPanel } from "@/components/CoWatchPanel";
import { VideoMap } from "@/components/VideoMap";
import { ErrorPanel } from "@/components/ErrorPanel";
import { JobProgress } from "@/components/JobProgress";
import { SourceForm } from "@/components/SourceForm";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Spinner } from "@/components/ui/Spinner";
import { Split } from "@/components/ui/Split";
import { cancelJob, createJob, createUploadJob } from "@/lib/api";
import {
  addRecentProject,
  type JobStatusLite,
  markReviewed,
  updateRecentProject,
} from "@/lib/recent";
import { useJob } from "@/lib/useJob";

/** Friendly label for the recent-projects list (no PII, just a hint). */
function labelFromUrl(url: string): string {
  try {
    const u = new URL(url);
    const v = u.searchParams.get("v");
    if (v) return `YouTube · ${v}`;
    return u.hostname.replace(/^www\./, "") + u.pathname.slice(0, 22);
  } catch {
    return url.slice(0, 40) || "Project";
  }
}

/** Shown the instant a file upload starts (before bytes even move) so a big upload
 *  never looks frozen. Real % comes from XHR upload-progress events. Leads with a big
 *  mono % readout + a determinate bar — no icon-in-circle. */
function UploadProgress({ pct }: { pct: number }) {
  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="flex items-end justify-between gap-4 border-b border-line pb-4">
        <div>
          <Eyebrow tone="accent">Uploading</Eyebrow>
          <h2 className="mt-1.5 font-display text-h3 text-ink">
            {pct < 100 ? "Sending your video" : "Getting it ready"}
          </h2>
        </div>
        <div className="text-right" aria-live="polite">
          <Numeral className="block text-display-lg font-semibold leading-none text-ink">
            {pct}
          </Numeral>
          <Eyebrow tone="faint" className="mt-1 block">
            percent
          </Eyebrow>
        </div>
      </div>
      <div className="mt-5 h-1 overflow-hidden rounded-pill bg-surface-3">
        <div
          className="h-full rounded-pill bg-accent transition-[width] duration-200 ease-out"
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
      <p className="mt-3 text-xs leading-relaxed text-faint">
        {pct < 100
          ? "Large files take a moment — keep this tab open while the bytes move."
          : "Upload complete — handing off to processing."}
      </p>
    </div>
  );
}

function DashboardInner() {
  const router = useRouter();
  const { job, jobId, error: pollError, elapsed, start, reset } = useJob();
  const [submitting, setSubmitting] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Requested clip count (from the form) → drives the reserved skeleton count while processing.
  const [requestedClips, setRequestedClips] = useState(3);
  // Local object URL of the just-uploaded file → the co-watch plays the user's OWN video
  // INSTANTLY (no upload round-trip / CORS) while the AI works. Only set for uploads in this
  // same session; gone after reload (then we fall back to the stepper). YouTube → null.
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  useEffect(() => {
    // Revoke the blob URL when it changes or on unmount — don't leak object URLs.
    return () => {
      if (sourceUrl) URL.revokeObjectURL(sourceUrl);
    };
  }, [sourceUrl]);
  const error = submitError ?? pollError;
  // In-flight upload controller — abort on reset / unmount / new submit. Без этого брошенная
  // загрузка (ушёл со страницы / «Новый проект» / залил второй раз) продолжала XHR: создавала
  // лишний джоб на воркере, а её поздний resolve перетирал UI (дубли джоб, скачущий прогресс).
  const uploadCtrl = useRef<AbortController | null>(null);
  useEffect(() => () => uploadCtrl.current?.abort(), []); // unmount → отменить загрузку

  // Deep-link: open an existing job via ?job=<id>. Reactive to the query param so
  // navigating from /dashboard to /dashboard?job=X (e.g. clicking a recent project
  // while already on the dashboard) loads it immediately — no manual refresh. The
  // mount-only effect missed this: same route + new query doesn't remount the page.
  const jobParam = useSearchParams().get("job");
  useEffect(() => {
    if (jobParam) start(jobParam);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobParam]);

  // Keep the recent-projects entry in sync with the live job: cache the latest status +
  // clip count (so the list shows "Processing… / Ready · N clips" instantly), and mark the
  // job reviewed once its results are on screen (clears the "New" badge). updateRecentProject
  // is a no-op when nothing changed, so this is cheap.
  useEffect(() => {
    if (!job) return;
    updateRecentProject(job.id, {
      status: job.status as JobStatusLite,
      nclips: job.clips?.length || undefined,
    });
    if (job.status === "done") markReviewed(job.id);
  }, [job?.id, job?.status, job?.clips?.length]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit(url: string, maxClips: number) {
    if (submitting) return; // guard: не плодим параллельные джобы двойным сабмитом
    setSubmitError(null);
    setSubmitting(true);
    setRequestedClips(maxClips);
    try {
      const { id } = await createJob({ source_type: "youtube", source_ref: url, max_clips: maxClips });
      addRecentProject({ id, label: labelFromUrl(url), at: Date.now() });
      setSourceUrl(null); // YouTube → no local file to co-watch (falls back to the stepper)
      start(id);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Couldn’t create project");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmitFile(file: File, maxClips: number) {
    if (submitting) return; // guard двойного сабмита (форма и так дизейблится — belt+braces)
    uploadCtrl.current?.abort(); // отменить прежнюю незавершённую загрузку перед новой
    const ctrl = new AbortController();
    uploadCtrl.current = ctrl;
    setSubmitError(null);
    setSubmitting(true);
    setRequestedClips(maxClips);
    setUploadPct(0); // show the uploading screen immediately, before bytes move
    try {
      const { id } = await createUploadJob(file, maxClips, setUploadPct, ctrl.signal);
      if (ctrl.signal.aborted) return; // отменена/вытеснена — не трогаем стейт
      setUploadPct(null);
      addRecentProject({ id, label: file.name, at: Date.now() });
      setSourceUrl(URL.createObjectURL(file)); // co-watch plays THIS file instantly while AI works
      start(id);
    } catch (e) {
      // намеренная отмена (reset/unmount/новый сабмит) → НЕ показываем ошибку
      if (ctrl.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) return;
      setUploadPct(null);
      setSubmitError(e instanceof Error ? e.message : "Couldn’t upload file");
    } finally {
      if (uploadCtrl.current === ctrl) {
        uploadCtrl.current = null;
        setSubmitting(false);
      }
    }
  }

  async function handleStop() {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
    } catch (e) {
      // 409 (already in a paid stage) or network error → surface, don't reset (job keeps going).
      setSubmitError(e instanceof Error ? e.message : "Couldn’t stop this video.");
      return;
    }
    handleReset(); // back to idle; the recent-projects entry is kept (added at submit time)
  }

  function handleReset() {
    uploadCtrl.current?.abort(); // отменить незавершённую загрузку — иначе она позже войдёт в tracking
    uploadCtrl.current = null;
    reset();
    setSubmitError(null);
    setSubmitting(false);
    setUploadPct(null);
    setSourceUrl(null); // drop the co-watch source (effect revokes the blob URL)
    // Drop ?job= so a deep-linked project doesn't keep us out of the idle "New project"
    // form (phase below treats a present ?job= as loading). Without this, reset couldn't
    // return to idle when the URL still carried the job id.
    if (jobParam) router.replace("/dashboard");
  }

  // `jobId` (set the moment a job starts) keeps us in "tracking" through the gap between submit
  // and the first status poll — otherwise the dashboard flashed back for a beat (worst on a Modal
  // cold start) before the first poll populated `job`.
  // `jobParam`: a deep-link (e.g. editor's "All clips" → /dashboard?job=X) must NOT flash the idle
  // "Create clips" form before the load effect runs. Treating a present ?job= as loading keeps us
  // out of idle until the job resolves to its grid (done) — fixes "All clips lands on the dashboard".
  const phase = error
    ? "error"
    : job?.status === "done"
      ? "done"
      : job?.status === "cancelled"
        ? "cancelled" // user stopped it (or deep-linked a stopped job) → neutral panel, not a loader
        : submitting || jobId || jobParam
          ? "tracking"
          : "idle";
  // Opening an existing project via deep-link, before the first poll populates `job`: show a neutral
  // loader (not the JobProgress stepper, which implies "still processing" for an already-done clip).
  const openingProject = !!jobParam && !job && !submitting;
  // Progressive results: the worker populates job.clips (metadata for ALL clips) while still
  // rendering — clips with a video_url are ready, the rest carry empty video_url. The moment any
  // clip exists we swap the bare stepper for the grid so the user can read hooks/reasons and start
  // editing ready clips while the rest finish. Early phases (queued…selecting) have no clips yet →
  // the stepper still shows.
  const showProgressiveGrid = phase === "tracking" && !openingProject && (job?.clips?.length ?? 0) > 0;

  return (
    <div className="min-h-dvh">
      <AppHeader />
      <main className="mx-auto max-w-[1200px] px-5 py-10 sm:px-8 sm:py-12">
        {phase !== "idle" && (
          <button
            onClick={handleReset}
            className="mb-6 inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-sm text-muted transition hover:border-line-strong hover:text-ink"
          >
            <Plus className="size-4" />
            New project
          </button>
        )}

        {phase === "idle" ? (
          // Instrument console: an intake protagonist on the left, a calibrated readout rail
          // on the right (unequal weight). Stacks on mobile via Split.
          <Split variant="main-rail">
            <section>
              <Eyebrow tone="faint">New project</Eyebrow>
              <h1 className="mt-2 font-display text-h2 text-ink sm:text-display-lg">Create clips</h1>
              <p className="mt-3 max-w-md text-lead text-muted">
                Drop a video. Quip finds the strongest moments, cuts vertical clips, and reports a
                confidence score and why each one works.
              </p>
              <div className="mt-8">
                <SourceForm onSubmit={handleSubmit} onSubmitFile={handleSubmitFile} busy={submitting} />
              </div>
            </section>
            {/* readout rail — meter (primary), recents (secondary), promo (tertiary) */}
            <aside className="space-y-5">
              <UsageMeter />
              <RecentProjects />
              <PromoRedeem />
            </aside>
          </Split>
        ) : uploadPct !== null ? (
          <UploadProgress pct={uploadPct} />
        ) : showProgressiveGrid && job ? (
          // Progressive grid: clips render in as they finish. Same <ClipGrid key={job.id}> as the
          // done branch → flipping to "done" doesn't remount (no flicker, selection preserved).
          <ClipGrid key={job.id} job={job} />
        ) : phase === "tracking" ? (
          // Centered (mx-auto on each panel) so the transient upload/processing screens don't sit
          // jammed against the left edge with a dead right half (founder call). Idle + done fill width.
          openingProject ? (
            <div className="flex items-center justify-center gap-3 py-10">
              <Spinner size="md" className="text-accent" />
              <p className="text-sm text-muted">Opening your project…</p>
            </div>
          ) : sourceUrl && jobId ? (
            // Co-watch: the uploaded file plays instantly while the AI reads it and real
            // moments light up. Falls back to the stepper for YouTube / after a reload.
            <CoWatchPanel
              jobId={jobId}
              src={sourceUrl}
              status={job?.status ?? "queued"}
              elapsed={elapsed}
              cancellable={job?.cancellable ?? false}
              onStop={handleStop}
            />
          ) : (
            <JobProgress
              status={job?.status ?? "queued"}
              elapsed={elapsed}
              progress={job?.progress ?? null}
              cancellable={job?.cancellable ?? false}
              onStop={handleStop}
              sourceMinutes={job?.source_minutes ?? null}
              transcriptWords={job?.transcript_words ?? null}
              momentsFound={job?.moments_found ?? null}
              requestedClips={requestedClips}
            />
          )
        ) : phase === "done" && job ? (
          <>
            <VideoMap jobId={job.id} clips={job.clips ?? []} />
            <ClipGrid key={job.id} job={job} />
          </>
        ) : phase === "cancelled" ? (
          <div className="mx-auto max-w-xl">
            <Eyebrow tone="faint">Run stopped</Eyebrow>
            <h2 className="mt-2 font-display text-h3 text-ink">This project was stopped</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              You stopped processing before it finished. Nothing was charged — start a new project
              whenever you’re ready.
            </p>
          </div>
        ) : phase === "error" && error ? (
          <ErrorPanel message={error} onRetry={handleReset} />
        ) : null}
      </main>
    </div>
  );
}

// useSearchParams() requires a Suspense boundary (Next App Router). The shell renders
// instantly; the tool hydrates inside.
export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-dvh">
          <AppHeader />
        </div>
      }
    >
      <DashboardInner />
    </Suspense>
  );
}
