"use client";

import { ChevronRight, Loader2, Send, Square, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelAgentRun,
  getActiveAgentRun,
  getAgentRun,
  startAgentRun,
} from "@/lib/api";
import { Eyebrow } from "@/components/ui/Eyebrow";
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

// thinking/action = внутренний прогресс. Для юзера это шум на жаргоне («thought»/«action»),
// поэтому объединяем подряд идущие thinking/action в ОДИН ненавязчивый блок «процесса»
// (свёрнутый по умолчанию), а финальный ответ агента (role=agent) оставляем крупным.
type ProcessGroup = { kind: "process"; steps: AgentEvent[] };
type ChatItem = AgentEvent | ProcessGroup;

function isProcessRole(role: AgentEvent["role"]): boolean {
  return role === "thinking" || role === "action";
}

function groupEvents(events: AgentEvent[]): ChatItem[] {
  const items: ChatItem[] = [];
  for (const ev of events) {
    if (isProcessRole(ev.role)) {
      const last = items[items.length - 1];
      if (last && "kind" in last && last.kind === "process") {
        last.steps.push(ev);
      } else {
        items.push({ kind: "process", steps: [ev] });
      }
    } else {
      items.push(ev);
    }
  }
  return items;
}

// Свёрнутая «работа агента»: муфта-строка «Working…/Готово · N шагов» + раскрытие в
// человекочитаемые строки. Спиннер — ТОЛЬКО пока прогон живой (после терминала это история).
function ProcessBlock({ steps, live }: { steps: AgentEvent[]; live: boolean }) {
  const [open, setOpen] = useState(false);
  const summary = live ? "Working on it…" : `Done · ${steps.length} step${steps.length === 1 ? "" : "s"}`;
  return (
    <div className="rounded-lg border border-line bg-surface-2/60 text-muted">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-xs transition duration-150 ease-snappy hover:text-ink"
        aria-expanded={open}
      >
        {live ? (
          <Loader2 className="size-3 shrink-0 animate-spin" />
        ) : (
          <ChevronRight
            className={`size-3 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
            aria-hidden
          />
        )}
        <span className="font-medium">{summary}</span>
        {!live && <span className="ml-auto text-xs opacity-70">{open ? "Hide" : "Details"}</span>}
      </button>
      {open && (
        <ul className="space-y-1 border-t border-line px-3 pb-2 pt-1.5">
          {steps.map((s, i) => {
            // A committed action (the agent actually changed the clip) is the live signal →
            // coral dot + ink text. Pure thinking stays a quiet muted tick.
            const committed = s.role === "action";
            return (
              <li key={i} className="flex items-start gap-1.5 text-xs leading-snug">
                <span
                  className={`mt-1.5 size-1 shrink-0 rounded-pill ${
                    committed ? "bg-accent" : "bg-muted/50"
                  }`}
                  aria-hidden
                />
                <span className={committed ? "text-ink" : undefined}>{s.text}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function ChatItemRow({ item, live }: { item: ChatItem; live: boolean }) {
  if ("kind" in item) {
    return <ProcessBlock steps={item.steps} live={live} />;
  }
  const ev = item;
  if (ev.role === "user") {
    return (
      <div className="ml-auto max-w-[85%] rounded-lg rounded-br-sm bg-surface-3 px-3 py-2 text-sm text-ink">
        {ev.text}
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
  return ( // agent — финальный ответ: левый ряд с волосяной коралловой линией (не залитый
    // пузырь). Выравнивание + hairline-rule отличают ход агента от пузыря юзера справа.
    <div className="mr-auto max-w-[90%] border-l-2 border-accent/60 pl-3 text-sm leading-snug text-ink">
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
  // Оптимистичные сообщения юзера: показываем МГНОВЕННО при отправке, до того как сервер
  // вернёт прогон с эхом этого же сообщения. Реконсиляция: как только в серверной ленте
  // появляется столько же user-сообщений, сколько мы насчитали оптимистично, — снимаем эхо
  // (дедуп по числу user-событий, чтобы один и тот же текст дважды не задвоился).
  const [pendingUser, setPendingUser] = useState<string[]>([]);
  // отправка в полёте (POST /start ещё не вернулся) → блок ввода/кнопки против дабл-сенда,
  // даже до того как статус прогона стал "running".
  const [sending, setSending] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<AgentRunStatus | "idle">("idle");
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const actionsSeen = useRef(0);

  const running = status === "running";
  const inFlight = running || sending;

  const applyRun = useCallback(
    (run: AgentRun) => {
      const evs = run.events ?? [];
      setEvents(evs);
      // дедуп оптимистичных эх: сколько user-событий уже подтвердил сервер — столько и
      // снимаем из локальной очереди (FIFO). Лишние (ещё не доехавшие) остаются видимыми.
      const serverUserCount = evs.filter((e) => e.role === "user").length;
      setPendingUser((prev) => (serverUserCount > 0 ? prev.slice(serverUserCount) : prev));
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

  // автоскролл ленты вниз (на серверные события И на оптимистичное эхо юзера)
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [events, pendingUser]);

  const send = useCallback(async () => {
    const msg = input.trim();
    if (!msg || inFlight || busy) return;
    setError(null);
    setInput("");
    // оптимистичное эхо: сообщение юзера появляется в ленте СРАЗУ, не дожидаясь поллинга —
    // иначе кажется, что отправка не сработала, и его шлют повторно (фидбек фаундера).
    setPendingUser((prev) => [...prev, msg]);
    setSending(true);
    try {
      const run = await startAgentRun(jobId, clipId, msg);
      applyRun(run);
      if (run.status === "running") startPolling(run.run_id);
    } catch (e) {
      // не глушим: показываем ошибку и откатываем оптимистичное эхо (НЕ дедупится сервером,
      // т.к. прогон не стартовал) + возвращаем текст в поле, чтобы можно было повторить.
      setPendingUser((prev) => prev.slice(0, -1));
      setInput(msg);
      setError(e instanceof Error ? e.message : "Failed to start the agent");
    } finally {
      setSending(false);
    }
  }, [input, inFlight, busy, jobId, clipId, applyRun, startPolling]);

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

  // Лента = серверные события + ещё-не-подтверждённые оптимистичные эхо юзера, сгруппированные
  // (подряд идущие thinking/action → один свёрнутый блок «процесса»).
  const chatItems = useMemo<ChatItem[]>(() => {
    const optimistic: AgentEvent[] = pendingUser.map((text) => ({ role: "user", text }));
    return groupEvents([...events, ...optimistic]);
  }, [events, pendingUser]);
  const isEmpty = chatItems.length === 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex items-center gap-2">
        <Wand2 className="size-4 text-muted" />
        <Eyebrow tone="muted">Clip agent</Eyebrow>
      </div>

      {/* лента */}
      <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
        {isEmpty ? (
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
                  className="rounded-pill border border-line bg-surface-2 px-2.5 py-1 text-xs text-muted transition duration-150 ease-snappy hover:border-line-strong hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          chatItems.map((item, i) => <ChatItemRow key={i} item={item} live={running} />)
        )}
        {inFlight && (
          <p className="flex items-center gap-1.5 px-1 text-xs text-muted">
            <Loader2 className="size-3 animate-spin" /> Working on it…
          </p>
        )}
      </div>

      {error && <p className="text-xs text-bad">{error}</p>}

      {/* ввод / Stop */}
      <div className="flex items-end gap-2">
        <textarea
          value={input}
          disabled={busy || inFlight}
          rows={2}
          maxLength={2000}
          placeholder={inFlight ? "Agent is working…" : "Ask the agent to fix this clip…"}
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
            className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-bad/40 bg-bad/10 text-bad transition duration-150 ease-snappy hover:bg-bad/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-bad/40"
            aria-label="Stop agent"
          >
            <Square className="size-4" />
          </button>
        ) : (
          <button
            type="button"
            disabled={busy || sending || !input.trim()}
            onClick={() => void send()}
            className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-bg transition duration-150 ease-snappy hover:bg-accent-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:opacity-40"
            aria-label="Send"
          >
            {sending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </button>
        )}
      </div>
    </div>
  );
}
