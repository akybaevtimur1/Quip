import { mmss, usd } from "@/lib/format";
import type { Job } from "@/lib/types";
import { ClipCard } from "./ClipCard";

function EmptyState() {
  return (
    <div className="rounded-2xl border border-line bg-surface p-10 text-center">
      <p className="font-display text-xl font-bold">Нечего нарезать</p>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted">
        Из этого видео не нашлось моментов, которые работают самостоятельно. Это не ошибка —
        попробуй другое видео.
      </p>
    </div>
  );
}

export function ClipGrid({ job }: { job: Job }) {
  const clips = [...(job.clips ?? [])].sort((a, b) => b.score - a.score);
  if (clips.length === 0) return <EmptyState />;

  const m = job.metrics;
  return (
    <div className="w-full">
      {m ? (
        <p className="mb-5 font-mono text-sm text-muted">
          {clips.length} клипов · источник {mmss(m.duration_sec)} · {Math.round(m.elapsed_sec)}s ·{" "}
          {usd(m.cost_usd)}
        </p>
      ) : null}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {clips.map((c) => (
          <ClipCard key={c.id} clip={c} />
        ))}
      </div>
    </div>
  );
}
