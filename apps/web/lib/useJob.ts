"use client";

import { useCallback, useEffect, useState } from "react";
import { getJob } from "./api";
import type { Job } from "./types";

const POLL_MS = 2500;
const MAX_FAILS = 3; // 3 сетевых сбоя подряд → job считаем упавшим (фронт закладывает задержки бэка)

/**
 * Polling статуса job каждые 2.5с (effect по jobId). Стоп на done/failed.
 * 3 сетевых сбоя подряд → error. elapsed тикает локально. start/reset — управление.
 */
export function useJob() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const start = useCallback((id: string) => {
    setError(null);
    setJob(null);
    setElapsed(0);
    setJobId(id);
  }, []);

  const reset = useCallback(() => {
    setError(null);
    setJob(null);
    setElapsed(0);
    setJobId(null);
  }, []);

  useEffect(() => {
    if (!jobId) return;
    const id = jobId;
    let active = true;
    let fails = 0;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();
    const tick = setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 250);

    async function loop() {
      try {
        const j = await getJob(id);
        fails = 0;
        if (!active) return;
        setJob(j);
        if (j.status === "failed") {
          // Surface the backend reason (e.g. "video over the 90-min limit") instead of
          // leaving the UI stuck on "Preparing video…" with a frozen timer. The worker
          // already set jobs.error on failure — show it, don't swallow it. Strip the
          // internal "[stage]" dev-prefix so users see a clean message.
          const reason = (j.error || "Processing failed — please try again.").replace(
            /^\[[^\]]+\]\s*/,
            "",
          );
          setError(reason);
          clearInterval(tick);
          return;
        }
        if (j.status === "done") {
          clearInterval(tick);
          return;
        }
      } catch {
        fails += 1;
        if (fails >= MAX_FAILS) {
          if (active) {
            setError(`Lost connection to the worker (${MAX_FAILS} failed requests in a row)`);
          }
          clearInterval(tick);
          return;
        }
      }
      if (active) pollTimer = setTimeout(loop, POLL_MS);
    }
    void loop();

    return () => {
      active = false;
      clearInterval(tick);
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [jobId]);

  // jobId is exposed so the UI can stay in the "tracking" state the instant a job is started
  // (jobId set) — без него фаза падала в idle между submit и первым поллингом → мелькал дашборд.
  return { job, jobId, error, elapsed, start, reset };
}
