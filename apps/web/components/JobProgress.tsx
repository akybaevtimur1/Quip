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

const STAGE_HINT: Partial<Record<JobStatus, string>> = {
  queued: "Warming up the engine…",
  downloading: "Getting your video ready…",
  transcribing: "Listening to every word…",
  selecting: "Finding the moments worth posting…",
  rendering: "Cutting your vertical clips…",
};

export function JobProgress({
  status,
  elapsed,
  progress = null,
  cancellable = false,
  onStop,
  sourceMinutes = null,
  transcriptWords = null,
  momentsFound = null,
}: {
  status: JobStatus;
  elapsed: number;
  // Серверный прогресс 0–100 (от воркера) → настоящий прогресс-бар, не только степпер.
  progress?: number | null;
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

  // Прогресс-бар: серверный progress, с полом по стадии чтобы бар никогда не выглядел
  // застрявшим на 0, и не дёргался назад (берём максимум из server и стадийного пола).
  const stageFloor = [0, 8, 35, 60, 80, 100][Math.min(cur, 5)] ?? 8;
  const pct = Math.min(99, Math.max(progress ?? 0, stageFloor));

  return (
    <div className="w-full max-w-3xl">
      <div className="mb-4 flex items-baseline justify-between gap-4">
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

      {/* прогресс-бар (серверный %) + текущая стадия + успокаивающая подсказка */}
      <div className="mb-6">
        <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
          <span className="font-medium text-ink">{STAGE_HINT[status] ?? "Working…"}</span>
          <span className="font-mono text-xs text-muted">{Math.round(pct)}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-surface-2">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
            style={{ width: `${Math.max(4, pct)}%` }}
          />
        </div>
        <p className="mt-2 text-xs text-faint">
          You can close this tab — processing keeps running, and your clips will be waiting in
          Recent projects.
        </p>
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
