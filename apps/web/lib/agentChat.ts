// Pure chat-feed logic for the Clip Agent tab (AgentTab.tsx). Extracted into lib/ so the
// grouping + per-turn "is this still working?" derivation are unit-testable in isolation (the
// component itself pulls React/lucide/@-aliases that the node-env vitest can't resolve). PURE —
// no React, no I/O.

import type { AgentEvent } from "./types";

// thinking/action = internal progress (jargon for the user). Consecutive thinking/action events
// collapse into ONE unobtrusive "process" block (collapsed by default); the agent's final reply
// (role=agent) stays a first-class message.
export type ProcessGroup = { kind: "process"; steps: AgentEvent[] };
export type ChatItem = AgentEvent | ProcessGroup;

export function isProcessRole(role: AgentEvent["role"]): boolean {
  return role === "thinking" || role === "action";
}

export function groupEvents(events: AgentEvent[]): ChatItem[] {
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

// Per-item "is this turn's work still in flight?" flag. THE BUG (founder screenshot): the chat
// drove EVERY ProcessBlock's "Working on it…" spinner off a SINGLE global `running` flag, so
// starting a NEW run re-lit the spinner on every ALREADY-COMPLETED process group — multiple
// stale "Working on it…" pills stacked up. A completed turn is terminal HISTORY and must never
// re-enter loading. Only the CURRENT, in-flight run is live, and its process steps are always the
// LAST process group in the list (events are chronological; the live run's thinking/action append
// at the tail). So a process group is live iff the run is running AND it is the LAST process
// group. Non-process items (user/agent/error) never carry a spinner → always false. PURE.
export function processLiveFlags(items: ChatItem[], running: boolean): boolean[] {
  let lastProcessIdx = -1;
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    if ("kind" in it && it.kind === "process") lastProcessIdx = i;
  }
  return items.map((_, i) => running && i === lastProcessIdx);
}
