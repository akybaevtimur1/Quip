"use client";

import { CheckCircle, Film, Loader2, Scissors } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  extendClip,
  getClipAnalysis,
  getClipEdit,
  getRenderStatus,
  startRenderClip,
  trimClip,
} from "@/lib/api";
import type { ClipEdit, Word } from "@/lib/types";

const WORKER_BASE = process.env.NEXT_PUBLIC_WORKER_URL ?? "";

function resolveUrl(url: string) {
  if (!url || url.startsWith("http")) return url;
  return `${WORKER_BASE}/${url}`;
}

interface ClipEditorProps {
  jobId: string;
  clipId: string;
  onRenderDone: (newVideoUrl: string) => void;
}

type Phase = "loading" | "ready" | "saving" | "rendering" | "done" | "error";

export default function ClipEditor({ jobId, clipId, onRenderDone }: ClipEditorProps) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<ClipEdit | null>(null);
  const [words, setWords] = useState<Word[]>([]);
  const [globalIndices, setGlobalIndices] = useState<number[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [extendSec, setExtendSec] = useState<string>("5");
  const [renderElapsed, setRenderElapsed] = useState(0);
  const [loadKey, setLoadKey] = useState(0);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      setPhase("loading");
      setError(null);
      setSelected(new Set());
      try {
        const [editData, analysisData] = await Promise.all([
          getClipEdit(jobId, clipId),
          getClipAnalysis(jobId, clipId),
        ]);
        if (cancelled) return;
        setEdit(editData);
        setWords(analysisData.words);
        setGlobalIndices((editData.captions.replies ?? []).flatMap((r) => r.word_refs));
        setPhase("ready");
      } catch (e) {
        if (cancelled) return;
        setError(String(e));
        setPhase("error");
      }
    }
    fetchData();
    return () => { cancelled = true; stopPoll(); };
  }, [jobId, clipId, loadKey, stopPoll]);

  const toggleWord = (pos: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(pos)) next.delete(pos); else next.add(pos);
      return next;
    });
  };

  const handleTrim = async () => {
    if (!edit || selected.size === 0) return;
    const wordIndices = Array.from(selected).map((pos) => globalIndices[pos]);
    setPhase("saving");
    setError(null);
    try {
      const newEdit = await trimClip(jobId, clipId, edit.version ?? 1, wordIndices);
      const analysisData = await getClipAnalysis(jobId, clipId);
      setEdit(newEdit);
      setWords(analysisData.words);
      setGlobalIndices((newEdit.captions.replies ?? []).flatMap((r) => r.word_refs));
      setSelected(new Set());
      setPhase("ready");
    } catch (e) {
      const msg = String(e);
      // Version conflict: auto-reload state so user can simply retry.
      if (msg.includes("conflict") || msg.includes("409")) {
        setError("Данные обновились — попробуй ещё раз");
        setLoadKey((k) => k + 1);
      } else {
        setError(msg);
        setPhase("ready");
      }
    }
  };

  const handleExtend = async (secs: number) => {
    if (!edit) return;
    const lastInterval = edit.source_intervals[edit.source_intervals.length - 1];
    if (!lastInterval) return;
    const newEnd = lastInterval.source_end + secs;
    setPhase("saving");
    setError(null);
    try {
      const newEdit = await extendClip(jobId, clipId, edit.version ?? 1, "end", newEnd);
      const analysisData = await getClipAnalysis(jobId, clipId);
      setEdit(newEdit);
      setWords(analysisData.words);
      setGlobalIndices((newEdit.captions.replies ?? []).flatMap((r) => r.word_refs));
      setSelected(new Set());
      setPhase("ready");
    } catch (e) {
      const msg = String(e);
      // Version conflict: auto-reload state so user can simply retry.
      if (msg.includes("conflict") || msg.includes("409")) {
        setError("Данные обновились — попробуй ещё раз");
        setLoadKey((k) => k + 1);
      } else {
        setError(msg);
        setPhase("ready");
      }
    }
  };

  const handleRender = async () => {
    if (!edit) return;
    setPhase("rendering");
    setRenderElapsed(0);
    setError(null);
    stopPoll();
    try {
      await startRenderClip(jobId, clipId);
    } catch (e) {
      setError(String(e));
      setPhase("ready");
      return;
    }
    // elapsed timer
    timerRef.current = setInterval(() => setRenderElapsed((s) => s + 1), 1000);
    // status poll
    pollRef.current = setInterval(async () => {
      try {
        const st = await getRenderStatus(jobId, clipId);
        if (st.status === "done" && st.video_url) {
          stopPoll();
          setPhase("done");
          onRenderDone(resolveUrl(st.video_url));
        } else if (st.status === "failed") {
          stopPoll();
          setError(st.error ?? "Render failed");
          setPhase("ready");
        }
      } catch { /* keep polling */ }
    }, 2000);
  };

  // ── loading skeleton ──
  if (phase === "loading") {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted">
        <Loader2 className="size-4 animate-spin" />
        Loading transcript…
      </div>
    );
  }

  // ── fatal error (no data at all) ──
  if (phase === "error" && !edit) {
    return (
      <div className="space-y-2 py-4 text-center text-sm">
        <p className="text-red-400">{error}</p>
        <button
          onClick={() => setLoadKey((k) => k + 1)}
          className="rounded-lg border border-line px-3 py-1.5 text-xs text-muted hover:text-ink transition-colors"
        >
          Try again
        </button>
      </div>
    );
  }

  const totalSec = edit
    ? edit.source_intervals.reduce((s, iv) => s + (iv.source_end - iv.source_start), 0)
    : 0;
  const busy = phase === "saving" || phase === "rendering";
  const cutCount = edit
    ? edit.source_intervals.length - 1
    : 0;

  return (
    <div className="divide-y divide-line">

      {/* ── HEADER ── */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <Scissors className="size-4 text-accent" />
          <span className="font-medium text-ink text-sm">Edit clip</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted font-mono">
          <span>{totalSec.toFixed(1)}s</span>
          {cutCount > 0 && (
            <span className="rounded-full bg-accent/15 px-2 py-0.5 text-accent">
              {cutCount} cut{cutCount > 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {/* ── ERROR BANNER ── */}
      {error && (
        <div className="px-4 py-2 text-xs text-red-400 bg-red-900/20">
          {error}
        </div>
      )}

      {/* ── STEP 1: CUT WORDS ── */}
      <div className="px-4 py-3 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider">
            1 · Выбери слова для вырезания
          </p>
          {selected.size > 0 && (
            <button
              onClick={() => setSelected(new Set())}
              className="text-xs text-muted hover:text-ink transition-colors"
            >
              Сбросить
            </button>
          )}
        </div>

        {/* words grid */}
        <div className="flex flex-wrap gap-1 max-h-44 overflow-y-auto rounded-xl border border-line bg-surface p-2">
          {words.map((w, i) => (
            <button
              key={i}
              disabled={busy}
              onClick={() => toggleWord(i)}
              title={`${w.start.toFixed(1)}s – ${w.end.toFixed(1)}s`}
              className={[
                "rounded-md px-2 py-1 text-xs transition-all select-none",
                selected.has(i)
                  ? "bg-red-500/20 text-red-400 line-through ring-1 ring-red-500/40"
                  : "bg-surface-2 text-ink hover:bg-surface-2 hover:ring-1 hover:ring-line",
              ].join(" ")}
            >
              {w.text}
            </button>
          ))}
          {words.length === 0 && (
            <span className="text-xs text-muted py-1">Нет слов</span>
          )}
        </div>

        {selected.size > 0 ? (
          <p className="text-xs text-red-400">
            {selected.size} слов будет вырезано из клипа
          </p>
        ) : (
          <p className="text-xs text-muted">
            Нажми на слово чтобы отметить его. Можно выбрать несколько подряд.
          </p>
        )}

        <button
          disabled={busy || selected.size === 0}
          onClick={handleTrim}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-red-600/80 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-30"
        >
          {phase === "saving" ? (
            <><Loader2 className="size-4 animate-spin" /> Сохраняю…</>
          ) : (
            <><Scissors className="size-4" /> Вырезать {selected.size > 0 ? `(${selected.size} слов)` : ""}</>
          )}
        </button>
      </div>

      {/* ── STEP 2: EXTEND ── */}
      <div className="px-4 py-3 space-y-2">
        <p className="text-xs font-semibold text-muted uppercase tracking-wider">
          2 · Продлить конец клипа
        </p>
        <div className="flex gap-2">
          {[3, 5, 10, 15].map((s) => (
            <button
              key={s}
              disabled={busy}
              onClick={() => handleExtend(s)}
              className="flex-1 rounded-xl border border-line bg-surface py-2 text-xs font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-30"
            >
              +{s}s
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            value={extendSec}
            onChange={(e) => setExtendSec(e.target.value)}
            disabled={busy}
            min="0.5"
            step="0.5"
            className="w-20 rounded-xl border border-line bg-surface px-3 py-2 text-xs text-ink disabled:opacity-30 focus:outline-none focus:ring-1 focus:ring-accent/50"
          />
          <span className="text-xs text-muted">секунд</span>
          <button
            disabled={busy}
            onClick={() => handleExtend(parseFloat(extendSec) || 5)}
            className="flex-1 rounded-xl border border-line bg-surface py-2 text-xs font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-30"
          >
            Применить
          </button>
        </div>
      </div>

      {/* ── STEP 3: RE-RENDER ── */}
      <div className="px-4 py-3 space-y-2">
        <p className="text-xs font-semibold text-muted uppercase tracking-wider">
          3 · Рендер с правками
        </p>

        {phase === "done" ? (
          <div className="flex items-center gap-2 rounded-xl bg-green-900/30 px-4 py-3 text-sm text-green-400">
            <CheckCircle className="size-5 shrink-0" />
            <span>Готово — видео обновилось сверху</span>
          </div>
        ) : phase === "rendering" ? (
          <div className="rounded-xl border border-accent/20 bg-accent/5 px-4 py-3">
            <div className="flex items-center gap-2 text-sm text-accent">
              <Loader2 className="size-4 animate-spin" />
              <span>Рендеринг… {renderElapsed}s</span>
            </div>
            <p className="mt-1 text-xs text-muted">Обычно 10–30 секунд. Видео появится автоматически.</p>
          </div>
        ) : (
          <>
            <p className="text-xs text-muted">
              Нажми — клип перерендерится с твоими вырезками. Видео сверху обновится автоматически.
            </p>
            <button
              disabled={busy}
              onClick={handleRender}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-2 disabled:opacity-30"
            >
              <Film className="size-4" />
              Рендерить клип
            </button>
          </>
        )}
      </div>

    </div>
  );
}
