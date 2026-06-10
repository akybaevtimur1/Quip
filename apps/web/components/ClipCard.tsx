"use client";

import { Check, Download, Pencil, X } from "lucide-react";
import { useState } from "react";
import { clipRange } from "@/lib/format";
import type { ClipOut } from "@/lib/types";
import ClipEditor from "./ClipEditor";
import { ReasonChip } from "./ReasonChip";

const WORKER_BASE = process.env.NEXT_PUBLIC_WORKER_URL ?? "";

export function resolveUrl(videoUrl: string): string {
  if (videoUrl.startsWith("http") || videoUrl.startsWith("/")) return videoUrl;
  return `${WORKER_BASE}/${videoUrl}`;
}

export function ClipCard({
  jobId,
  clip,
  selected,
  onToggle,
}: {
  jobId: string;
  clip: ClipOut;
  selected: boolean;
  onToggle: () => void;
}) {
  const [videoSrc, setVideoSrc] = useState(() => resolveUrl(clip.video_url));
  const [showEditor, setShowEditor] = useState(false);
  const [renderDone, setRenderDone] = useState(false);

  const handleRenderDone = (url: string) => {
    setVideoSrc(url);
    setRenderDone(true);
    setTimeout(() => setRenderDone(false), 4000);
  };

  return (
    <article
      className={`flex flex-col rounded-2xl border bg-surface transition ${
        selected ? "border-accent/60 ring-1 ring-accent/30" : "border-line opacity-55"
      }`}
    >
      {/* ── video ── */}
      <div className="relative overflow-hidden rounded-t-2xl bg-surface-2">
        <video
          key={videoSrc}
          src={videoSrc}
          controls
          preload="metadata"
          playsInline
          className="aspect-[9/16] w-full bg-black object-contain"
        />
        <span className="absolute left-2 top-2">
          <ReasonChip type={clip.type} />
        </span>
        {/* render-done flash */}
        {renderDone && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60 animate-pulse pointer-events-none">
            <span className="rounded-full bg-green-500/90 px-4 py-2 text-sm font-semibold text-white">
              ✓ Обновлено
            </span>
          </div>
        )}
        {/* select button */}
        <button
          type="button"
          onClick={onToggle}
          aria-pressed={selected}
          aria-label={selected ? "Убрать из выбора" : "Добавить в выбор"}
          className={`absolute right-2 top-2 inline-flex size-7 items-center justify-center rounded-lg border transition focus:outline-none focus:ring-2 focus:ring-accent/50 ${
            selected
              ? "border-accent bg-accent text-white"
              : "border-line bg-surface/80 text-transparent backdrop-blur hover:border-accent/60"
          }`}
        >
          <Check className="size-4" strokeWidth={3} />
        </button>
      </div>

      {/* ── meta ── */}
      <div className="flex flex-col gap-2 p-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-muted">{clipRange(clip.start, clip.end)}</span>
          <span className="font-mono text-sm font-semibold text-ink">{clip.score.toFixed(2)}</span>
        </div>
        <p className="text-sm leading-snug text-ink">{clip.reason}</p>
        {clip.transcript && (
          <p className="line-clamp-2 text-xs leading-snug text-muted">«{clip.transcript}»</p>
        )}

        {/* actions */}
        <div className="flex gap-2 pt-1">
          <a
            href={videoSrc}
            download
            className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-ink transition hover:border-accent/50 hover:text-accent focus:outline-none"
          >
            <Download className="size-4" />
            Скачать
          </a>
          <button
            type="button"
            onClick={() => setShowEditor((v) => !v)}
            className={`inline-flex items-center justify-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-semibold transition focus:outline-none ${
              showEditor
                ? "border-accent/60 bg-accent/10 text-accent"
                : "border-line bg-surface-2 text-ink hover:border-accent/50 hover:text-accent"
            }`}
          >
            {showEditor ? <X className="size-4" /> : <Pencil className="size-4" />}
            {showEditor ? "Закрыть" : "Редактировать"}
          </button>
        </div>
      </div>

      {/* ── inline editor ── */}
      {showEditor && (
        <div className="rounded-b-2xl border-t border-line bg-surface overflow-hidden">
          <ClipEditor
            jobId={jobId}
            clipId={clip.id}
            onRenderDone={handleRenderDone}
          />
        </div>
      )}
    </article>
  );
}
