import { describe, expect, it } from "vitest";
import type { AgentEvent } from "./types";
import { groupEvents, processLiveFlags } from "./agentChat";

// Bug (founder screenshot): in the CLIP AGENT chat, after the agent finished a run and replied,
// sending a NEW message re-lit the spinning "Working on it…" pill on the PREVIOUS, already-
// completed turns too — multiple stale "Working on it…" pills stacked up. Root cause: every
// ProcessBlock's `live` came from a SINGLE global `running` flag, so a fresh run flipped EVERY
// process group (incl. terminal history) back into the loading state. Only the CURRENT in-flight
// run's process group (always the LAST one) may show "Working on it…".

const ev = (role: AgentEvent["role"], text: string): AgentEvent => ({ role, text });

describe("groupEvents", () => {
  it("collapses consecutive thinking/action into one process group, keeps user/agent separate", () => {
    const items = groupEvents([
      ev("user", "trim the intro"),
      ev("thinking", "looking at the start"),
      ev("action", "moved start -1.2s"),
      ev("agent", "Trimmed the slow intro."),
    ]);
    expect(items.map((i) => ("kind" in i ? "process" : i.role))).toEqual([
      "user",
      "process",
      "agent",
    ]);
    const proc = items[1];
    expect("kind" in proc && proc.steps.length).toBe(2);
  });

  it("starts a NEW process group after a non-process event interrupts", () => {
    const items = groupEvents([
      ev("thinking", "a"),
      ev("agent", "done turn 1"),
      ev("thinking", "b"),
    ]);
    expect(items.filter((i) => "kind" in i)).toHaveLength(2);
  });
});

describe("processLiveFlags — only the in-flight run shows 'Working on it…'", () => {
  // Two completed turns then a third turn that is CURRENTLY running.
  const items = groupEvents([
    ev("user", "turn 1"),
    ev("thinking", "t1 work"),
    ev("agent", "turn 1 reply"),
    ev("user", "turn 2"),
    ev("thinking", "t2 work"),
    ev("agent", "turn 2 reply"),
    ev("user", "turn 3"),
    ev("thinking", "t3 work (in flight)"),
  ]);
  // index map: 0 user, 1 process(t1), 2 agent, 3 user, 4 process(t2), 5 agent, 6 user, 7 process(t3)

  it("THE BUG: when a new run is running, ONLY the last (current) process group is live", () => {
    const flags = processLiveFlags(items, true);
    expect(flags[1]).toBe(false); // turn 1 process — completed history, must NOT spin
    expect(flags[4]).toBe(false); // turn 2 process — completed history, must NOT spin
    expect(flags[7]).toBe(true); // turn 3 process — the live, in-flight run
    // exactly one live pill, never a stack
    expect(flags.filter(Boolean)).toHaveLength(1);
  });

  it("when NOTHING is running, no process group is live (all turns terminal)", () => {
    const flags = processLiveFlags(items, false);
    expect(flags.some(Boolean)).toBe(false);
  });

  it("non-process items (user/agent) are never live", () => {
    const flags = processLiveFlags(items, true);
    expect(flags[0]).toBe(false); // user
    expect(flags[2]).toBe(false); // agent reply
    expect(flags[6]).toBe(false); // user
  });

  it("a single completed run (no new run started) is not live", () => {
    const one = groupEvents([ev("user", "do it"), ev("thinking", "..."), ev("agent", "done")]);
    expect(processLiveFlags(one, false).some(Boolean)).toBe(false);
  });
});
