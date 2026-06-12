"use client";

import { ArrowLeft, CheckCircle, ChevronLeft, ChevronRight, Film, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ExportMenu } from "@/components/ExportMenu";

// ── Хедер страницы редактора ──
// «← Все клипы» ведёт на /?job=<id> (deep-link главной восстанавливает грид —
// возврат БЕЗ потери состояния). ‹ › переключают клипы той же задачи.

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
  onRender: () => void;
}) {
  const router = useRouter();
  const idx = clipIds.indexOf(clipId);
  const prevId = idx > 0 ? clipIds[idx - 1] : null;
  const nextId = idx >= 0 && idx < clipIds.length - 1 ? clipIds[idx + 1] : null;

  const goTo = (id: string) => router.push(`/edit/${jobId}/${id}`);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line bg-surface px-4">
      {/* лево: назад + навигация по клипам */}
      <div className="flex min-w-0 items-center gap-3">
        <Link
          href={`/?job=${jobId}`}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm text-muted transition hover:border-accent/50 hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          <ArrowLeft className="size-4" />
          Все клипы
        </Link>

        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={!prevId || busy}
            onClick={() => prevId && goTo(prevId)}
            title="Предыдущий клип"
            className="inline-flex size-8 items-center justify-center rounded-lg border border-line text-muted transition enabled:hover:border-accent/50 enabled:hover:text-ink disabled:opacity-30"
          >
            <ChevronLeft className="size-4" />
          </button>
          <span className="min-w-[88px] text-center font-display text-sm font-semibold text-ink">
            {idx >= 0 ? `Клип ${idx + 1} из ${clipIds.length}` : clipId}
          </span>
          <button
            type="button"
            disabled={!nextId || busy}
            onClick={() => nextId && goTo(nextId)}
            title="Следующий клип"
            className="inline-flex size-8 items-center justify-center rounded-lg border border-line text-muted transition enabled:hover:border-accent/50 enabled:hover:text-ink disabled:opacity-30"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>

        <span className="hidden font-mono text-xs text-muted sm:inline">{totalSec.toFixed(1)}s</span>
      </div>

      {/* право: статус рендера + действия */}
      <div className="flex shrink-0 items-center gap-2">
        {dirty && renderState.kind !== "rendering" && (
          <span
            title="Превью уже показывает правки, но скачиваемый файл — старый. Нажми «Рендер», чтобы применить."
            className="hidden items-center gap-1.5 rounded-lg border border-amber-600/40 bg-amber-900/20 px-3 py-1.5 text-xs text-amber-300 md:inline-flex"
          >
            <span className="size-1.5 animate-pulse rounded-full bg-amber-400" />
            Правки не в рендере
          </span>
        )}
        {renderState.kind === "rendering" && (
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-accent/30 bg-accent/10 px-3 py-1.5 font-mono text-xs text-accent">
            <Loader2 className="size-3.5 animate-spin" />
            Рендер… {renderState.elapsed}s
          </span>
        )}
        {renderState.kind === "done" && (
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-green-700/40 bg-green-900/25 px-3 py-1.5 text-xs text-green-400">
            <CheckCircle className="size-3.5" />
            Готово
          </span>
        )}
        <button
          type="button"
          disabled={busy || renderState.kind === "rendering"}
          onClick={onRender}
          className={`relative inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-accent-2 disabled:opacity-40 ${
            dirty && renderState.kind === "idle" ? "ring-2 ring-amber-400/60" : ""
          }`}
        >
          <Film className="size-4" />
          Рендер
          {dirty && renderState.kind === "idle" && (
            <span className="absolute -right-1 -top-1 size-2.5 rounded-full bg-amber-400" />
          )}
        </button>
        <ExportMenu jobId={jobId} clipId={clipId} subtitledUrl={downloadUrl} align="right" />
      </div>
    </header>
  );
}
