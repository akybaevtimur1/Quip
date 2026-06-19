"use client";

import { CheckSquare, Download, Loader2, Square } from "lucide-react";
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

// NB: родитель монтирует <ClipGrid key={job.id}> → новый прогон = свежий маунт.
// Progressive: clips arrive with metadata while still rendering (empty video_url). The grid
// renders them immediately — ready clips are playable/editable, pending ones show a skeleton —
// and re-renders smoothly as polling flips pending→ready (stable keys by clip.id, no remount).
export function ClipGrid({ job }: { job: Job }) {
  const jobId = job.id;
  // Сорт по score ↓ с ДЕТЕРМИНИРОВАННЫМ тай-брейком по id: при равных score (часто у
  // подкаст-клипов) без него порядок зависел от исходной последовательности фетча и мог
  // разойтись с порядком в редакторе → «открываю первый, попадаю в третий», скачет ‹ ›.
  // score is final from the first poll, so order is stable as clips flip pending→ready.
  const clips = useMemo(
    () => [...(job.clips ?? [])].sort((a, b) => b.score - a.score || a.id.localeCompare(b.id)),
    [job.clips],
  );
  // A clip is READY (playable, editable, downloadable) once it has a non-empty video_url.
  const readyClips = useMemo(() => clips.filter((c) => c.video_url), [clips]);
  const rendering = job.status !== "done";

  // Selection model = "deselected ids" so a clip that flips pending→ready during polling is
  // selected by default (тracking a positive set would leave newly-arrived ready clips out).
  // Only READY clips are ever selectable/downloadable.
  const [deselected, setDeselected] = useState<Set<string>>(() => new Set());
  const selectedCount = readyClips.filter((c) => !deselected.has(c.id)).length;
  const allSelected = readyClips.length > 0 && selectedCount === readyClips.length;

  if (clips.length === 0) return <EmptyState />;

  const m = job.metrics;
  const readyCount = readyClips.length;

  function isSelected(id: string) {
    return !deselected.has(id);
  }

  function toggle(id: string) {
    setDeselected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    // Deselect-all marks every READY clip; select-all clears the deselected set.
    setDeselected(allSelected ? new Set(readyClips.map((c) => c.id)) : new Set());
  }

  function downloadSelected() {
    const chosen = readyClips.filter((c) => isSelected(c.id));
    downloadClips(chosen.map((c) => ({ href: resolveUrl(c.video_url), name: `${c.id}.mp4` })));
  }

  return (
    <div className="w-full">
      {rendering ? (
        // While rendering: compact "N of M clips ready" + a small status indicator. Drops to
        // the normal metrics line once status === "done".
        <p className="mb-4 flex items-center gap-2 font-mono text-sm text-muted">
          <Loader2 className="size-3.5 animate-spin text-accent" />
          <span className="text-ink">
            {readyCount} of {clips.length} clips ready
          </span>
          <span className="text-muted">· still rendering…</span>
        </p>
      ) : m ? (
        <p className="mb-4 font-mono text-sm text-muted">
          {clips.length} clips · source {mmss(m.duration_sec)} · {Math.round(m.elapsed_sec)}s
        </p>
      ) : null}

      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface p-3">
        <span className="font-mono text-sm text-ink">
          {selectedCount} of {readyCount} selected
        </span>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={toggleAll}
          disabled={readyCount === 0}
        >
          {allSelected ? <Square className="size-4" /> : <CheckSquare className="size-4" />}
          {allSelected ? "Deselect all" : "Select all"}
        </Button>
        <Button
          type="button"
          variant="accent"
          size="sm"
          onClick={downloadSelected}
          disabled={selectedCount === 0}
          className="ml-auto"
        >
          <Download className="size-4" />
          Download selected ({selectedCount})
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {clips.map((c) => (
          <ClipCard
            key={c.id}
            jobId={jobId}
            clip={c}
            selected={isSelected(c.id)}
            onToggle={() => toggle(c.id)}
          />
        ))}
      </div>
    </div>
  );
}
