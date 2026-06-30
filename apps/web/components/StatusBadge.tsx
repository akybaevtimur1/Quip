"use client";

import { useTranslations } from "next-intl";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { JobStatus } from "@/lib/types";

// Job-status pill, rebuilt on the shared Badge so the colors come from tokens (no
// off-palette ok/bad hex). Done = ok, failed = bad, cancelled = neutral, the live
// processing stages = accent (the single "working" signal). Labels are localized
// via the `status` message catalog.
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
  const t = useTranslations("status");
  return (
    <Badge tone={TONE[status]} dot>
      {t(status)}
    </Badge>
  );
}
