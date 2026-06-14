"use client";

import { CheckSquare, Download, Square } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { mmss } from "@/lib/format";
import type { Job } from "@/lib/types";
import { ClipCard, resolveUrl } from "./ClipCard";

function EmptyState() {
  return (
    <div className="rounded-lg border border-line bg-surface p-10 text-center">
      <p className="font-display text-xl font-bold">Nothing to clip</p>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted">
        No standalone-worthy moments were found in this video. That’s not an error —
        try a different video.
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
          {clips.length} clips · source {mmss(m.duration_sec)} · {Math.round(m.elapsed_sec)}s
        </p>
      ) : null}

      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface p-3">
        <span className="font-mono text-sm text-ink">
          {selected.size} of {clips.length} selected
        </span>
        <Button type="button" variant="secondary" size="sm" onClick={toggleAll}>
          {allSelected ? <Square className="size-4" /> : <CheckSquare className="size-4" />}
          {allSelected ? "Deselect all" : "Select all"}
        </Button>
        <Button
          type="button"
          variant="accent"
          size="sm"
          onClick={downloadSelected}
          disabled={selected.size === 0}
          className="ml-auto"
        >
          <Download className="size-4" />
          Download selected ({selected.size})
        </Button>
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
