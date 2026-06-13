import { Check, Loader2 } from "lucide-react";
import { mmss } from "@/lib/format";
import type { JobStatus } from "@/lib/types";

const ORDER: JobStatus[] = ["queued", "downloading", "transcribing", "selecting", "rendering", "done"];
const STEPS: { key: JobStatus; label: string }[] = [
  { key: "downloading", label: "Скачивание" },
  { key: "transcribing", label: "Транскрипция" },
  { key: "selecting", label: "Выбор моментов" },
  { key: "rendering", label: "Рендер" },
];

export function JobProgress({ status, elapsed }: { status: JobStatus; elapsed: number }) {
  const cur = ORDER.indexOf(status);

  return (
    <div className="w-full max-w-3xl">
      <div className="mb-6 flex items-baseline justify-between">
        <h2 className="font-display text-2xl font-bold">Режем видео…</h2>
        <span className="font-mono text-sm text-muted" aria-live="polite">
          {mmss(elapsed)}
        </span>
      </div>

      <ol className="flex flex-col gap-3">
        {STEPS.map((step) => {
          const i = ORDER.indexOf(step.key);
          const done = cur > i;
          const active = cur === i;
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
