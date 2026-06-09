"use client";

import { CheckSquare, Download, Square } from "lucide-react";
import { useMemo, useState } from "react";
import { mmss, usd } from "@/lib/format";
import type { Job } from "@/lib/types";
import { ClipCard, resolveUrl } from "./ClipCard";

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

function downloadClips(urls: { href: string; name: string }[]) {
  // последовательные скачивания (стаггер, чтобы браузер не зарезал пачку как попап)
  urls.forEach(({ href, name }, i) => {
    setTimeout(() => {
      const a = document.createElement("a");
      a.href = href;
      a.download = name;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }, i * 400);
  });
}

// NB: родитель монтирует <ClipGrid key={job.id}> → новый прогон = свежий маунт =
// выбор сбрасывается на «все выбраны» без эффектов (см. page.tsx).
export function ClipGrid({ job }: { job: Job }) {
  const jobId = job.id;
  const clips = useMemo(
    () => [...(job.clips ?? [])].sort((a, b) => b.score - a.score),
    [job.clips],
  );
  const [selected, setSelected] = useState<Set<string>>(() => new Set(clips.map((c) => c.id)));

  if (clips.length === 0) return <EmptyState />;

  const m = job.metrics;
  const allSelected = selected.size === clips.length;

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(clips.map((c) => c.id)));
  }

  function downloadSelected() {
    const chosen = clips.filter((c) => selected.has(c.id));
    downloadClips(chosen.map((c) => ({ href: resolveUrl(c.video_url), name: `${c.id}.mp4` })));
  }

  return (
    <div className="w-full">
      {m ? (
        <p className="mb-4 font-mono text-sm text-muted">
          {clips.length} клипов · источник {mmss(m.duration_sec)} · {Math.round(m.elapsed_sec)}s ·{" "}
          {usd(m.cost_usd)}
        </p>
      ) : null}

      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-3">
        <span className="font-mono text-sm text-ink">
          Выбрано {selected.size} из {clips.length}
        </span>
        <button
          type="button"
          onClick={toggleAll}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm text-muted transition hover:text-ink"
        >
          {allSelected ? <Square className="size-4" /> : <CheckSquare className="size-4" />}
          {allSelected ? "Снять все" : "Выбрать все"}
        </button>
        <button
          type="button"
          onClick={downloadSelected}
          disabled={selected.size === 0}
          className="ml-auto inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-accent-2 focus:outline-none focus:ring-2 focus:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Download className="size-4" />
          Скачать выбранные ({selected.size})
        </button>
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {clips.map((c) => (
          <ClipCard
            key={c.id}
            jobId={jobId}
            clip={c}
            selected={selected.has(c.id)}
            onToggle={() => toggle(c.id)}
          />
        ))}
      </div>
    </div>
  );
}
