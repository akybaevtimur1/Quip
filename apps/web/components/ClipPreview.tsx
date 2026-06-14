"use client";

import { Loader2, Maximize2, Minimize2, Pause, Play, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { CaptionOverlay } from "@/components/CaptionOverlay";
import { LibassLayer } from "@/components/LibassLayer";
import { getClipAss } from "@/lib/api";
import { mmss } from "@/lib/format";
import type { Word } from "@/lib/types";

// ────────────────────────────────────────────────────────────────────────────
// ClipPreview — the clip preview used on the all-clips grid. Same caption engine
// as the editor: libass renders the clip's REAL compiled ASS (hook + captions +
// karaoke + whatever you edited), so grid == editor == the exported file. The clip
// video itself stays clean (reframe-only) → still fully editable.
//
// Custom controls (no native <video controls>) so the libass canvas can't clash
// with the browser control bar (that mismatch was the "crooked buttons"/"different
// player" problem). libass is lazy-mounted only when the card is on screen, so a
// grid of cards doesn't spin up N WASM workers at once.
// ────────────────────────────────────────────────────────────────────────────

export function ClipPreview({
  src,
  jobId,
  clipId,
  words,
  clipStart,
}: {
  src: string;
  jobId: string;
  clipId: string;
  words: Word[];
  clipStart: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const [visible, setVisible] = useState(false);
  const [ass, setAss] = useState<string | null>(null);
  const [libassFailed, setLibassFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [now, setNow] = useState(0);
  const [dur, setDur] = useState(0);

  // Mount the caption engine only when the card is actually on screen.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setVisible(true);
            io.disconnect();
          }
        }
      },
      { rootMargin: "200px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Fetch the clip's real ASS once visible (hook + captions + edit-state).
  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    getClipAss(jobId, clipId)
      .then((t) => !cancelled && setAss(t))
      .catch(() => !cancelled && setLibassFailed(true));
    return () => {
      cancelled = true;
    };
  }, [visible, jobId, clipId]);

  // Player state from the (clip-relative) video.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onTime = () => setNow(v.currentTime);
    const onMeta = () => setDur(v.duration || 0);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("loadedmetadata", onMeta);
    if (v.readyState >= 1) setDur(v.duration || 0);
    return () => {
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("loadedmetadata", onMeta);
    };
  }, []);

  useEffect(() => {
    const onFs = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
  };
  const toggleMute = () => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setMuted(v.muted);
  };
  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void containerRef.current?.requestFullscreen();
  };
  const scrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = videoRef.current;
    if (!v || !dur) return;
    v.currentTime = (Number(e.target.value) / 1000) * dur;
  };

  const useLibass = !!ass && !libassFailed;

  return (
    <div
      ref={containerRef}
      className={`group relative overflow-hidden rounded-t-lg bg-black ${
        fullscreen ? "flex h-full w-full items-center justify-center" : ""
      }`}
    >
      <div className={fullscreen ? "relative h-full aspect-[9/16]" : "relative aspect-[9/16] w-full"}>
        <video
          ref={videoRef}
          key={src}
          src={src}
          playsInline
          preload="metadata"
          onClick={togglePlay}
          className="absolute inset-0 size-full cursor-pointer bg-black object-contain"
        />

        {/* captions + hook — the exact ASS ffmpeg burns (matches the editor) */}
        {useLibass && (
          <LibassLayer
            videoRef={videoRef}
            assText={ass}
            sourceStart={0}
            onError={() => setLibassFailed(true)}
          />
        )}
        {/* fallback only if libass fails: at least show the captions (no hook) */}
        {!useLibass && libassFailed && words.length > 0 && (
          <CaptionOverlay words={words} clipStart={clipStart} videoRef={videoRef} />
        )}

        {/* big play button when paused */}
        {!playing && (
          <button
            type="button"
            aria-label="Play"
            onClick={togglePlay}
            className="absolute left-1/2 top-1/2 z-20 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/55 p-3.5 text-white backdrop-blur transition hover:bg-accent"
          >
            <Play className="size-6 fill-current" />
          </button>
        )}

        {/* slim control bar (own controls — consistent with the editor player) */}
        <div
          className={`absolute inset-x-0 bottom-0 z-30 flex items-center gap-2 bg-gradient-to-t from-black/85 to-transparent px-3 pb-2 pt-6 transition-opacity ${
            playing ? "opacity-0 group-hover:opacity-100" : "opacity-100"
          }`}
        >
          <button
            type="button"
            aria-label={playing ? "Pause" : "Play"}
            onClick={togglePlay}
            className="text-white/90 transition hover:text-white"
          >
            {playing ? <Pause className="size-4 fill-current" /> : <Play className="size-4 fill-current" />}
          </button>
          <span className="font-mono text-[10px] tabular-nums text-white/80">
            {mmss(now)} / {mmss(dur)}
          </span>
          <input
            type="range"
            min={0}
            max={1000}
            value={dur ? Math.round((now / dur) * 1000) : 0}
            onChange={scrub}
            aria-label="Scrub clip"
            className="h-1 min-w-0 flex-1 cursor-pointer appearance-none rounded-full bg-white/25 accent-accent"
          />
          <button
            type="button"
            aria-label={muted ? "Unmute" : "Mute"}
            onClick={toggleMute}
            className="text-white/80 transition hover:text-white"
          >
            {muted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
          </button>
          <button
            type="button"
            aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"}
            onClick={toggleFullscreen}
            className="text-white/80 transition hover:text-white"
          >
            {fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </button>
        </div>

        {/* caption engine still warming up */}
        {visible && !ass && !libassFailed && (
          <div className="pointer-events-none absolute right-2 top-2 z-20">
            <Loader2 className="size-4 animate-spin text-white/50" />
          </div>
        )}
      </div>
    </div>
  );
}
