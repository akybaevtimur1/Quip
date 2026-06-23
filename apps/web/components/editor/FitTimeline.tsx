"use client";

import { Loader2 } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { mmss } from "@/lib/format";
import type { CropOverride, SourceInterval } from "@/lib/types";

// ────────────────────────────────────────────────────────────────────────────
// FitTimeline — полоса шотов под превью для ПОШОТОВОГО кадрирования.
// Видео склеено из шотов (смен ракурса камеры). Для каждого шота AI решает,
// как уместить его в 9:16: Wide (весь кадр) / Tight (кроп на спикере) / Split.
// Тут можно ПЕРЕОПРЕДЕЛИТЬ кадр на выбранных шотах.
//
// Три честных состояния (variant):
//   • "ai"      — реальные границы шотов от CV (PySceneDetect): блок = реальная склейка.
//   • "manual"  — AI-план недоступен → равные слоты как РУЧНАЯ разметка (честно подписано,
//                 НЕ маскируется под реальные шоты — это была главная путаница).
//   • loading   — план шотов ещё считается → скелетон, а не фейковые «шоты».
//
// Драг по полосе → выбор СМЕЖНОГО диапазона шотов (снап к границам = целый шот).
// [Wide / Tight / Auto] применяет режим к диапазону (Auto = убрать override).
// ────────────────────────────────────────────────────────────────────────────

/** Регион reframe-плана в КЛИП-времени (совпадает с RawRegion в ClipEditorScreen). */
export interface FitRegion {
  t0: number;
  t1: number;
  mode: string;
}

export type ForceMode = "fit" | "fill" | "auto";

export interface FitTimelineProps {
  /** Регионы reframe-плана (клип-время t0/t1/mode). null/пусто → ничего не рисуем. */
  regions: FitRegion[] | null;
  /** Интервалы клипа (CLIP-порядок) для маппинга клип-время → source-время. */
  intervals: SourceInterval[];
  /** Текущие ручные override'ы — подсветить регионы с форсированным кадром. */
  overrides?: CropOverride[];
  /** Текущее время видео (source-сек) → плейхед + подсветка активного шота. */
  nowSec?: number;
  /** Идёт сохранение/рендер: взаимодействие заблокировано. */
  busy?: boolean;
  /** "ai" = реальные шоты от CV; "manual" = равные слоты (AI-план недоступен). */
  variant?: "ai" | "manual";
  /** План шотов ещё грузится → скелетон вместо полосы. */
  loading?: boolean;
  /** Применить режим к source-диапазону выделенных регионов. mode:"auto" чистит override. */
  onApplyRange: (sourceStart: number, sourceEnd: number, mode: ForceMode) => void;
}

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

/**
 * Маппинг точки КЛИП-времени → source-время (обратный к backend regions_to_clip_time).
 * Клип-время = конкатенация intervals: интервал i занимает [offset, offset+dur). Точка
 * clipT лежит в интервале, чей кумулятивный offset её содержит → source = source_start +
 * (clipT - offset). Одно-интервальный кейс = source = intervals[0].source_start + clipT. PURE.
 */
export function clipTimeToSource(clipT: number, intervals: SourceInterval[]): number {
  if (intervals.length === 0) return clipT;
  let offset = 0;
  for (let i = 0; i < intervals.length; i++) {
    const iv = intervals[i];
    const dur = iv.source_end - iv.source_start;
    // A point ON an inner seam (clipT === offset+dur, i.e. the join between interval i and i+1)
    // belongs to the NEXT interval's START, not this one's end — use `<` for inner intervals so a
    // region/shot starting exactly on a seam maps correctly. The LAST interval keeps `<=` to catch
    // the tail (clipT == total clip length). (Single-interval clips are unaffected.)
    const isLast = i === intervals.length - 1;
    if (isLast ? clipT <= offset + dur : clipT < offset + dur) {
      return iv.source_start + (clipT - offset);
    }
    offset += dur;
  }
  // за пределами клипа → конец последнего интервала
  return intervals[intervals.length - 1].source_end;
}

/** Активен ли ручной override на регионе [t0,t1] клип-времени (по пересечению source-окна). */
function regionOverride(
  region: FitRegion,
  intervals: SourceInterval[],
  overrides: CropOverride[],
): CropOverride | null {
  if (overrides.length === 0) return null;
  const s0 = clipTimeToSource(region.t0, intervals);
  const s1 = clipTimeToSource(region.t1, intervals);
  // последний выигрывает (как в ClipEditorScreen.frame) — берём с конца
  for (let i = overrides.length - 1; i >= 0; i--) {
    const ov = overrides[i];
    if (ov.source_start < s1 && ov.source_end > s0) return ov;
  }
  return null;
}

/** Лейбл режима кадра в терминах юзера. */
function modeLabel(mode: string): string {
  return mode === "fit" ? "Wide" : mode === "fill" ? "Tight" : mode === "split" ? "Split" : mode;
}

const MODE_TINT: Record<string, string> = {
  fill: "bg-quote/30", // tight crop (синий)
  fit: "bg-thought/30", // wide / horizontal (зелёный)
  split: "bg-peak/30", // split (фиолетовый)
};

const FORCE_OPTIONS: { value: ForceMode; label: string; hint: string }[] = [
  { value: "fit", label: "Wide", hint: "show the whole frame" },
  { value: "fill", label: "Tight", hint: "crop in on the speaker" },
  { value: "auto", label: "Auto", hint: "let AI decide" },
];

export function FitTimeline({
  regions,
  intervals,
  overrides = [],
  nowSec,
  busy = false,
  variant = "ai",
  loading = false,
  onApplyRange,
}: FitTimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  // выделенный диапазон регионов [from, to] (индексы, оба включительно) или null
  const [sel, setSel] = useState<{ from: number; to: number } | null>(null);
  const [mode, setMode] = useState<ForceMode>("fit");
  const dragRef = useRef<{ anchor: number } | null>(null);

  // суммарная клип-длительность = конец последнего региона (= длина клипа в reframe-плане)
  const clipDur = useMemo(() => {
    if (!regions || regions.length === 0) return 0;
    return Math.max(0.001, regions[regions.length - 1].t1 - regions[0].t0);
  }, [regions]);

  const t0 = regions && regions.length > 0 ? regions[0].t0 : 0;

  // индекс региона под clientX (снап к границам регионов = целый шот)
  const regionAtX = useCallback(
    (clientX: number): number | null => {
      const el = trackRef.current;
      if (!el || !regions || regions.length === 0) return null;
      const r = el.getBoundingClientRect();
      const clipT = t0 + clamp((clientX - r.left) / r.width, 0, 1) * clipDur;
      for (let i = 0; i < regions.length; i++) {
        if (clipT >= regions[i].t0 && clipT < regions[i].t1) return i;
      }
      return regions.length - 1; // хвост → последний регион
    },
    [regions, t0, clipDur],
  );

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (busy) return;
      const idx = regionAtX(e.clientX);
      if (idx === null) return;
      e.preventDefault();
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      dragRef.current = { anchor: idx };
      setSel({ from: idx, to: idx });
    },
    [busy, regionAtX],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const idx = regionAtX(e.clientX);
      if (idx === null) return;
      setSel({ from: Math.min(drag.anchor, idx), to: Math.max(drag.anchor, idx) });
    },
    [regionAtX],
  );

  const endDrag = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current) return;
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* capture мог не стоять */
    }
    dragRef.current = null;
  }, []);

  const apply = useCallback(() => {
    if (!sel || !regions || regions.length === 0 || busy) return;
    const lo = regions[sel.from];
    const hi = regions[sel.to];
    const sourceStart = clipTimeToSource(lo.t0, intervals);
    const sourceEnd = clipTimeToSource(hi.t1, intervals);
    if (sourceEnd <= sourceStart) return;
    onApplyRange(sourceStart, sourceEnd, mode);
    setSel(null);
  }, [sel, regions, intervals, mode, busy, onApplyRange]);

  const unit = variant === "manual" ? "part" : "shot";

  // ── loading: план шотов считается → скелетон (НЕ фейковые «шоты») ──
  if (loading) {
    return (
      <div className="mt-2 space-y-1.5">
        <div className="flex h-14 w-full gap-px overflow-hidden rounded-lg border border-line bg-surface-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-full flex-1 animate-pulse bg-surface-3/60" />
          ))}
        </div>
        <p className="flex items-center justify-center gap-1.5 text-[11px] text-muted">
          <Loader2 className="size-3 animate-spin" />
          Detecting the shots in this clip…
        </p>
      </div>
    );
  }

  // ── пусто/нет плана → честная подсказка (не ломаемся) ──
  if (!regions || regions.length === 0) {
    return (
      <div className="mt-2 rounded-lg border border-dashed border-line bg-surface-2 px-3 py-2 text-center text-[11px] text-muted">
        Shot plan unavailable for this clip — framing follows the AI default.
      </div>
    );
  }

  const playheadClipT =
    nowSec !== undefined && intervals.length > 0
      ? clipTimeFromSource(nowSec, intervals)
      : null;
  const playheadFrac =
    playheadClipT !== null ? clamp((playheadClipT - t0) / clipDur, 0, 1) : null;
  const activeIdx =
    playheadClipT !== null
      ? regions.findIndex((r) => playheadClipT >= r.t0 && playheadClipT < r.t1)
      : -1;

  const selLabel = sel
    ? sel.from === sel.to
      ? `${unit === "shot" ? "Shot" : "Part"} ${sel.from + 1} selected`
      : `${unit === "shot" ? "Shots" : "Parts"} ${sel.from + 1}–${sel.to + 1} selected`
    : `Drag across the bar to pick ${unit}s`;

  return (
    <div className="mt-2 select-none">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold text-ink">
          {regions.length} {unit}
          {regions.length === 1 ? "" : "s"}
          {variant === "manual" && (
            <span className="ml-1.5 font-normal text-muted">· manual (no AI shot plan)</span>
          )}
        </span>
        <span className="text-[10px] text-muted">{selLabel}</span>
      </div>

      <div
        ref={trackRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className={`relative flex h-14 w-full gap-px overflow-hidden rounded-lg border border-line bg-surface-2 touch-none ${
          busy ? "cursor-wait opacity-60" : "cursor-pointer"
        }`}
      >
        {regions.map((reg, i) => {
          const widthFrac = (reg.t1 - reg.t0) / clipDur;
          const ov = regionOverride(reg, intervals, overrides);
          const selected = sel !== null && i >= sel.from && i <= sel.to;
          const isActive = i === activeIdx;
          // эффективный режим: override приоритетнее AI-плана
          const effMode = ov ? ov.mode : reg.mode;
          const tint = MODE_TINT[effMode] ?? "bg-surface-3";
          const widthPct = Math.max(widthFrac * 100, 1.5);
          const wide = widthPct > 7; // влезает ли подпись внутрь блока
          return (
            <div
              key={i}
              className={`relative flex h-full flex-col items-center justify-center overflow-hidden ${tint} transition`}
              style={{ width: `${widthPct}%` }}
              title={`${unit === "shot" ? "Shot" : "Part"} ${i + 1} · ${
                ov ? `${modeLabel(ov.mode)} (forced)` : modeLabel(reg.mode)
              } · ${mmss(reg.t0)}–${mmss(reg.t1)}`}
            >
              {wide && (
                <>
                  <span className="pointer-events-none text-[10px] font-bold leading-none text-ink/80">
                    {i + 1}
                  </span>
                  <span className="pointer-events-none mt-0.5 text-[8px] font-semibold uppercase leading-none tracking-wide text-ink/55">
                    {modeLabel(effMode)}
                  </span>
                </>
              )}
              {ov && <span className="absolute inset-x-0 top-0 h-1 bg-accent" aria-hidden />}
              {isActive && !selected && (
                <span
                  className="pointer-events-none absolute inset-0 ring-2 ring-inset ring-white/70"
                  aria-hidden
                />
              )}
              {selected && (
                <span
                  className="pointer-events-none absolute inset-0 bg-accent/25 ring-2 ring-inset ring-accent"
                  aria-hidden
                />
              )}
            </div>
          );
        })}

        {playheadFrac !== null && (
          <div
            className="pointer-events-none absolute top-0 bottom-0 z-10 w-0.5 bg-white shadow-[0_0_4px_rgba(0,0,0,.6)]"
            style={{ left: `${playheadFrac * 100}%` }}
            aria-hidden
          />
        )}
      </div>

      {/* действие: выбрать режим → применить к выделенным шотам */}
      <div className="mt-2 flex items-center gap-2">
        <div
          className="flex gap-0.5 rounded-md border border-line bg-surface p-0.5"
          role="radiogroup"
          aria-label="Forced framing mode"
        >
          {FORCE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={mode === opt.value}
              disabled={busy}
              title={opt.hint}
              onClick={() => setMode(opt.value)}
              className={`rounded px-2.5 py-1 text-[11px] font-semibold transition disabled:opacity-40 ${
                mode === opt.value ? "bg-surface-3 text-accent" : "text-muted hover:text-ink"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled={busy || !sel}
          onClick={apply}
          aria-label="Apply framing to selected shots"
          className="ml-auto rounded-md border border-accent/60 bg-accent/10 px-3 py-1 text-[11px] font-semibold text-accent transition enabled:hover:bg-accent/20 disabled:border-line disabled:bg-transparent disabled:text-muted disabled:opacity-50"
        >
          {sel
            ? `Apply ${FORCE_OPTIONS.find((o) => o.value === mode)?.label ?? ""} to ${
                sel.from === sel.to ? "1" : sel.to - sel.from + 1
              } ${unit}${sel && sel.from === sel.to ? "" : "s"}`
            : `Select ${unit}s first`}
        </button>
      </div>

      {/* легенда */}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-muted">
        <span className="inline-flex items-center gap-1">
          <span className="size-2 rounded-sm bg-thought/40" /> Wide (full frame)
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="size-2 rounded-sm bg-quote/40" /> Tight (crop)
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="size-2 rounded-sm bg-peak/40" /> Split
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-0.5 w-3 bg-accent" /> Forced
        </span>
      </div>
    </div>
  );
}

/**
 * Маппинг source-время → КЛИП-время (для плейхеда). Обратный к clipTimeToSource:
 * source попадает в интервал [source_start, source_end) → clipT = offset + (source - source_start).
 * За пределами клипа клампится. PURE.
 */
function clipTimeFromSource(sourceT: number, intervals: SourceInterval[]): number {
  let offset = 0;
  for (const iv of intervals) {
    const dur = iv.source_end - iv.source_start;
    if (sourceT < iv.source_end) {
      return offset + Math.max(0, sourceT - iv.source_start);
    }
    offset += dur;
  }
  return offset; // после конца → суммарная длина
}

export default FitTimeline;
