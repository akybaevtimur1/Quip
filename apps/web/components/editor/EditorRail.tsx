"use client";

import { Captions, Crop, Palette, Type, Wand2 } from "lucide-react";

// ────────────────────────────────────────────────────────────────────────────
// EditorRail — left icon-rail (Fixed-Studio shell). Single source of truth for
// the editor's panels: the `Tab` type and the `TABS` list live here and are
// imported back into ClipEditorScreen (no duplication). 5 items: Agent /
// Captions / Hook / Style / Frame. Keyboard 1-5 map to rail order (6 = no-op).
// ────────────────────────────────────────────────────────────────────────────

export type Tab = "captions" | "hook" | "style" | "frame" | "agent";

export const TABS: { id: Tab; label: string; icon: typeof Captions }[] = [
  { id: "agent", label: "Agent", icon: Wand2 },
  { id: "captions", label: "Captions", icon: Captions },
  { id: "hook", label: "Hook", icon: Type },
  { id: "style", label: "Style", icon: Palette },
  { id: "frame", label: "Frame", icon: Crop },
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
          <button
            key={id}
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
        );
      })}
    </nav>
  );
}
