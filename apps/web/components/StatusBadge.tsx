import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { JobStatus } from "@/lib/types";

// Job-status pill, rebuilt on the shared Badge so the colors come from tokens (no
// off-palette ok/bad hex). Done = ok, failed = bad, cancelled = neutral, the live
// processing stages = accent (the single "working" signal).
const LABEL: Record<JobStatus, string> = {
  queued: "Queued",
  downloading: "Preparing",
  transcribing: "Transcribing",
  selecting: "Selecting",
  rendering: "Rendering",
  done: "Done",
  failed: "Failed",
  cancelled: "Stopped",
};

const TONE: Record<JobStatus, BadgeTone> = {
  queued: "accent",
  downloading: "accent",
  transcribing: "accent",
  selecting: "accent",
  rendering: "accent",
  done: "ok",
  failed: "bad",
  cancelled: "neutral",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <Badge tone={TONE[status]} dot>
      {LABEL[status]}
    </Badge>
  );
}
