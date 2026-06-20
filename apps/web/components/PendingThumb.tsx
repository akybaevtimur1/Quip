"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { resolveUrl } from "./ClipCard";

// ────────────────────────────────────────────────────────────────────────────
// PendingThumb — client-side frame-grab poster for a clip that's still rendering.
//
// A pending clip has full metadata but no video file yet (video_url === ""). Rather
// than show a bare grey skeleton over its 9:16 area, we mount a hidden <video> on the
// lightweight PREVIEW PROXY (jobs/{jobId}/preview.mp4 — the source-aspect proxy the
// editor already uses), seek to the clip's start (in SOURCE seconds), and draw one
// frame to a <canvas>, center-cropped to 9:16. That canvas becomes the card's poster.
//
// The proxy is built in parallel and may 404 for a while early on; on any failure
// (load/seek error, proxy not ready) we fall back to the exact skeleton look ClipCard
// used before. The parent re-renders on each status poll, so keying the effect off the
// proxy URL lets a not-yet-ready proxy retry naturally on a later poll.
//
// A small "Rendering…" badge stays over the thumbnail either way, so it's always clear
// the clip isn't playable yet.
// ────────────────────────────────────────────────────────────────────────────

export function PendingThumb({ jobId, clipStart }: { jobId: string; clipStart: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // The proxy URL that produced the currently-drawn frame. `hasFrame` is derived:
  // a frame counts only if it was grabbed for the CURRENT proxyUrl, so when the URL
  // changes we fall back to the skeleton automatically — no synchronous reset needed
  // (which the React Compiler lint forbids inside an effect body).
  const [frameUrl, setFrameUrl] = useState<string | null>(null);

  const proxyUrl = resolveUrl(`jobs/${jobId}/preview.mp4`);
  const hasFrame = frameUrl === proxyUrl;

  useEffect(() => {
    const video = document.createElement("video");
    video.crossOrigin = "anonymous";
    video.muted = true;
    video.preload = "metadata";
    video.playsInline = true;

    let cancelled = false;

    const onLoadedData = () => {
      if (cancelled) return;
      // Seek to the clip's start (source seconds); the frame is grabbed on `seeked`.
      try {
        video.currentTime = clipStart;
      } catch {
        // Some browsers throw if currentTime is set before metadata; ignore — the
        // skeleton fallback stays up and the next poll re-mounts this effect.
      }
    };

    const onSeeked = () => {
      if (cancelled) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const vw = video.videoWidth;
      const vh = video.videoHeight;
      if (!vw || !vh) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // Center-crop the source frame (typically 16:9) to 9:16 and draw it 1:1 into a
      // 9:16 canvas. Cheap "this is the moment" cue; true reframed thumbs are out of scope.
      const targetRatio = 9 / 16;
      let sx: number;
      let sy: number;
      let sw: number;
      let sh: number;
      if (vw / vh > targetRatio) {
        // Source wider than 9:16 → crop the sides.
        sh = vh;
        sw = Math.round(vh * targetRatio);
        sx = Math.round((vw - sw) / 2);
        sy = 0;
      } else {
        // Source taller than 9:16 → crop top/bottom.
        sw = vw;
        sh = Math.round(vw / targetRatio);
        sx = 0;
        sy = Math.round((vh - sh) / 2);
      }
      canvas.width = sw;
      canvas.height = sh;
      try {
        ctx.drawImage(video, sx, sy, sw, sh, 0, 0, sw, sh);
        // Event-callback setState (not the effect body) — allowed by the lint.
        setFrameUrl(proxyUrl);
      } catch {
        // drawImage can throw (e.g. tainted canvas if CORS headers are missing) — keep
        // the skeleton; nothing is shown half-drawn.
      }
    };

    const onError = () => {
      // Proxy 404 / not ready / decode failure → stay on skeleton, retry next poll.
    };

    video.addEventListener("loadeddata", onLoadedData);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("error", onError);

    video.src = proxyUrl;
    video.load();

    return () => {
      cancelled = true;
      video.removeEventListener("loadeddata", onLoadedData);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("error", onError);
      video.removeAttribute("src");
      video.load();
    };
  }, [proxyUrl, clipStart]);

  return (
    <div className="relative aspect-[9/16] w-full overflow-hidden rounded-t-lg bg-surface-2">
      {/* Skeleton — visible until a frame is grabbed (and the only thing shown on fallback). */}
      {!hasFrame && (
        <>
          <div className="absolute inset-0 animate-pulse bg-surface-2" />
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 text-muted">
            <Loader2 className="size-6 animate-spin" />
            <span className="font-mono text-xs">Rendering…</span>
          </div>
        </>
      )}

      {/* Frame-grab poster — drawn into the canvas, filling the 9:16 area. */}
      <canvas
        ref={canvasRef}
        aria-hidden
        className={`absolute inset-0 size-full object-cover transition-opacity duration-300 ease-snappy ${
          hasFrame ? "opacity-100" : "opacity-0"
        }`}
      />

      {/* Always-on "Rendering…" badge — the clip isn't playable yet, frame or not. */}
      <span className="pointer-events-none absolute bottom-2 left-1/2 z-20 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-black/65 px-2.5 py-1 font-mono text-[10px] text-white/90 backdrop-blur">
        <Loader2 className="size-3 animate-spin" />
        Rendering…
      </span>
    </div>
  );
}
