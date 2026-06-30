"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getJob } from "./api";
import { isConnectivityError } from "./connectionError";
import type { Job } from "./types";

const POLL_MS = 2500;
const MAX_BACKOFF_MS = 10_000; // reconnect backoff ceiling: 2.5s → 5s → 10s, then steady.

/**
 * Polling статуса job каждые 2.5с (effect по jobId). Стоп на done/failed.
 *
 * Disconnect resilience: a flaky connection must NOT look like a fatal failure. The job runs
 * server-side on Modal and stays ALIVE through a network blip, so a connectivity-class poll
 * error (offline / fetch TypeError / timeout — see `isConnectivityError`) does NOT abandon the
 * job. Instead we enter a `reconnecting` state, keep retrying with backoff, and re-poll the
 * instant the browser fires "online". Only a REAL HTTP/app error (or a `failed` status from the
 * worker) becomes a terminal `error`. elapsed тикает локально. start/reset/reconnectNow — управление.
 */
export function useJob() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  // Stable handle into the running poll loop so the UI ("Try now") and the "online" event can
  // force an immediate re-poll of the SAME job WITHOUT tearing down the effect or resetting
  // elapsed/job (which `start` would do).
  const pollNowRef = useRef<(() => void) | null>(null);

  const start = useCallback((id: string) => {
    setError(null);
    setReconnecting(false);
    setJob(null);
    setElapsed(0);
    setJobId(id);
  }, []);

  const reset = useCallback(() => {
    setError(null);
    setReconnecting(false);
    setJob(null);
    setElapsed(0);
    setJobId(null);
  }, []);

  // Force an immediate poll, skipping any pending backoff. No-op when no job is being tracked.
  const reconnectNow = useCallback(() => pollNowRef.current?.(), []);

  useEffect(() => {
    if (!jobId) return;
    const id = jobId;
    let active = true;
    let fails = 0;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();
    const tick = setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 250);

    function schedule(delay: number) {
      if (!active) return;
      if (pollTimer) clearTimeout(pollTimer);
      pollTimer = setTimeout(() => void loop(), delay);
    }

    async function loop() {
      try {
        const j = await getJob(id);
        if (!active) return;
        fails = 0;
        setReconnecting(false); // any success clears a reconnecting banner
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
        if (j.status === "done" || j.status === "cancelled") {
          // "cancelled" is a terminal user action (Stop) — stop polling, no error set.
          clearInterval(tick);
          return;
        }
      } catch (err) {
        if (!active) return;
        const online = typeof navigator === "undefined" ? true : navigator.onLine;
        if (isConnectivityError(err, online)) {
          // The job is alive server-side — a flaky connection must NOT abandon it. Enter the
          // calm "reconnecting" state and keep retrying with backoff; the "online" listener
          // below pulls us back immediately when the network returns. jobId is kept intact, so
          // the user never has to re-upload.
          fails += 1;
          setReconnecting(true);
          schedule(Math.min(POLL_MS * 2 ** (fails - 1), MAX_BACKOFF_MS));
          return;
        }
        // A genuine HTTP/app error (worker 500'd, job 404'd, …) → surface it and stop polling.
        setError(err instanceof Error ? err.message : String(err));
        clearInterval(tick);
        return;
      }
      schedule(POLL_MS);
    }

    pollNowRef.current = () => {
      if (!active) return;
      fails = 0; // a fresh attempt restarts the backoff ladder
      schedule(0);
    };

    // Reconnect the instant connectivity returns — don't wait out the backoff.
    const onOnline = () => pollNowRef.current?.();
    window.addEventListener("online", onOnline);

    void loop();

    return () => {
      active = false;
      clearInterval(tick);
      if (pollTimer) clearTimeout(pollTimer);
      window.removeEventListener("online", onOnline);
      pollNowRef.current = null;
    };
  }, [jobId]);

  // jobId is exposed so the UI can stay in the "tracking" state the instant a job is started
  // (jobId set) — без него фаза падала в idle между submit и первым поллингом → мелькал дашборд.
  return { job, jobId, error, reconnecting, elapsed, start, reset, reconnectNow };
}
