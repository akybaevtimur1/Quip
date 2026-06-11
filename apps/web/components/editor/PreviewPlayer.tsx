"use client";

import { Loader2, Maximize2, Minimize2, Pause, Play, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

// ── PreviewPlayer — превью 9:16 с СОБСТВЕННЫМИ контролами ──
// Видео = ИСТОЧНИК (source.mp4), залуплен в [outerStart, outerEnd). Нативные
// controls убраны: редактору нужны пауза-правка, скраб В КЛИП-времени и
// fullscreen НА КОНТЕЙНЕРЕ (иначе libass-канвас пропадает — грабля CC overlay).
// Слои поверх видео (libass, хит-зоны, тулбары) приходят как children.

export function PreviewPlayer({
  src,
  outerStart,
  outerEnd,
  videoRef,
  onTimeChange,
  children,
}: {
  src: string;
  outerStart: number;
  outerEnd: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onTimeChange?: (sec: number) => void;
  children?: React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [clipNow, setClipNow] = useState(0);

  const clipDur = Math.max(0.01, outerEnd - outerStart);

  // ── seek на старт интервала + луп в его границах ──
  useEffect(() => {
    const video = videoRef.current;
    if (!video || outerEnd <= outerStart) return;

    const seekToStart = () => {
      if (video.currentTime < outerStart || video.currentTime >= outerEnd) {
        try {
          video.currentTime = outerStart;
        } catch {
          /* до loadedmetadata seek может бросить — onLoaded повторит */
        }
      }
    };
    const onLoaded = () => {
      try {
        video.currentTime = outerStart;
      } catch {
        /* noop */
      }
    };
    const onTimeUpdate = () => {
      const t = video.currentTime;
      setClipNow(Math.max(0, Math.min(clipDur, t - outerStart)));
      onTimeChange?.(t);
      if (t >= outerEnd || t < outerStart - 0.3) seekToStart();
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onWaiting = () => setLoading(true);
    const onCanPlay = () => setLoading(false);

    if (video.readyState >= 1) onLoaded();
    if (video.readyState >= 2) setLoading(false);
    video.addEventListener("loadedmetadata", onLoaded);
    video.addEventListener("timeupdate", onTimeUpdate);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("waiting", onWaiting);
    video.addEventListener("canplay", onCanPlay);
    return () => {
      video.removeEventListener("loadedmetadata", onLoaded);
      video.removeEventListener("timeupdate", onTimeUpdate);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("waiting", onWaiting);
      video.removeEventListener("canplay", onCanPlay);
    };
  }, [outerStart, outerEnd, clipDur, videoRef, onTimeChange]);

  // ── fullscreen на контейнере ──
  useEffect(() => {
    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play();
    else video.pause();
  }, [videoRef]);

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void containerRef.current?.requestFullscreen();
  }, []);

  const toggleMute = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = !video.muted;
    setMuted(video.muted);
  }, [videoRef]);

  const handleScrub = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const video = videoRef.current;
      if (!video) return;
      const frac = Number(e.target.value) / 1000;
      try {
        video.currentTime = outerStart + frac * clipDur;
      } catch {
        /* noop */
      }
    },
    [videoRef, outerStart, clipDur],
  );

  return (
    <div
      ref={containerRef}
      className={`group relative overflow-hidden rounded-xl border border-line bg-black ${
        isFullscreen ? "flex items-center justify-center" : "aspect-[9/16]"
      }`}
    >
      <div className={isFullscreen ? "relative aspect-[9/16] h-full" : "absolute inset-0"}>
        {/* клик по видео = play/pause (как во всех редакторах) */}
        <video
          ref={videoRef}
          key={src}
          src={src}
          playsInline
          preload="auto"
          onClick={togglePlay}
          className="absolute inset-0 size-full cursor-pointer bg-black object-cover [object-position:center]"
        />

        {children}

        {/* загрузка большого источника */}
        {loading && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-black/40">
            <Loader2 className="size-8 animate-spin text-white/80" />
          </div>
        )}

        {/* большая кнопка play на паузе */}
        {!playing && !loading && (
          <button
            type="button"
            aria-label="Воспроизвести"
            onClick={togglePlay}
            className="absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/60 p-4 text-white backdrop-blur transition hover:bg-accent"
          >
            <Play className="size-7 fill-current" />
          </button>
        )}

        {/* ── контрол-бар (виден на hover и на паузе) ── */}
        <div
          className={`absolute inset-x-0 bottom-0 z-30 flex items-center gap-2 bg-gradient-to-t from-black/85 to-transparent px-3 pb-2 pt-6 transition-opacity ${
            playing ? "opacity-0 group-hover:opacity-100" : "opacity-100"
          }`}
        >
          <button
            type="button"
            aria-label={playing ? "Пауза" : "Воспроизвести"}
            onClick={togglePlay}
            className="text-white/90 transition hover:text-white"
          >
            {playing ? <Pause className="size-4 fill-current" /> : <Play className="size-4 fill-current" />}
          </button>

          <span className="font-mono text-[10px] tabular-nums text-white/80">
            {fmtSec(clipNow)} / {fmtSec(clipDur)}
          </span>

          <input
            type="range"
            min={0}
            max={1000}
            value={Math.round((clipNow / clipDur) * 1000)}
            onChange={handleScrub}
            aria-label="Перемотка клипа"
            className="h-1 min-w-0 flex-1 cursor-pointer appearance-none rounded-full bg-white/25 accent-accent"
          />

          <button
            type="button"
            aria-label={muted ? "Включить звук" : "Выключить звук"}
            onClick={toggleMute}
            className="text-white/80 transition hover:text-white"
          >
            {muted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
          </button>
          <button
            type="button"
            aria-label={isFullscreen ? "Выйти из полного экрана" : "Полный экран"}
            onClick={toggleFullscreen}
            className="text-white/80 transition hover:text-white"
          >
            {isFullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}

function fmtSec(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}
