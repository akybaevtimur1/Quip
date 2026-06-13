import type { JobStatus } from "@/lib/types";

const LABEL: Record<JobStatus, string> = {
  queued: "В очереди",
  downloading: "Скачивание",
  transcribing: "Транскрипция",
  selecting: "Выбор моментов",
  rendering: "Рендер",
  done: "Готово",
  failed: "Ошибка",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const cls =
    status === "failed"
      ? "text-bad border-bad/40 bg-bad/10"
      : status === "done"
        ? "text-ok border-ok/40 bg-ok/10"
        : "text-muted border-line bg-surface-2";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${cls}`}
    >
      {LABEL[status]}
    </span>
  );
}
