"use client";

import { Fragment } from "react";
import { Captions, Crop, Type, Wand2 } from "lucide-react";

// ────────────────────────────────────────────────────────────────────────────
// EditorRail — left icon-rail (Fixed-Studio shell). Single source of truth for
// the editor's panels: the `Tab` type and the `TABS` list live here and are
// imported back into ClipEditorScreen (no duplication). 4 items.
//
// Order = the manual editing flow, most-edited first, AI agent set apart last:
//   1 "Subtitles" = caption text (lines) + caption style (was Captions + Style;
//     they edited the SAME object → one tab). The default tab → keyboard 1.
//   2 "Hook"      = the top hook overlay (text + its own style).
//   3 "Frame"     = output aspect + whole-clip framing mode + per-shot framing
//     (was Frame + Shots; both write reframe_overrides → one tab).
//   4 "Agent"     = the AI chat that can do ~99% of editing — a distinct *mode*,
//     so it sits last, below a divider. Keyboard 1-4 map to this order.
// ────────────────────────────────────────────────────────────────────────────

export type Tab = "subtitles" | "hook" | "frame" | "agent";

export const TABS: { id: Tab; label: string; icon: typeof Captions }[] = [
  { id: "subtitles", label: "Subtitles", icon: Captions },
  { id: "hook", label: "Hook", icon: Type },
  { id: "frame", label: "Frame", icon: Crop },
  { id: "agent", label: "Agent", icon: Wand2 },
];

export function EditorRail({
  active,
  onSelect,
  agentActive = false,
}: {
  active: Tab;
  onSelect: (tab: Tab) => void;
  /** Inert this task — a seam for a later agent-activity badge. */
  agentActive?: boolean;
}) {
  return (
    <nav
      aria-label="Editor panels"
      className="flex shrink-0 gap-1 rounded-xl border border-line bg-surface p-1 lg:h-full lg:flex-col"
    >
      {TABS.map(({ id, label, icon: Icon }) => {
        const isActive = active === id;
        return (
          <Fragment key={id}>
            {/* Agent is a different KIND of tool (AI chat) → set it apart with a divider. */}
            {id === "agent" && (
              <span
                aria-hidden
                className="mx-1 my-auto h-5 w-px self-center bg-line lg:mx-auto lg:my-1 lg:h-px lg:w-5"
              />
            )}
            <button
              type="button"
              onClick={() => onSelect(id)}
              aria-current={isActive ? "page" : undefined}
              title={label}
              className={`relative flex flex-1 flex-col items-center justify-center gap-1 rounded-lg px-3 py-2.5 text-[11px] font-semibold transition lg:flex-none lg:py-3 ${
                isActive
                  ? "bg-surface-3 text-accent shadow-[0_1px_2px_rgba(0,0,0,.4)]"
                  : "text-muted hover:bg-surface-2 hover:text-ink"
              }`}
            >
              <span className="relative">
                <Icon className="size-5" />
                {/* Agent activity badge-dot — inert this task (agentActive never set). */}
                {id === "agent" && agentActive && (
                  <span className="absolute -right-1 -top-1 size-2 rounded-full bg-accent ring-2 ring-surface" />
                )}
              </span>
              {label}
            </button>
          </Fragment>
        );
      })}
    </nav>
  );
}
