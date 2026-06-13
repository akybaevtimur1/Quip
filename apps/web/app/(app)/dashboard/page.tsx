"use client";

import { Plus } from "lucide-react";
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

function DashboardInner() {
  const { job, error: pollError, elapsed, start, reset } = useJob();
  const [submitting, setSubmitting] = useState(false);
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
      setSubmitError(e instanceof Error ? e.message : "Не удалось создать проект");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmitFile(file: File, maxClips: number) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const { id } = await createUploadJob(file, maxClips);
      addRecentProject({ id, label: file.name, at: Date.now() });
      start(id);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Не удалось загрузить файл");
    } finally {
      setSubmitting(false);
    }
  }

  function handleReset() {
    reset();
    setSubmitError(null);
    setSubmitting(false);
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
            Новый проект
          </button>
        )}

        {phase === "idle" ? (
          <div className="grid gap-10 lg:grid-cols-[1fr_320px] lg:gap-12">
            <section>
              <h1 className="font-display text-h2 text-ink sm:text-display-lg">Создать клипы</h1>
              <p className="mt-3 max-w-md text-lead text-muted">
                Вставь ссылку или загрузи видео. Quip находит сильные моменты, нарезает
                вертикальные клипы и объясняет, почему каждый зайдёт.
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
