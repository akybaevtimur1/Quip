"use client";

import { ArrowLeft, CheckCircle, ChevronLeft, ChevronRight, Film, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { ExportMenu } from "@/components/ExportMenu";
import { Button } from "@/components/ui/Button";

// ── Хедер страницы редактора ──
// «← Все клипы» ведёт на /dashboard?job=<id> (deep-link грид восстанавливается).
// ‹ › переключают клипы той же задачи. ЛЮБАЯ навигация СНАЧАЛА дожимает несохранённые
// правки (onBeforeLeave = flushPending) → уход НИКОГДА не теряет правки (B-#5).

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
  onRender,
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
  onRender: () => void;
}) {
  const router = useRouter();
  const idx = clipIds.indexOf(clipId);
  const prevId = idx > 0 ? clipIds[idx - 1] : null;
  const nextId = idx >= 0 && idx < clipIds.length - 1 ? clipIds[idx + 1] : null;

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
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line bg-surface px-4">
      {/* лево: назад + навигация по клипам */}
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={() => leaveTo(`/dashboard?job=${jobId}`)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm text-muted transition hover:border-accent/50 hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          <ArrowLeft className="size-4" />
          All clips
        </button>

        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={!prevId || busy}
            onClick={() => prevId && leaveTo(`/edit/${jobId}/${prevId}`)}
            title="Previous clip"
            className="inline-flex size-8 items-center justify-center rounded-lg border border-line text-muted transition enabled:hover:border-accent/50 enabled:hover:text-ink disabled:opacity-30"
          >
            <ChevronLeft className="size-4" />
          </button>
          <span className="min-w-[88px] text-center font-display text-sm font-semibold text-ink">
            {idx >= 0 ? `Clip ${idx + 1} of ${clipIds.length}` : clipId}
          </span>
          <button
            type="button"
            disabled={!nextId || busy}
            onClick={() => nextId && leaveTo(`/edit/${jobId}/${nextId}`)}
            title="Next clip"
            className="inline-flex size-8 items-center justify-center rounded-lg border border-line text-muted transition enabled:hover:border-accent/50 enabled:hover:text-ink disabled:opacity-30"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>

        <span className="hidden font-mono text-xs text-muted sm:inline">{totalSec.toFixed(1)}s</span>
      </div>

      {/* право: статус сохранения + рендера + действия */}
      <div className="flex shrink-0 items-center gap-2">
        {saving && (
          <span
            title="Saving your edits…"
            className="inline-flex items-center gap-1.5 rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-muted"
          >
            <Loader2 className="size-3 animate-spin" />
            <span className="hidden sm:inline">Saving…</span>
          </span>
        )}
        {dirty && renderState.kind !== "rendering" && (
          <span
            title="The preview already shows your edits live. The downloadable file is still the old one. Click “Render” to write edits to the file."
            className="inline-flex items-center gap-1.5 rounded-md border border-warn/40 bg-warn/10 px-2.5 py-1.5 text-xs text-warn"
          >
            <span className="size-1.5 animate-pulse rounded-full bg-warn" />
            <span className="hidden sm:inline">Click “Render” to save to file</span>
            <span className="sm:hidden">not saved</span>
          </span>
        )}
        {renderState.kind === "rendering" && (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-accent/30 bg-surface-2 px-3 py-1.5 font-mono text-xs text-accent">
            <Loader2 className="size-3.5 animate-spin" />
            Rendering… {renderState.elapsed}s
          </span>
        )}
        {renderState.kind === "done" && (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-ok/40 bg-ok/10 px-3 py-1.5 text-xs text-ok">
            <CheckCircle className="size-3.5" />
            Done
          </span>
        )}
        <Button
          variant="accent"
          size="sm"
          disabled={busy || renderState.kind === "rendering"}
          onClick={onRender}
          className={`relative ${dirty && renderState.kind === "idle" ? "ring-2 ring-warn/60" : ""}`}
        >
          <Film className="size-4" />
          Render
          {dirty && renderState.kind === "idle" && (
            <span className="absolute -right-1 -top-1 size-2.5 rounded-full bg-warn" />
          )}
        </Button>
        <ExportMenu jobId={jobId} clipId={clipId} bakedUrl={downloadUrl} align="right" />
      </div>
    </header>
  );
}
