"use client";

import {
  ArrowLeft,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Film,
  Loader2,
  Palette,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ExportMenu } from "@/components/ExportMenu";
import { Button } from "@/components/ui/Button";
import type { StylePreferencePayload, StyleTemplate } from "@/lib/api";
import { TemplatesPanel } from "./TemplatesPanel";

// ── Хедер страницы редактора ──
// «← Все клипы» ведёт на /dashboard?job=<id> (deep-link грид восстанавливается, РЕАЛЬНАЯ навигация).
// ‹ › переключают клипы той же задачи IN-PAGE (Task 7): onSwitchClip — без remount, мгновенно
// (flush + queue-isolation + shallow-URL внутри ClipEditorScreen). «Все клипы» — настоящий push,
// который СНАЧАЛА дожимает несохранённые правки (onBeforeLeave = flushPending) → ничего не теряется.

export type RenderState =
  | { kind: "idle" }
  | { kind: "rendering"; elapsed: number }
  | { kind: "done" };

export function EditorHeader({
  jobId,
  clipId,
  clipIds,
  totalSec,
  downloadUrl,
  renderState,
  busy,
  dirty,
  saving,
  onBeforeLeave,
  onSwitchClip,
  onRender,
  templates,
  defaultTemplateId,
  onApplyTemplateClip,
  onApplyTemplateAll,
  onSaveTemplate,
  onUpdateTemplate,
  onDeleteTemplate,
  onSetDefaultTemplate,
  onError,
}: {
  jobId: string;
  clipId: string;
  clipIds: string[];
  totalSec: number;
  downloadUrl: string | null;
  renderState: RenderState;
  busy: boolean;
  /** Есть правки после последнего рендера → результат увидишь только после «Рендер». */
  dirty: boolean;
  /** Есть НЕсохранённые правки (debounce-PATCH в полёте) → индикатор «Сохраняю…». */
  saving?: boolean;
  /** Дожать несохранённые правки ПЕРЕД уходом со страницы (без потери данных). */
  onBeforeLeave?: () => Promise<void>;
  /** Переключить клип IN-PAGE (без remount) — flush/queue-isolation/URL внутри редактора. */
  onSwitchClip: (nextId: string) => void;
  onRender: () => void;
  // ── Style templates (global, cross-panel look reuse) — opened from a header popover ──
  /** The user's saved style templates + which one seeds new clips of future videos. */
  templates: StyleTemplate[];
  defaultTemplateId: string | null;
  /** Apply a template's look to THIS clip (instant). */
  onApplyTemplateClip: (look: StylePreferencePayload) => void;
  /** Apply a template to ALL clips (instant on this one, rest in background) → count. */
  onApplyTemplateAll: (look: StylePreferencePayload) => Promise<number>;
  /** Save the current look as a NAMED template (optionally the new-clip default). */
  onSaveTemplate: (name: string, setDefault: boolean) => Promise<void>;
  /** Overwrite an existing template's stored look with the CURRENT clip style (update in place). */
  onUpdateTemplate: (id: string) => Promise<void>;
  onDeleteTemplate: (id: string) => Promise<void>;
  onSetDefaultTemplate: (id: string, isDefault: boolean) => Promise<void>;
  /** Surface a template-action error in the editor's shared error banner. */
  onError: (msg: string) => void;
}) {
  const router = useRouter();
  const idx = clipIds.indexOf(clipId);
  const prevId = idx > 0 ? clipIds[idx - 1] : null;
  const nextId = idx >= 0 && idx < clipIds.length - 1 ? clipIds[idx + 1] : null;

  // Style-templates popover (global look reuse). Click-outside / Esc closes — mirrors ExportMenu.
  const [tplOpen, setTplOpen] = useState(false);
  const tplRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!tplOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (tplRef.current && !tplRef.current.contains(e.target as Node)) setTplOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setTplOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [tplOpen]);

  // Любая навигация: сначала дожать pending-правки, потом push (правки не теряются).
  const leaveTo = async (href: string) => {
    try {
      await onBeforeLeave?.();
    } catch {
      /* даже если flush упал — не блокируем уход (keepalive-эффект подстрахует) */
    }
    router.push(href);
  };

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-line bg-surface px-3 sm:gap-4 sm:px-4">
      {/* лево: назад + навигация по клипам */}
      <div className="flex min-w-0 items-center gap-1.5 sm:gap-3">
        <button
          type="button"
          onClick={() => leaveTo(`/dashboard?job=${jobId}`)}
          aria-label="All clips"
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-2 text-sm text-muted transition hover:border-accent/50 hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40 sm:px-3 sm:py-1.5"
        >
          <ArrowLeft className="size-4" />
          <span className="hidden sm:inline">All clips</span>
        </button>

        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={!prevId || busy}
            onClick={() => prevId && onSwitchClip(prevId)}
            title="Previous clip"
            aria-label="Previous clip"
            className="inline-flex size-9 items-center justify-center rounded-lg border border-line text-muted transition enabled:hover:border-accent/50 enabled:hover:text-ink disabled:opacity-30 sm:size-8"
          >
            <ChevronLeft className="size-4" />
          </button>
          <span className="min-w-[58px] text-center font-display text-sm font-semibold text-ink sm:min-w-[88px]">
            {idx >= 0 ? (
              <>
                <span className="sm:hidden">{`${idx + 1}/${clipIds.length}`}</span>
                <span className="hidden sm:inline">{`Clip ${idx + 1} of ${clipIds.length}`}</span>
              </>
            ) : (
              clipId
            )}
          </span>
          <button
            type="button"
            disabled={!nextId || busy}
            onClick={() => nextId && onSwitchClip(nextId)}
            title="Next clip"
            aria-label="Next clip"
            className="inline-flex size-9 items-center justify-center rounded-lg border border-line text-muted transition enabled:hover:border-accent/50 enabled:hover:text-ink disabled:opacity-30 sm:size-8"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>

        <span className="hidden font-mono text-xs tabular-nums text-muted sm:inline">
          {totalSec.toFixed(1)}s
        </span>
      </div>

      {/* право: статус сохранения + рендера + действия */}
      <div className="flex shrink-0 items-center gap-2">
        {/* Calm status-line: saving / not-saved-to-file / rendering / done. A single quiet
            row of mono readouts — the "click Render" nudge is informative, not shouty. */}
        {saving && (
          <span
            title="Saving your edits…"
            className="inline-flex items-center gap-1.5 text-xs text-muted"
          >
            <Loader2 className="size-3 animate-spin" />
            <span className="hidden sm:inline">Saving…</span>
          </span>
        )}
        {dirty && renderState.kind !== "rendering" && (
          <span
            title="The preview already shows your edits live. The downloadable file is still the old one. Click “Render” to write edits to the file."
            className="inline-flex items-center gap-1.5 text-xs text-warn"
          >
            <span className="size-1.5 rounded-pill bg-warn" />
            <span className="hidden sm:inline">Edits not yet in the file</span>
            <span className="sm:hidden">not saved</span>
          </span>
        )}
        {renderState.kind === "rendering" && (
          <span className="inline-flex items-center gap-1.5 font-mono text-xs tabular-nums text-accent">
            <Loader2 className="size-3.5 animate-spin" />
            Rendering… {renderState.elapsed}s
          </span>
        )}
        {renderState.kind === "done" && (
          <span className="inline-flex items-center gap-1.5 text-xs text-ok">
            <CheckCircle className="size-3.5" />
            Done
          </span>
        )}
        {/* Style templates: a GLOBAL look (captions + highlight + hook + position/size/timing)
            reused across clips/videos. A header popover (not a tab) signals it acts over the
            WHOLE look, above the 4-tab editing flow. */}
        <div ref={tplRef} className="relative">
          <button
            type="button"
            aria-haspopup="dialog"
            aria-expanded={tplOpen}
            onClick={() => setTplOpen((v) => !v)}
            title="Style templates — save a look, reuse it on any clip"
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-2 text-sm text-muted transition hover:border-accent/50 hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40 sm:py-1.5"
          >
            <Palette className="size-4" />
            <span className="hidden sm:inline">Style templates</span>
          </button>
          {tplOpen && (
            <div
              role="dialog"
              aria-label="Style templates"
              className="absolute right-0 top-full z-50 mt-2 w-[22rem] max-w-[calc(100vw-1.5rem)] rounded-xl border border-line bg-surface p-3 shadow-xl"
            >
              <TemplatesPanel
                templates={templates}
                defaultTemplateId={defaultTemplateId}
                busy={busy}
                onError={onError}
                onApplyTemplateClip={onApplyTemplateClip}
                onApplyTemplateAll={onApplyTemplateAll}
                onSaveTemplate={onSaveTemplate}
                onUpdateTemplate={onUpdateTemplate}
                onDeleteTemplate={onDeleteTemplate}
                onSetDefaultTemplate={onSetDefaultTemplate}
              />
            </div>
          )}
        </div>

        <Button
          variant="accent"
          size="sm"
          disabled={busy || renderState.kind === "rendering"}
          onClick={onRender}
        >
          <Film className="size-4" />
          Render
        </Button>
        <ExportMenu
          jobId={jobId}
          clipId={clipId}
          bakedUrl={downloadUrl}
          dirty={dirty}
          align="right"
        />
      </div>
    </header>
  );
}
