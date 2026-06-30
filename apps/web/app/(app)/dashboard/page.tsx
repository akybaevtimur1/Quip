"use client";

import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { AppHeader } from "@/components/app/AppHeader";
import { PromoRedeem } from "@/components/app/PromoRedeem";
import { RecentProjects } from "@/components/app/RecentProjects";
import { UsageMeter } from "@/components/app/UsageMeter";
import { ClipGrid } from "@/components/ClipGrid";
import { VideoMap } from "@/components/VideoMap";
import { ErrorPanel } from "@/components/ErrorPanel";
import { JobProgress } from "@/components/JobProgress";
import { ReconnectBanner } from "@/components/ReconnectBanner";
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
 *  mono % readout + a determinate bar while bytes move.
 *
 *  At 100% the bytes are up but the worker is still finalizing the multipart upload + creating the
 *  job (the `upload-complete` round-trip) BEFORE status polling can begin — a window with no server
 *  progress to show. A full, static bar there reads as frozen (the L5 "silent gap"), so we flip to
 *  an explicit, animated "Preparing your video…" state (spinner + indeterminate bar) until
 *  `createUploadJob` resolves and the live status view (the JobProgress stepper) takes over. */
function UploadProgress({ pct }: { pct: number }) {
  const t = useTranslations("dashboard");
  const preparing = pct >= 100;
  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="flex items-end justify-between gap-4 border-b border-line pb-4">
        <div>
          <Eyebrow tone="accent">{preparing ? t("preparing") : t("uploading")}</Eyebrow>
          <h2 className="mt-1.5 font-display text-h3 text-ink">
            {preparing ? t("preparingVideo") : t("sendingVideo")}
          </h2>
        </div>
        <div className="flex items-center justify-end text-right" aria-live="polite">
          {preparing ? (
            <Spinner size="lg" className="text-accent" />
          ) : (
            <div>
              <Numeral className="block text-display-lg font-semibold leading-none text-ink">
                {pct}
              </Numeral>
              <Eyebrow tone="faint" className="mt-1 block">
                {t("percent")}
              </Eyebrow>
            </div>
          )}
        </div>
      </div>
      <div className="mt-5 h-1 overflow-hidden rounded-pill bg-surface-3">
        <div
          className={
            preparing
              ? "h-full w-full rounded-pill bg-accent motion-safe:animate-pulse"
              : "h-full rounded-pill bg-accent transition-[width] duration-200 ease-out"
          }
          style={preparing ? undefined : { width: `${Math.max(2, pct)}%` }}
        />
      </div>
      <p className="mt-3 text-xs leading-relaxed text-faint">
        {preparing ? t("uploadHintPreparing") : t("uploadHintSending")}
      </p>
    </div>
  );
}

function DashboardInner() {
  const t = useTranslations("dashboard");
  const router = useRouter();
  const { job, jobId, error: pollError, reconnecting, elapsed, start, reset, reconnectNow } = useJob();
  const [submitting, setSubmitting] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Requested clip count (from the form) → drives the reserved skeleton count while processing.
  const [requestedClips, setRequestedClips] = useState(3);
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
      start(id);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : t("errors.create"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmitFile(file: File, maxClips: number, language: string | null = null) {
    if (submitting) return; // guard двойного сабмита (форма и так дизейблится — belt+braces)
    uploadCtrl.current?.abort(); // отменить прежнюю незавершённую загрузку перед новой
    const ctrl = new AbortController();
    uploadCtrl.current = ctrl;
    setSubmitError(null);
    setSubmitting(true);
    setRequestedClips(maxClips);
    setUploadPct(0); // show the uploading screen immediately, before bytes move
    try {
      const { id } = await createUploadJob(file, maxClips, setUploadPct, ctrl.signal, language);
      if (ctrl.signal.aborted) return; // отменена/вытеснена — не трогаем стейт
      setUploadPct(null);
      addRecentProject({ id, label: file.name, at: Date.now() });
      start(id);
    } catch (e) {
      // намеренная отмена (reset/unmount/новый сабмит) → НЕ показываем ошибку
      if (ctrl.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) return;
      setUploadPct(null);
      setSubmitError(e instanceof Error ? e.message : t("errors.upload"));
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
      setSubmitError(e instanceof Error ? e.message : t("errors.stop"));
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
        : reconnecting
          ? "reconnecting" // a connectivity blip — calm banner, NOT the red error panel; job's alive
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
            {t("newProject")}
          </button>
        )}

        {phase === "idle" ? (
          // Instrument console: an intake protagonist on the left, a calibrated readout rail
          // on the right (unequal weight). Stacks on mobile via Split.
          <Split variant="main-rail">
            <section>
              <Eyebrow tone="faint">{t("newProject")}</Eyebrow>
              <h1 className="mt-2 font-display text-h2 text-ink sm:text-display-lg">
                {t("createClips")}
              </h1>
              <p className="mt-3 max-w-md text-lead text-muted">{t("intro")}</p>
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
        ) : phase === "reconnecting" ? (
          // Connectivity blip: the job keeps processing server-side, so we show a calm reconnect
          // banner (NOT the red ErrorPanel) and keep any clips that already arrived usable below.
          (job?.clips?.length ?? 0) > 0 && job ? (
            <>
              <ReconnectBanner onRetry={reconnectNow} />
              <div className="mt-6">
                <ClipGrid key={job.id} job={job} />
              </div>
            </>
          ) : (
            <ReconnectBanner onRetry={reconnectNow} />
          )
        ) : phase === "tracking" ? (
          // Centered (mx-auto on each panel) so the transient upload/processing screens don't sit
          // jammed against the left edge with a dead right half (founder call). Idle + done fill width.
          openingProject ? (
            <div className="flex items-center justify-center gap-3 py-10">
              <Spinner size="md" className="text-accent" />
              <p className="text-sm text-muted">{t("openingProject")}</p>
            </div>
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
              sourceKind={job?.source_kind ?? null}
            />
          )
        ) : phase === "done" && job ? (
          <>
            <VideoMap jobId={job.id} clips={job.clips ?? []} />
            <ClipGrid key={job.id} job={job} />
          </>
        ) : phase === "cancelled" ? (
          <div className="mx-auto max-w-xl">
            <Eyebrow tone="faint">{t("runStopped")}</Eyebrow>
            <h2 className="mt-2 font-display text-h3 text-ink">{t("projectStopped")}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{t("projectStoppedBody")}</p>
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
