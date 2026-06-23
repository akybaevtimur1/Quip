"use client";

import { CheckSquare, Download, Square } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Spinner } from "@/components/ui/Spinner";
import { mmss } from "@/lib/format";
import type { ClipOut, Job } from "@/lib/types";
import { ClipCard, resolveUrl } from "./ClipCard";

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

/** One mono readout in the results stat strip: a faint eyebrow over a tabular value. */
function StripStat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <Eyebrow tone="faint" className="block">
        {label}
      </Eyebrow>
      <Numeral className="mt-1 block text-sm text-ink">{value}</Numeral>
    </div>
  );
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
  // READY clips bubble to the TOP (in score order), still-rendering ones sink to the bottom —
  // so finished clips always accumulate at the front and the user never hunts for "what appeared
  // where". When everything is done all clips are ready → pure score order (the final, good order).
  const clips = useMemo(() => {
    const byScore = (a: ClipOut, b: ClipOut) => b.score - a.score || a.id.localeCompare(b.id);
    return [...(job.clips ?? [])].sort((a, b) => {
      const ar = a.video_url ? 0 : 1; // ready first (0), pending after (1)
      const br = b.video_url ? 0 : 1;
      return ar - br || byScore(a, b);
    });
  }, [job.clips]);
  // A clip is READY (playable, editable, downloadable) once it has a non-empty video_url.
  const readyClips = useMemo(() => clips.filter((c) => c.video_url), [clips]);
  const rendering = job.status !== "done";

  // The single highest-scoring clip gets the one coral score meter (the scarce peak signal).
  const topClipId = useMemo(() => {
    if (clips.length === 0) return null;
    return clips.reduce((best, c) => (c.score > best.score ? c : best), clips[0]).id;
  }, [clips]);

  // Average confidence across all clips (a results-masthead reading).
  const avgScore = useMemo(() => {
    if (clips.length === 0) return 0;
    return clips.reduce((sum, c) => sum + c.score, 0) / clips.length;
  }, [clips]);

  // Selection model = "deselected ids" so a clip that flips pending→ready during polling is
  // selected by default (тracking a positive set would leave newly-arrived ready clips out).
  // Only READY clips are ever selectable/downloadable.
  const [deselected, setDeselected] = useState<Set<string>>(() => new Set());
  const selectedCount = readyClips.filter((c) => !deselected.has(c.id)).length;
  const allSelected = readyClips.length > 0 && selectedCount === readyClips.length;

  if (clips.length === 0)
    return (
      <EmptyState
        align="center"
        className="rounded-lg border border-line bg-surface p-10"
        title="Nothing to clip"
        description="No standalone-worthy moments were found in this video. That’s not an error — try a different video."
      />
    );

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
      {/* ── results masthead: the verdict (display) + a mono stat strip. ── */}
      <header className="mb-5 border-b border-line pb-5">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div>
            <Eyebrow tone="faint">{rendering ? "Cutting clips" : "Results"}</Eyebrow>
            <h1 className="mt-1.5 font-display text-h2 text-ink">
              {rendering
                ? `${readyCount} of ${clips.length} clip${clips.length === 1 ? "" : "s"} ready`
                : `${clips.length} clip${clips.length === 1 ? "" : "s"} ready`}
            </h1>
          </div>
          {/* stat strip — calibrated readings about this run */}
          <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
            <StripStat label="Avg confidence" value={`${Math.round(avgScore * 100)}/100`} />
            {m && <StripStat label="Source" value={mmss(m.duration_sec)} />}
            {m && <StripStat label="Time taken" value={`${Math.round(m.elapsed_sec)}s`} />}
          </div>
        </div>
      </header>

      {/* selection — a quiet inline row, not a boxed toolbar. */}
      <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        {rendering && (
          <span className="inline-flex items-center gap-1.5 font-mono text-eyebrow uppercase text-muted">
            <Spinner size="sm" className="text-accent" />
            still rendering
          </span>
        )}
        <span className="font-mono text-eyebrow uppercase text-muted">
          <Numeral className="text-ink">{selectedCount}</Numeral> of{" "}
          <Numeral>{readyCount}</Numeral> selected
        </span>
        <button
          type="button"
          onClick={toggleAll}
          disabled={readyCount === 0}
          className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-ink disabled:opacity-50"
        >
          {allSelected ? <Square className="size-4" /> : <CheckSquare className="size-4" />}
          {allSelected ? "Deselect all" : "Select all"}
        </button>
        <Button
          type="button"
          variant="accent"
          size="sm"
          onClick={downloadSelected}
          disabled={selectedCount === 0}
          className="ml-auto"
        >
          <Download className="size-4" />
          Download ({selectedCount})
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
            topClip={c.id === topClipId}
          />
        ))}
      </div>
    </div>
  );
}
