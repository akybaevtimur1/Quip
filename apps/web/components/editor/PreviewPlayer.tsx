"use client";

import { Loader2, Maximize2, Minimize2, Pause, Play, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

// ── PreviewPlayer — превью 9:16 с СОБСТВЕННЫМИ контролами ──
// Видео = ИСТОЧНИК (source.mp4), залуплен в [outerStart, outerEnd). Нативные
// controls убраны: редактору нужны пауза-правка, скраб В КЛИП-времени и
// fullscreen НА КОНТЕЙНЕРЕ (иначе libass-канвас пропадает — грабля CC overlay).
// Слои поверх видео (libass, хит-зоны, тулбары) приходят как children.
//
// frame — РЕАЛЬНЫЙ режим кадра на текущий момент (из reframe-плана/override):
//   fill  → object-cover с реальным центром кропа (а не всегда центр кадра);
//   fit   → весь кадр + блюр-фон (как «горизонтальный вид» в рендере);
//   split → два синхронных окна верх/низ (как в рендере; aux-видео ведомые).
// Раньше превью ВСЕГДА показывало центр-кроп → на главной клип широкий,
// в редакторе «вертикальный» (фидбек фаундера). Точность — приближение CSS,
// финальная истина — рендер.

export interface FrameState {
  mode: "fill" | "fit" | "split";
  cx: number; // центр кропа [0..1] (fill / верх split)
  cxB: number; // низ split
}

export function PreviewPlayer({
  src,
  outerStart,
  outerEnd,
  videoRef,
  frame,
  onTimeChange,
  aspectClass = "aspect-[9/16]",
  children,
}: {
  src: string;
  outerStart: number;
  outerEnd: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  frame?: FrameState | null;
  onTimeChange?: (sec: number) => void;
  /** T5: класс соотношения сторон (aspect-[9/16] | aspect-[1/1] | aspect-[4/5] | aspect-[16/9]).
   *  Контейнер сам contain'ится: w-full + max-h-full + aspect → не распирает страницу. */
  aspectClass?: string;
  children?: React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const auxARef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [clipNow, setClipNow] = useState(0);

  const clipDur = Math.max(0.01, outerEnd - outerStart);
  const mode = frame?.mode ?? "fill";
  const cx = frame?.cx ?? 0.5;
  const cxB = frame?.cxB ?? 0.7;

  // ── блюр-фон (fit) ведомый: догоняет мастера ТОЛЬКО пока fit активен ──
  // (иначе 3 лишних декодера 300МБ-источника крутятся вхолостую и душат страницу)
  useEffect(() => {
    if (mode !== "fit") {
      auxARef.current?.pause();
      return;
    }
    let raf = 0;
    const tick = () => {
      const m = videoRef.current;
      const aux = auxARef.current;
      if (m && aux && aux.readyState >= 1) {
        if (Math.abs(aux.currentTime - m.currentTime) > 0.15) {
          try {
            aux.currentTime = m.currentTime;
          } catch {
            /* noop */
          }
        }
        if (m.paused && !aux.paused) aux.pause();
        else if (!m.paused && aux.paused) void aux.play().catch(() => {});
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [videoRef, mode]);

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
      className={`group relative mx-auto overflow-hidden rounded-xl border border-line bg-black ${
        isFullscreen ? "flex h-full w-full items-center justify-center" : `w-full max-h-full ${aspectClass}`
      }`}
    >
      <div className={isFullscreen ? `relative h-full ${aspectClass}` : "absolute inset-0"}>
        {/* fit: блюр-фон позади (весь кадр + рамки, как в рендере) */}
        <video
          ref={auxARef}
          key={`bg-${src}`}
          src={src}
          muted
          playsInline
          preload="metadata"
          className={`absolute inset-0 size-full scale-110 object-cover blur-xl brightness-50 ${
            mode === "fit" ? "" : "hidden"
          }`}
        />

        {/* мастер-видео: время+звук. fill=кроп с реальным центром; fit=весь кадр;
            split=прячем картинку (звук/часы живут), показываем две половины ниже */}
        <video
          ref={videoRef}
          key={src}
          src={src}
          playsInline
          preload="auto"
          onClick={togglePlay}
          className={`absolute inset-0 size-full cursor-pointer transition-[object-position] duration-300 ease-linear ${
            mode === "fit" ? "object-contain" : "object-cover"
          } ${mode === "split" ? "opacity-0" : ""}`}
          style={mode === "fill" ? { objectPosition: `${cx * 100}% 50%` } : undefined}
        />

        {/* split: два синхронных окна (верх/низ), каждое кропится вокруг своего центра */}
        <div
          className={`pointer-events-none absolute inset-0 flex-col bg-black ${
            mode === "split" ? "flex" : "hidden"
          }`}
        >
          <SplitHalf src={src} masterRef={videoRef} cx={cx} active={mode === "split"} />
          <SplitHalf src={src} masterRef={videoRef} cx={cxB} active={mode === "split"} />
        </div>

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
            aria-label="Play"
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
            aria-label={playing ? "Pause" : "Play"}
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
            aria-label={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
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

/** Половина split-превью: своё немое видео, ведомое мастером (rAF-синк). */
function SplitHalf({
  src,
  masterRef,
  cx,
  active,
}: {
  src: string;
  masterRef: React.RefObject<HTMLVideoElement | null>;
  cx: number;
  active: boolean;
}) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!active) {
      ref.current?.pause();
      return;
    }
    let raf = 0;
    const tick = () => {
      const m = masterRef.current;
      const v = ref.current;
      if (m && v && v.readyState >= 1) {
        if (Math.abs(v.currentTime - m.currentTime) > 0.15) {
          try {
            v.currentTime = m.currentTime;
          } catch {
            /* noop */
          }
        }
        if (m.paused && !v.paused) v.pause();
        else if (!m.paused && v.paused) void v.play().catch(() => {});
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, masterRef]);

  return (
    <div className="relative h-1/2 w-full overflow-hidden">
      <video
        ref={ref}
        src={src}
        muted
        playsInline
        preload="metadata"
        className="absolute inset-0 size-full object-cover transition-[object-position] duration-300 ease-linear"
        style={{ objectPosition: `${cx * 100}% 50%` }}
      />
    </div>
  );
}
