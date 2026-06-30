"use client";

import { Captions, CheckSquare, ChevronDown, Download, FileText, Film, Square } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import { downloadFile } from "@/components/ExportMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Numeral } from "@/components/ui/Numeral";
import { Spinner } from "@/components/ui/Spinner";
import { clipCaptionedExportUrl, clipSrtUrl } from "@/lib/api";
import { elapsed, mmss } from "@/lib/format";
import type { ClipOut, Job } from "@/lib/types";
import { ClipCard, resolveUrl } from "./ClipCard";

const WORKER_BASE = process.env.NEXT_PUBLIC_WORKER_URL ?? "";

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

/** Download N exports as blobs with a concurrency cap, reporting progress as each finishes.
 *  Heavier than the native-link path (it fetches every file), but it lets us (a) cap how many
 *  on-the-fly renders hit the worker at once and (b) show "Preparing X of Y…". A per-item failure
 *  falls back to a native anchor (the worker sends Content-Disposition: attachment, so the browser
 *  saves rather than navigates) — never a silent drop. Shares ExportMenu's `downloadFile`. */
async function runBatchDownload(
  items: { url: string; name: string }[],
  concurrency: number,
  onDone: (completed: number) => void,
): Promise<void> {
  let completed = 0;
  let next = 0;
  const worker = async () => {
    for (let i = next++; i < items.length; i = next++) {
      const { url, name } = items[i];
      try {
        await downloadFile(url, name);
      } catch (e) {
        console.warn("[download-all] blob fetch failed, native fallback:", e);
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
      onDone(++completed);
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker));
}

type ChosenClip = { id: string; cleanHref: string };
type BatchState = { kind: "captioned" | "srt"; done: number; total: number };

/** "Download all" as a 3-variant menu (mirrors the single-clip ExportMenu, but batched):
 *   • With subtitles  — per-clip on-the-fly captioned render (heavier → concurrency 2 + progress).
 *   • Without subtitles — the clean clip is already baked on the CDN (clip.video_url) → instant
 *                         native staggered links (no fetch/render).
 *   • Subtitles only (.SRT) — cheap per-clip text (concurrency 3 + progress).
 *  Default (primary button) = With subtitles, matching what the grid renders (captioned preview). */
function DownloadAllMenu({
  jobId,
  chosen,
  disabled,
}: {
  jobId: string;
  chosen: ChosenClip[];
  disabled: boolean;
}) {
  const t = useTranslations("clipGrid");
  const [open, setOpen] = useState(false);
  const [batch, setBatch] = useState<BatchState | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const count = chosen.length;
  const busy = batch !== null;

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Clean clips are already on the CDN → reuse the existing native stagger helper (instant).
  const downloadClean = () => {
    if (busy || count === 0) return;
    downloadClips(chosen.map((c) => ({ href: c.cleanHref, name: `${c.id}.mp4` })));
    setOpen(false);
  };

  const runBatch = async (kind: "captioned" | "srt") => {
    if (busy || count === 0) return;
    const items = chosen.map((c) =>
      kind === "captioned"
        ? { url: clipCaptionedExportUrl(WORKER_BASE, jobId, c.id), name: `${c.id}-captioned.mp4` }
        : { url: clipSrtUrl(WORKER_BASE, jobId, c.id), name: `${c.id}.srt` },
    );
    setOpen(false);
    setBatch({ kind, done: 0, total: items.length });
    try {
      // Captioned renders on the fly (heavy) → 2 at a time; SRT is cheap text → 3.
      await runBatchDownload(items, kind === "captioned" ? 2 : 3, (done) =>
        setBatch({ kind, done, total: items.length }),
      );
    } finally {
      setBatch(null);
    }
  };

  const primaryLabel = busy
    ? t("preparingBatch", { done: batch.done, total: batch.total })
    : t("download", { count });
  const accent =
    "inline-flex items-center justify-center gap-1.5 bg-accent text-sm font-semibold text-white " +
    "transition duration-200 ease-snappy hover:bg-accent-2 disabled:pointer-events-none " +
    "disabled:bg-surface-2 disabled:text-faint";

  return (
    <div ref={ref} className="relative ml-auto">
      <div className="inline-flex overflow-hidden rounded-md">
        <button
          type="button"
          onClick={() => runBatch("captioned")}
          disabled={disabled}
          aria-busy={busy || undefined}
          className={`${accent} h-9 px-3.5 ${busy ? "pointer-events-none" : ""}`}
        >
          {busy ? <Spinner size="sm" className="text-white" /> : <Download className="size-4" />}
          {primaryLabel}
        </button>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={disabled || busy}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={t("downloadOptions")}
          className={`${accent} h-9 border-l border-white/25 px-2`}
        >
          <ChevronDown className={`size-4 transition ${open ? "rotate-180" : ""}`} />
        </button>
      </div>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-30 mt-1 min-w-[260px] max-w-[calc(100vw-1.5rem)] overflow-hidden rounded-md border border-line-strong bg-surface shadow-[0_16px_40px_-12px_rgba(0,0,0,.7)]"
        >
          <DownloadAllItem
            icon={<Captions className="size-4" />}
            title={t("withSubtitles")}
            sub={t("withSubtitlesSub")}
            onPick={() => runBatch("captioned")}
          />
          <DownloadAllItem
            icon={<Film className="size-4" />}
            title={t("withoutSubtitles")}
            sub={t("withoutSubtitlesSub")}
            onPick={downloadClean}
          />
          <DownloadAllItem
            icon={<FileText className="size-4" />}
            title={t("srtOnly")}
            sub={t("srtOnlySub")}
            onPick={() => runBatch("srt")}
          />
        </div>
      )}
    </div>
  );
}

function DownloadAllItem({
  icon,
  title,
  sub,
  onPick,
}: {
  icon: React.ReactNode;
  title: string;
  sub: string;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onPick}
      className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition hover:bg-surface-2"
    >
      <span className="mt-0.5 text-muted">{icon}</span>
      <span className="flex flex-col">
        <span className="text-sm font-semibold text-ink">{title}</span>
        <span className="text-xs text-muted">{sub}</span>
      </span>
    </button>
  );
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
  const t = useTranslations("clipGrid");
  const jobId = job.id;
  // Score order is locked the moment clip IDs arrive (score is final from first poll).
  // Re-sort only when the SET of IDs changes (new clips added), NOT when video_url populates —
  // so clips never jump position as renders complete.
  const clipIdKey = (job.clips ?? []).map((c) => c.id).join(",");
  const sortedIds = useMemo(
    () =>
      [...(job.clips ?? [])]
        .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
        .map((c) => c.id),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clipIdKey]
  );
  // Map IDs → current clip objects so video_url / thumbnail updates land in-place.
  const clips = useMemo(
    () =>
      sortedIds
        .map((id) => (job.clips ?? []).find((c) => c.id === id))
        .filter((c): c is ClipOut => !!c),
    [sortedIds, job.clips]
  );
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
        title={t("emptyTitle")}
        description={t("emptyBody")}
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

  // Selected + ready clips, with their stable clean CDN url (clip.video_url) resolved once — the
  // DownloadAllMenu uses these for "Without subtitles" (instant) and the per-clip job/clip ids for
  // the captioned/SRT batches. Snapshotted at click time inside the menu, so changing the
  // selection mid-download doesn't affect an in-flight batch.
  const chosen: ChosenClip[] = readyClips
    .filter((c) => isSelected(c.id))
    .map((c) => ({ id: c.id, cleanHref: resolveUrl(c.video_url) }));

  return (
    <div className="w-full">
      {/* ── results masthead: the verdict (display) + a mono stat strip. ── */}
      <header className="mb-5 border-b border-line pb-5">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div>
            <Eyebrow tone="faint">{rendering ? t("cutting") : t("results")}</Eyebrow>
            <h1 className="mt-1.5 font-display text-h2 text-ink">
              {rendering
                ? t("readyOfTotal", { ready: readyCount, total: clips.length })
                : t("totalReady", { total: clips.length })}
            </h1>
          </div>
          {/* stat strip — calibrated readings about this run */}
          <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
            <StripStat label={t("avgConfidence")} value={`${Math.round(avgScore * 100)}/100`} />
            {m && <StripStat label={t("source")} value={mmss(m.duration_sec)} />}
            {m && <StripStat label={t("timeTaken")} value={elapsed(m.elapsed_sec)} />}
          </div>
        </div>
      </header>

      {/* selection — a quiet inline row, not a boxed toolbar. */}
      <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        {rendering && (
          <span className="inline-flex items-center gap-1.5 font-mono text-eyebrow uppercase text-muted">
            <Spinner size="sm" className="text-accent" />
            {t("stillRendering")}
          </span>
        )}
        <span className="font-mono text-eyebrow uppercase text-muted">
          {t.rich("selectedOf", {
            selected: selectedCount,
            ready: readyCount,
            sel: (chunks) => <Numeral className="text-ink">{chunks}</Numeral>,
            total: (chunks) => <Numeral>{chunks}</Numeral>,
          })}
        </span>
        <button
          type="button"
          onClick={toggleAll}
          disabled={readyCount === 0}
          className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-ink disabled:opacity-50"
        >
          {allSelected ? <Square className="size-4" /> : <CheckSquare className="size-4" />}
          {allSelected ? t("deselectAll") : t("selectAll")}
        </button>
        <DownloadAllMenu jobId={jobId} chosen={chosen} disabled={selectedCount === 0} />
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
