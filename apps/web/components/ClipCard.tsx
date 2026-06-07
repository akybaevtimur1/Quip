import { Download } from "lucide-react";
import { clipRange } from "@/lib/format";
import type { ClipOut } from "@/lib/types";
import { ReasonChip } from "./ReasonChip";

const WORKER_BASE = process.env.NEXT_PUBLIC_WORKER_URL ?? "";

function resolveUrl(videoUrl: string): string {
  if (videoUrl.startsWith("http") || videoUrl.startsWith("/")) return videoUrl;
  return `${WORKER_BASE}/${videoUrl}`;
}

export function ClipCard({ clip }: { clip: ClipOut }) {
  const src = resolveUrl(clip.video_url);
  return (
    <article className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-3">
      <div className="relative overflow-hidden rounded-xl bg-surface-2">
        <video
          src={src}
          controls
          preload="metadata"
          playsInline
          className="aspect-[9/16] w-full bg-black object-contain"
        />
        <span className="absolute left-2 top-2">
          <ReasonChip type={clip.type} />
        </span>
      </div>

      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-muted">{clipRange(clip.start, clip.end)}</span>
        <span className="font-mono text-sm font-semibold text-ink">{clip.score.toFixed(2)}</span>
      </div>

      <p className="text-sm leading-snug text-ink">{clip.reason}</p>

      {clip.transcript ? (
        <p className="line-clamp-2 text-xs leading-snug text-muted">«{clip.transcript}»</p>
      ) : null}

      <a
        href={src}
        download
        className="mt-1 inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-ink transition hover:border-accent/50 hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
      >
        <Download className="size-4" />
        Скачать
      </a>
    </article>
  );
}
