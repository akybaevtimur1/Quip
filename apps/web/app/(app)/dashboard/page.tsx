"use client";

import { Plus, UploadCloud } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AppHeader } from "@/components/app/AppHeader";
import { RecentProjects } from "@/components/app/RecentProjects";
import { UsageMeter } from "@/components/app/UsageMeter";
import { ClipGrid } from "@/components/ClipGrid";
import { ErrorPanel } from "@/components/ErrorPanel";
import { JobProgress } from "@/components/JobProgress";
import { SourceForm } from "@/components/SourceForm";
import { createJob, createUploadJob } from "@/lib/api";
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
  const { job, error: pollError, elapsed, start, reset } = useJob();
  const [submitting, setSubmitting] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const error = submitError ?? pollError;

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
    setSubmitError(null);
    setSubmitting(true);
    setUploadPct(0); // show the uploading screen immediately, before bytes move
    try {
      const { id } = await createUploadJob(file, maxClips, setUploadPct);
      setUploadPct(null);
      addRecentProject({ id, label: file.name, at: Date.now() });
      start(id);
    } catch (e) {
      setUploadPct(null);
      setSubmitError(e instanceof Error ? e.message : "Couldn’t upload file");
    } finally {
      setSubmitting(false);
    }
  }

  function handleReset() {
    reset();
    setSubmitError(null);
    setSubmitting(false);
    setUploadPct(null);
  }

  const phase = error
    ? "error"
    : job?.status === "done"
      ? "done"
      : job || submitting
        ? "tracking"
        : "idle";

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
              <RecentProjects />
            </aside>
          </div>
        ) : uploadPct !== null ? (
          <div className="flex justify-center py-8">
            <UploadProgress pct={uploadPct} />
          </div>
        ) : phase === "tracking" ? (
          <div className="flex justify-center py-8">
            <JobProgress status={job?.status ?? "queued"} elapsed={elapsed} />
          </div>
        ) : phase === "done" && job ? (
          <ClipGrid key={job.id} job={job} />
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
