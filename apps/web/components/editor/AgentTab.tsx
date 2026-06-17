"use client";

import { Loader2, Send, Sparkles, Square, Wand2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelAgentRun,
  getActiveAgentRun,
  getAgentRun,
  startAgentRun,
} from "@/lib/api";
import type { AgentEvent, AgentRun, AgentRunStatus } from "@/lib/types";

// ── Таб «Agent» (W3): чат-редактор клипа. Агент правит ИНТЕРВАЛ и ХУК тулзами (не субтитры,
// не кадр), показывает мысли/действия, фоновый прогон с поллингом и Stop (как у джоба).
// onAgentEdited() зовётся, когда агент изменил edit-state → редактор перечитывает edit/превью.

const POLL_MS = 1200;
const SUGGESTIONS = [
  "Start a few seconds earlier",
  "Make the hook punchier",
  "Trim the slow ending",
];

function isTerminal(s: AgentRunStatus | "idle"): boolean {
  return s === "done" || s === "failed" || s === "cancelled";
}

function EventRow({ ev, live }: { ev: AgentEvent; live: boolean }) {
  if (ev.role === "user") {
    return (
      <div className="ml-auto max-w-[85%] rounded-lg rounded-br-sm bg-surface-3 px-3 py-2 text-sm text-ink">
        {ev.text}
      </div>
    );
  }
  if (ev.role === "thinking") {
    // Спиннер крутится ТОЛЬКО пока прогон живой. После done/failed/cancelled мысли — это
    // история; крутящийся лоадер на каждой создавал ложное «всё ещё грузится» (фидбек фаундера).
    return (
      <p className="flex items-center gap-1.5 px-1 text-[11px] italic text-muted">
        {live ? (
          <Loader2 className="size-3 shrink-0 animate-spin" />
        ) : (
          <span className="size-1.5 shrink-0 rounded-full bg-muted/40" aria-hidden />
        )}
        {ev.text}
      </p>
    );
  }
  if (ev.role === "action") {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-1.5 text-xs text-ink">
        <Sparkles className="size-3.5 shrink-0 text-accent" />
        <span className="truncate">{ev.text}</span>
      </div>
    );
  }
  if (ev.role === "error") {
    return (
      <div className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-xs text-bad">
        {ev.text}
      </div>
    );
  }
  return ( // agent
    <div className="max-w-[90%] rounded-lg rounded-bl-sm bg-surface-2 px-3 py-2 text-sm text-ink">
      {ev.text}
    </div>
  );
}

export function AgentTab({
  jobId,
  clipId,
  busy,
  onAgentEdited,
}: {
  jobId: string;
  clipId: string;
  busy: boolean;
  onAgentEdited: () => void;
}) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<AgentRunStatus | "idle">("idle");
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const actionsSeen = useRef(0);

  const running = status === "running";

  const applyRun = useCallback(
    (run: AgentRun) => {
      const evs = run.events ?? [];
      setEvents(evs);
      setRunId(run.run_id);
      setStatus(run.status);
      // агент изменил edit-state (появились новые action) или завершился → перечитать редактор
      const nActions = evs.filter((e) => e.role === "action").length;
      if (nActions > actionsSeen.current || isTerminal(run.status)) {
        actionsSeen.current = nActions;
        onAgentEdited();
      }
    },
    [onAgentEdited],
  );

  const stopPolling = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const poll = useCallback(
    async (rid: string) => {
      try {
        const run = await getAgentRun(jobId, clipId, rid);
        applyRun(run);
        if (isTerminal(run.status)) stopPolling();
      } catch {
        /* транзиентно — следующий тик повторит */
      }
    },
    [jobId, clipId, applyRun, stopPolling],
  );

  const startPolling = useCallback(
    (rid: string) => {
      stopPolling();
      timer.current = setInterval(() => void poll(rid), POLL_MS);
    },
    [poll, stopPolling],
  );

  // реконнект к активному прогону при монтировании (компонент монтируется с key={clipId} →
  // на смену клипа ремаунт → стейт уже свежий, синхронный сброс setState не нужен).
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const run = await getActiveAgentRun(jobId, clipId);
        if (alive && run) {
          applyRun(run);
          if (run.status === "running") startPolling(run.run_id);
        }
      } catch {
        /* нет активного прогона — норм */
      }
    })();
    return () => {
      alive = false;
      stopPolling();
    };
  }, [jobId, clipId, applyRun, startPolling, stopPolling]);

  // автоскролл ленты вниз
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [events]);

  const send = useCallback(async () => {
    const msg = input.trim();
    if (!msg || running || busy) return;
    setError(null);
    setInput("");
    try {
      const run = await startAgentRun(jobId, clipId, msg);
      applyRun(run);
      if (run.status === "running") startPolling(run.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start the agent");
    }
  }, [input, running, busy, jobId, clipId, applyRun, startPolling]);

  const stop = useCallback(async () => {
    if (!runId) return;
    try {
      const run = await cancelAgentRun(jobId, clipId, runId);
      applyRun(run);
      stopPolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to stop the agent");
    }
  }, [runId, jobId, clipId, applyRun, stopPolling]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex items-center gap-2">
        <Wand2 className="size-4 text-accent" />
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Clip agent
        </p>
      </div>

      {/* лента */}
      <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
        {events.length === 0 ? (
          <div className="flex flex-col gap-2 py-2">
            <p className="text-xs leading-snug text-muted">
              Ask me to fix this clip’s timing or hook. I can move the start/end, trim, or rewrite
              the hook — I don’t change subtitles or framing.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={busy}
                  onClick={() => setInput(s)}
                  className="rounded-full border border-line bg-surface-2 px-2.5 py-1 text-[11px] text-muted transition hover:border-line-strong hover:text-ink disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          events.map((ev, i) => <EventRow key={i} ev={ev} live={running} />)
        )}
        {running && (
          <p className="flex items-center gap-1.5 px-1 text-[11px] text-muted">
            <Loader2 className="size-3 animate-spin" /> working…
          </p>
        )}
      </div>

      {error && <p className="text-[11px] text-bad">{error}</p>}

      {/* ввод / Stop */}
      <div className="flex items-end gap-2">
        <textarea
          value={input}
          disabled={busy || running}
          rows={2}
          maxLength={2000}
          placeholder={running ? "Agent is working…" : "Ask the agent to fix this clip…"}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          className="min-w-0 flex-1 resize-none rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink outline-none transition-colors focus:border-accent/60 disabled:opacity-60"
        />
        {running ? (
          <button
            type="button"
            onClick={() => void stop()}
            className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-bad/40 bg-bad/10 text-bad transition hover:bg-bad/20"
            aria-label="Stop agent"
          >
            <Square className="size-4" />
          </button>
        ) : (
          <button
            type="button"
            disabled={busy || !input.trim()}
            onClick={() => void send()}
            className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-white transition hover:opacity-90 disabled:opacity-40"
            aria-label="Send"
          >
            <Send className="size-4" />
          </button>
        )}
      </div>
    </div>
  );
}
