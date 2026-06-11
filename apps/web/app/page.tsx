"use client";

import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { ClipGrid } from "@/components/ClipGrid";
import { ErrorPanel } from "@/components/ErrorPanel";
import { JobProgress } from "@/components/JobProgress";
import { SourceForm } from "@/components/SourceForm";
import { createJob, createUploadJob } from "@/lib/api";
import { useJob } from "@/lib/useJob";

export default function Home() {
  const { job, error: pollError, elapsed, start, reset } = useJob();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const error = submitError ?? pollError;

  // Deep-link: открыть существующую задачу по ?job=<id> (на маунте). start стабилен.
  useEffect(() => {
    const j = new URLSearchParams(window.location.search).get("job");
    if (j) start(j);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(url: string, maxClips: number) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const { id } = await createJob({
        source_type: "youtube",
        source_ref: url,
        max_clips: maxClips,
      });
      start(id);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Не удалось создать задачу");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmitFile(file: File, maxClips: number) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const { id } = await createUploadJob(file, maxClips);
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
    <main className="mx-auto flex min-h-dvh w-full max-w-6xl flex-col px-5 py-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="size-3 rounded-full bg-accent" />
          <span className="font-display text-lg font-extrabold tracking-tight">ClipFlow</span>
        </div>
        {phase !== "idle" ? (
          <button
            onClick={handleReset}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm text-muted transition hover:text-ink"
          >
            <Plus className="size-4" />
            Новое видео
          </button>
        ) : null}
      </header>

      <section className="flex flex-1 flex-col items-center justify-center py-10">
        {phase === "idle" ? (
          <div className="flex w-full max-w-xl flex-col items-center text-center">
            <h1 className="font-display text-4xl font-extrabold leading-tight sm:text-5xl">
              Длинное видео → <span className="text-accent">вертикальные клипы</span>
            </h1>
            <p className="mt-4 max-w-md text-muted">
              Вставь ссылку или загрузи файл — ИИ найдёт лучшие моменты, обрежет в 9:16 и
              прожжёт субтитры.
            </p>
            <div className="mt-8 flex justify-center">
              <SourceForm
                onSubmit={handleSubmit}
                onSubmitFile={handleSubmitFile}
                busy={submitting}
              />
            </div>
          </div>
        ) : null}

        {phase === "tracking" ? (
          <JobProgress status={job?.status ?? "queued"} elapsed={elapsed} />
        ) : null}

        {phase === "done" && job ? <ClipGrid key={job.id} job={job} /> : null}

        {phase === "error" && error ? (
          <ErrorPanel message={error} onRetry={handleReset} />
        ) : null}
      </section>
    </main>
  );
}
