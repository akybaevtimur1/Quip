"use client";

import { Loader2, Plus, UploadCloud } from "lucide-react";
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
import { SourceForm } from "@/components/SourceForm";
import { cancelJob, createJob, createUploadJob } from "@/lib/api";
import { addRecentProject } from "@/lib/recent";
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
 *  never looks frozen. Real % comes from XHR upload-progress events. */
function UploadProgress({ pct }: { pct: number }) {
  return (
    <div className="w-full max-w-md text-center">
      <span className="mx-auto mb-5 grid size-12 place-items-center rounded-full border border-line bg-surface-2 text-accent">
        <UploadCloud className="size-6" aria-hidden />
      </span>
      <h2 className="font-display text-2xl font-bold text-ink">Uploading your video…</h2>
      <p className="mt-2 text-sm text-muted">
        {pct < 100 ? "Hang tight — large files take a moment." : "Almost there — getting it ready…"}
      </p>
      <div className="mt-6 h-2 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-200 ease-out"
          style={{ width: `${Math.max(4, pct)}%` }}
        />
      </div>
      <p className="mt-2 font-mono text-sm text-muted" aria-live="polite">
        {pct}%
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

  async function handleSubmit(url: string, maxClips: number) {
    if (submitting) return; // guard: не плодим параллельные джобы двойным сабмитом
    setSubmitError(null);
    setSubmitting(true);
    try {
      const { id } = await createJob({ source_type: "youtube", source_ref: url, max_clips: maxClips });
      addRecentProject({ id, label: labelFromUrl(url), at: Date.now() });
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
    setUploadPct(0); // show the uploading screen immediately, before bytes move
    try {
      const { id } = await createUploadJob(file, maxClips, setUploadPct, ctrl.signal);
      if (ctrl.signal.aborted) return; // отменена/вытеснена — не трогаем стейт
      setUploadPct(null);
      addRecentProject({ id, label: file.name, at: Date.now() });
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
          <div className="grid gap-10 lg:grid-cols-[1fr_320px] lg:gap-12">
            <section>
              <h1 className="font-display text-h2 text-ink sm:text-display-lg">Create clips</h1>
              <p className="mt-3 max-w-md text-lead text-muted">
                Paste a link or upload a video. Quip finds the strongest moments, cuts
                vertical clips, and explains why each one works.
              </p>
              <div className="mt-8">
                <SourceForm onSubmit={handleSubmit} onSubmitFile={handleSubmitFile} busy={submitting} />
              </div>
            </section>
            <aside className="space-y-5">
              <UsageMeter />
              <PromoRedeem />
              <RecentProjects />
            </aside>
          </div>
        ) : uploadPct !== null ? (
          <div className="flex justify-center py-8">
            <UploadProgress pct={uploadPct} />
          </div>
        ) : phase === "tracking" ? (
          <div className="flex justify-center py-8">
            {openingProject ? (
              <div className="flex flex-col items-center gap-3 py-10 text-center">
                <Loader2 className="size-6 animate-spin text-accent" aria-hidden />
                <p className="text-sm text-muted">Opening your project…</p>
              </div>
            ) : (
              <JobProgress
                status={job?.status ?? "queued"}
                elapsed={elapsed}
                cancellable={job?.cancellable ?? false}
                onStop={handleStop}
              />
            )}
          </div>
        ) : phase === "done" && job ? (
          <>
            <VideoMap jobId={job.id} clips={job.clips ?? []} />
            <ClipGrid key={job.id} job={job} />
          </>
        ) : phase === "cancelled" ? (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <h2 className="font-display text-2xl font-bold text-ink">This project was stopped</h2>
            <p className="max-w-sm text-sm text-muted">
              You stopped processing this video before it finished. Nothing was charged — start a
              new project whenever you’re ready.
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
