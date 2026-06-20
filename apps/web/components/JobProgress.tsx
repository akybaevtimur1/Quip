import { Check, Loader2, X } from "lucide-react";
import { useState } from "react";
import { mmss } from "@/lib/format";
import type { JobStatus } from "@/lib/types";

const ORDER: JobStatus[] = ["queued", "downloading", "transcribing", "selecting", "rendering", "done"];
const STEPS: { key: JobStatus; label: string }[] = [
  // "Preparing" (not "Downloading"): for an uploaded file there's nothing to download
  // — showing "Downloading" right after the upload screen read like a second download.
  { key: "downloading", label: "Preparing video" },
  { key: "transcribing", label: "Transcribing" },
  { key: "selecting", label: "Selecting moments" },
  { key: "rendering", label: "Rendering" },
];

export function JobProgress({
  status,
  elapsed,
  cancellable = false,
  onStop,
  sourceMinutes = null,
  transcriptWords = null,
  momentsFound = null,
}: {
  status: JobStatus;
  elapsed: number;
  // Stop-кнопка: показываем ТОЛЬКО когда воркер сообщил cancellable (FREE-фаза до транскрипции).
  cancellable?: boolean;
  onStop?: () => void;
  // Live-narration счётчики (наполняются по мере стадий) → окно 0–60% (до карточек) не мёртвое.
  sourceMinutes?: number | null;
  transcriptWords?: number | null;
  momentsFound?: number | null;
}) {
  // While "queued" (cur=0) the first real step ("Downloading", index 1) reads as active,
  // so the stepper never looks dead between submit and the first status change.
  const cur = Math.max(ORDER.indexOf(status), 1);
  // Local disable between click and the next poll (which flips cancellable→false) so a
  // double-click can't fire two cancels.
  const [stopping, setStopping] = useState(false);

  return (
    <div className="w-full max-w-3xl">
      <div className="mb-6 flex items-baseline justify-between gap-4">
        <h2 className="font-display text-2xl font-bold">Cutting your video…</h2>
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm text-muted" aria-live="polite">
            {mmss(elapsed)}
          </span>
          {cancellable && onStop && (
            <button
              type="button"
              disabled={stopping}
              onClick={() => {
                setStopping(true);
                onStop();
              }}
              className="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-sm text-muted transition hover:border-line-strong hover:text-ink disabled:opacity-50"
            >
              <X className="size-4" />
              {stopping ? "Stopping…" : "Stop"}
            </button>
          )}
        </div>
      </div>

      <ol className="flex flex-col gap-3">
        {STEPS.map((step) => {
          const i = ORDER.indexOf(step.key);
          const done = cur > i;
          const active = cur === i;
          // Live count for this stage (shown once the worker reports it) → the pre-clip wait
          // shows real progress on THEIR video, not just a spinner.
          const count =
            step.key === "downloading" && sourceMinutes != null
              ? `${sourceMinutes} min`
              : step.key === "transcribing" && transcriptWords != null
                ? `${transcriptWords.toLocaleString()} words`
                : step.key === "selecting" && momentsFound != null
                  ? `${momentsFound} found`
                  : null;
          return (
            <li
              key={step.key}
              className={`flex items-center gap-3 rounded-xl border px-4 py-3 transition ${
                active
                  ? "border-accent bg-surface-3"
                  : done
                    ? "border-line bg-surface"
                    : "border-line bg-surface opacity-50"
              }`}
            >
              <span
                className={`flex size-7 shrink-0 items-center justify-center rounded-full ${
                  done ? "bg-thought text-white" : active ? "bg-accent text-white" : "bg-surface-2 text-muted"
                }`}
              >
                {done ? (
                  <Check className="size-4" />
                ) : active ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <span className="size-2 rounded-full bg-muted" />
                )}
              </span>
              <span className={`font-medium ${active ? "text-ink" : done ? "text-ink" : "text-muted"}`}>
                {step.label}
                {count && <span className="ml-2 font-normal text-muted">· {count}</span>}
              </span>
            </li>
          );
        })}
      </ol>

      {/* скелетоны будущих клипов — резервируем место, показываем что идёт работа */}
      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="animate-pulse">
            <div className="aspect-[9/16] rounded-xl bg-surface-2" />
            <div className="mt-2 h-3 w-2/3 rounded bg-surface-2" />
          </div>
        ))}
      </div>
    </div>
  );
}
