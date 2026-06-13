"use client";

import { Check, Gauge, Maximize2, Minimize2, Pencil, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ExportMenu } from "@/components/ExportMenu";
import { clipRange } from "@/lib/format";
import type { ClipOut } from "@/lib/types";
import { CaptionOverlay } from "./CaptionOverlay";
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
  const [videoSrc] = useState(() => resolveUrl(clip.video_url));
  const [showCaptions, setShowCaptions] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Track fullscreen state so overlay remains synced.
  useEffect(() => {
    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      containerRef.current?.requestFullscreen();
    }
  };

  return (
    <article
      className={`flex flex-col rounded-lg border bg-surface transition duration-200 ease-snappy ${
        selected ? "border-accent/60 ring-1 ring-accent/30" : "border-line opacity-55 hover:opacity-80"
      }`}
    >
      {/* ── video ── */}
      <div
        ref={containerRef}
        className="relative overflow-hidden rounded-t-lg bg-surface-2"
        style={isFullscreen ? { background: "#000", display: "flex", alignItems: "center", justifyContent: "center" } : {}}
      >
        <video
          ref={videoRef}
          key={videoSrc}
          src={videoSrc}
          controls
          preload="metadata"
          playsInline
          // Remove native fullscreen button — we supply our own that fullscreens the container
          // so the caption overlay stays visible.
          controlsList="nofullscreen"
          className={
            isFullscreen
              ? "h-full max-h-screen w-auto bg-black object-contain"
              : "aspect-[9/16] w-full bg-black object-contain"
          }
        />
        {showCaptions && clip.words.length > 0 && (
          <CaptionOverlay words={clip.words} clipStart={clip.start} videoRef={videoRef} />
        )}
        <span className="absolute left-2 top-2">
          <ReasonChip type={clip.type} />
        </span>

        {/* Fullscreen toggle — fullscreens the container so the overlay travels with it.
            Dark scrim is intentional: these controls overlay arbitrary video frames. */}
        <button
          type="button"
          onClick={toggleFullscreen}
          title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
          className="absolute bottom-14 right-10 rounded-sm bg-black/60 p-1 text-white/70 backdrop-blur-sm transition duration-150 ease-snappy hover:bg-black/75 hover:text-white active:scale-95"
        >
          {isFullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
        </button>

        {/* CC toggle */}
        {clip.words.length > 0 && (
          <button
            type="button"
            onClick={() => setShowCaptions((v) => !v)}
            title={showCaptions ? "Hide animated captions" : "Show animated captions"}
            className={`absolute bottom-14 right-2 rounded-sm px-2 py-0.5 text-[11px] font-bold backdrop-blur-sm transition duration-150 ease-snappy active:scale-95 ${
              showCaptions
                ? "bg-accent text-white"
                : "bg-black/60 text-white/70 hover:bg-black/75 hover:text-white"
            }`}
          >
            CC
          </button>
        )}

        {/* select button (custom-styled checkbox affordance over the video) */}
        <button
          type="button"
          onClick={onToggle}
          aria-pressed={selected}
          aria-label={selected ? "Deselect" : "Select"}
          className={`absolute right-2 top-2 inline-flex size-7 items-center justify-center rounded-sm border transition duration-150 ease-snappy active:scale-95 ${
            selected
              ? "border-accent bg-accent text-white"
              : "border-line-strong bg-bg/70 text-transparent backdrop-blur hover:border-accent/60 hover:text-white/30"
          }`}
        >
          <Check className="size-4" strokeWidth={3} />
        </button>
      </div>

      {/* ── meta: структурный reasoning (объяснимость = наш отличитель) ── */}
      <div className="flex flex-col gap-2.5 p-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-muted">{clipRange(clip.start, clip.end)}</span>
          <span
            className="inline-flex items-center gap-1 font-mono text-sm font-semibold text-ink"
            title="AI confidence that this clip works as a short"
          >
            <Gauge className="size-3.5 text-muted" />
            {clip.score.toFixed(2)}
          </span>
        </div>

        {/* хук-заголовок (топ-текст клипа) */}
        {clip.hook && (
          <p className="flex items-start gap-1.5 text-[15px] font-bold leading-tight text-ink">
            <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" />
            <span>«{clip.hook}»</span>
          </p>
        )}

        {/* почему сработает (структурно, не один blob) */}
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            Why it works
          </p>
          <p className="text-sm leading-snug text-ink">{clip.why_works ?? clip.reason}</p>
        </div>

        {clip.transcript && (
          <p className="line-clamp-2 text-xs leading-snug text-muted">«{clip.transcript}»</p>
        )}

        {/* actions */}
        <div className="flex gap-2 pt-1">
          {/* Меню экспорта (с субтитрами / без / .srt) — открывается ВВЕРХ, чтобы не
              перекрываться соседними карточками грида. */}
          <ExportMenu
            jobId={jobId}
            clipId={clip.id}
            subtitledUrl={videoSrc}
            align="left"
            placement="up"
            className="flex-1"
          />
          {/* Страница-редактор: возврат через «← Все клипы» (/?job=) или Back —
              грид восстанавливается deep-link'ом, ничего не теряется. */}
          <Link
            href={`/edit/${jobId}/${clip.id}`}
            className="inline-flex items-center justify-center gap-1.5 rounded-sm border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-ink transition duration-200 ease-snappy hover:-translate-y-px hover:border-line-strong hover:bg-surface-3"
          >
            <Pencil className="size-4" />
            Edit
          </Link>
        </div>
      </div>
    </article>
  );
}
