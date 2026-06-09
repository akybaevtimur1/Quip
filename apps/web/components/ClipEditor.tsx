"use client";

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

type Phase = "loading" | "ready" | "saving" | "rendering" | "error";

export default function ClipEditor({ jobId, clipId, onRenderDone }: ClipEditorProps) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<ClipEdit | null>(null);
  const [words, setWords] = useState<Word[]>([]);
  // parallel array: globalIndices[i] = transcript word index for words[i]
  const [globalIndices, setGlobalIndices] = useState<number[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [extendSec, setExtendSec] = useState<string>("5");
  // bumping this triggers a re-load
  const [loadKey, setLoadKey] = useState(0);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  // load on mount and whenever loadKey changes
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
    return () => {
      cancelled = true;
      stopPoll();
    };
  }, [jobId, clipId, loadKey, stopPoll]);

  const toggleWord = (pos: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(pos)) next.delete(pos);
      else next.add(pos);
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
      setError(String(e));
      setPhase("ready");
    }
  };

  const handleExtend = async () => {
    if (!edit) return;
    const secs = parseFloat(extendSec);
    if (isNaN(secs) || secs <= 0) return;
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
      setError(String(e));
      setPhase("ready");
    }
  };

  const handleRender = async () => {
    if (!edit) return;
    setPhase("rendering");
    setError(null);
    stopPoll();
    try {
      await startRenderClip(jobId, clipId);
    } catch (e) {
      setError(String(e));
      setPhase("ready");
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const st = await getRenderStatus(jobId, clipId);
        if (st.status === "done" && st.video_url) {
          stopPoll();
          setPhase("ready");
          onRenderDone(resolveUrl(st.video_url));
        } else if (st.status === "failed") {
          stopPoll();
          setError(st.error ?? "Render failed");
          setPhase("ready");
        }
      } catch {
        // keep polling
      }
    }, 2000);
  };

  if (phase === "loading") {
    return (
      <div className="p-4 text-center text-sm text-muted animate-pulse">Loading editor…</div>
    );
  }

  if (phase === "error" && !edit) {
    return (
      <div className="p-4 text-sm text-red-400">
        {error}
        <button onClick={() => setLoadKey((k) => k + 1)} className="ml-2 underline">
          Retry
        </button>
      </div>
    );
  }

  const totalSec = edit
    ? edit.source_intervals.reduce((s, iv) => s + (iv.source_end - iv.source_start), 0)
    : 0;

  const busy = phase === "saving" || phase === "rendering";

  return (
    <div className="border-t border-line bg-surface-2 p-3 space-y-3 text-sm rounded-b-xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted">
          {edit?.source_intervals.length ?? 0} interval
          {(edit?.source_intervals.length ?? 0) !== 1 ? "s" : ""} · {totalSec.toFixed(1)}s
        </span>
        {phase === "rendering" && (
          <span className="text-xs text-accent animate-pulse">Rendering…</span>
        )}
        {phase === "saving" && <span className="text-xs text-muted">Saving…</span>}
      </div>

      {error && (
        <div className="rounded bg-red-900/30 px-2 py-1 text-xs text-red-400">{error}</div>
      )}

      {/* Words */}
      <div>
        <div className="mb-1.5 text-xs text-muted">
          Click words to select for trim
          {selected.size > 0 && (
            <span className="ml-1 text-accent">({selected.size} selected)</span>
          )}
        </div>
        <div className="flex flex-wrap gap-1 max-h-36 overflow-y-auto rounded-lg border border-line bg-surface p-2">
          {words.map((w, i) => (
            <button
              key={i}
              disabled={busy}
              onClick={() => toggleWord(i)}
              className={[
                "rounded px-1.5 py-0.5 text-xs transition-colors",
                selected.has(i)
                  ? "bg-accent text-white"
                  : "bg-surface-2 text-ink hover:opacity-80",
              ].join(" ")}
            >
              {w.text}
            </button>
          ))}
          {words.length === 0 && <span className="text-xs text-muted">No words loaded</span>}
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-2 items-center">
        <button
          disabled={busy || selected.size === 0}
          onClick={handleTrim}
          className="rounded-lg bg-red-700/80 px-3 py-1 text-xs text-white disabled:opacity-40 hover:bg-red-600 transition-colors"
        >
          Trim{selected.size > 0 ? ` (${selected.size})` : ""}
        </button>

        <div className="flex items-center gap-1">
          <span className="text-xs text-muted">+end</span>
          <input
            type="number"
            value={extendSec}
            onChange={(e) => setExtendSec(e.target.value)}
            disabled={busy}
            min="0.5"
            step="0.5"
            className="w-14 rounded border border-line bg-surface px-1.5 py-0.5 text-xs text-ink disabled:opacity-40 focus:outline-none focus:ring-1 focus:ring-accent/50"
          />
          <span className="text-xs text-muted">s</span>
          <button
            disabled={busy}
            onClick={handleExtend}
            className="rounded-lg border border-line bg-surface px-2 py-1 text-xs text-ink disabled:opacity-40 hover:border-accent/50 hover:text-accent transition-colors"
          >
            Apply
          </button>
        </div>

        <button
          disabled={busy}
          onClick={handleRender}
          className="ml-auto rounded-lg bg-accent px-3 py-1 text-xs text-white font-semibold disabled:opacity-40 hover:bg-accent-2 transition-colors"
        >
          {phase === "rendering" ? "Rendering…" : "Re-render"}
        </button>
      </div>
    </div>
  );
}
