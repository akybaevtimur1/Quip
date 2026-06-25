"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { CoWatch, type Moment } from "./CoWatch";
import { getPreviewMoments } from "@/lib/api";

// Container for the co-watch processing view (Part 4): polls the worker for preview-moments and
// reveals them ONE AT A TIME (gentle stream) regardless of how the backend batches them (energy
// markers land after download, transcript markers after transcribe). The markers are real; the
// stagger is just pacing — the "labor illusion" done with the user's own content. ⚠️ Cosmetic:
// never influences clip selection. The dashboard unmounts this the instant real clips exist
// (handoff to the clip grid), so the opening act yields to the show.

const STAGE_LABEL: Record<string, string> = {
  queued: "Getting your video ready",
  downloading: "Getting your video ready",
  transcribing: "Listening to every word",
  selecting: "Finding the moments worth posting",
  rendering: "Cutting your clips",
};

export function CoWatchPanel({
  jobId,
  src,
  status,
  elapsed,
  cancellable = false,
  onStop,
}: {
  jobId: string;
  src: string;
  status: string;
  elapsed: number;
  // Stop (free-phase cancel, $0) — shown only while the worker reports cancellable, same as the stepper.
  cancellable?: boolean;
  onStop?: () => void;
}) {
  const [all, setAll] = useState<Moment[]>([]);
  const [shown, setShown] = useState(0);
  const [stopping, setStopping] = useState(false);

  // Poll the worker for the full set found so far (sorted by time).
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const ms = await getPreviewMoments(jobId);
        if (alive && ms.length) setAll([...ms].sort((a, b) => a.t - b.t));
      } catch {
        /* transient — keep polling */
      }
    };
    void tick();
    const id = setInterval(() => void tick(), 2000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [jobId]);

  // Reveal one more marker at a time (≈900ms) until caught up to what's been found.
  useEffect(() => {
    if (shown >= all.length) return;
    const id = setTimeout(() => setShown((s) => s + 1), 900);
    return () => clearTimeout(id);
  }, [shown, all.length]);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-start">
      <CoWatch
        src={src}
        moments={all.slice(0, shown)}
        stageLabel={STAGE_LABEL[status] ?? "Reading your video"}
        elapsed={elapsed}
      />
      {cancellable && onStop && (
        <button
          type="button"
          disabled={stopping}
          onClick={() => {
            setStopping(true);
            onStop();
          }}
          className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-sm text-muted transition hover:border-line-strong hover:text-ink disabled:opacity-50"
        >
          <X className="size-4" />
          {stopping ? "Stopping…" : "Stop · no charge"}
        </button>
      )}
    </div>
  );
}
