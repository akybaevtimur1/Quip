"use client";

import { Check, Download, Maximize2, Minimize2, Pencil } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
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
      className={`flex flex-col rounded-2xl border bg-surface transition ${
        selected ? "border-accent/60 ring-1 ring-accent/30" : "border-line opacity-55"
      }`}
    >
      {/* ── video ── */}
      <div
        ref={containerRef}
        className="relative overflow-hidden rounded-t-2xl bg-surface-2"
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

        {/* Fullscreen toggle — fullscreens the container so the overlay travels with it */}
        <button
          type="button"
          onClick={toggleFullscreen}
          title={isFullscreen ? "Выйти из полного экрана" : "Полный экран"}
          className="absolute bottom-14 right-10 rounded-md p-1 bg-black/60 text-white/70 hover:text-white transition"
        >
          {isFullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
        </button>

        {/* CC toggle */}
        {clip.words.length > 0 && (
          <button
            type="button"
            onClick={() => setShowCaptions((v) => !v)}
            title={showCaptions ? "Скрыть анимированные субтитры" : "Показать анимированные субтитры"}
            className={`absolute bottom-14 right-2 rounded-md px-2 py-0.5 text-[11px] font-bold transition ${
              showCaptions
                ? "bg-accent text-white"
                : "bg-black/60 text-white/70 hover:text-white"
            }`}
          >
            CC
          </button>
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
          {/* Страница-редактор: возврат через «← Все клипы» (/?job=) или Back —
              грид восстанавливается deep-link'ом, ничего не теряется. */}
          <Link
            href={`/edit/${jobId}/${clip.id}`}
            className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-ink transition hover:border-accent/50 hover:text-accent focus:outline-none"
          >
            <Pencil className="size-4" />
            Редактировать
          </Link>
        </div>
      </div>
    </article>
  );
}
