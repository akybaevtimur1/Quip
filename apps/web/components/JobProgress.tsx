import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Meter } from "@/components/ui/Meter";
import { Numeral } from "@/components/ui/Numeral";
import { Skeleton } from "@/components/ui/Skeleton";
import { mmss } from "@/lib/format";
import type { JobStatus, SourceKind } from "@/lib/types";

const ORDER: JobStatus[] = ["queued", "downloading", "transcribing", "selecting", "rendering", "done"];
// Pipeline steps in order. Labels come from `jobProgress.step.*`; "Preparing" (not
// "Downloading") because an uploaded file has nothing to download — "Downloading" right
// after the upload screen read like a second download.
const STEP_KEYS = ["downloading", "transcribing", "selecting", "rendering"] as const;
// Stages that carry a localized one-line hint under `jobProgress.hint.*`.
const HINT_KEYS = ["queued", "downloading", "transcribing", "selecting", "rendering"] as const;

export function JobProgress({
  status,
  elapsed,
  progress = null,
  cancellable = false,
  onStop,
  sourceMinutes = null,
  transcriptWords = null,
  momentsFound = null,
  requestedClips = 3,
  sourceKind = null,
}: {
  status: JobStatus;
  elapsed: number;
  // Серверный прогресс 0–100 (от воркера) → настоящий прогресс-бар, не только степпер.
  progress?: number | null;
  // Stop-кнопка: показываем ТОЛЬКО когда воркер сообщил cancellable (FREE-фаза до транскрипции).
  cancellable?: boolean;
  onStop?: () => void;
  // Live-narration счётчики (наполняются по мере стадий) → окно 0–60% (до карточек) не мёртвое.
  sourceMinutes?: number | null;
  transcriptWords?: number | null;
  momentsFound?: number | null;
  // How many clips the user asked for — drives the reserved skeleton count.
  requestedClips?: number;
  // Source of the job — drives YouTube-specific "fetching" copy (the import can still fail).
  sourceKind?: SourceKind | null;
}) {
  const t = useTranslations("jobProgress");
  const stageHint = (HINT_KEYS as readonly string[]).includes(status)
    ? t(`hint.${status}`)
    : t("working");
  // While "queued" (cur=0) the first real step ("Downloading", index 1) reads as active,
  // so the stepper never looks dead between submit and the first status change.
  const cur = Math.max(ORDER.indexOf(status), 1);
  // YouTube import (download_youtube) is the one BEST-EFFORT stage that can still fail mid-run
  // (the DC-IP bot-gate). Surface it explicitly so the user watches it and isn't surprised by a
  // late failure — vs an uploaded file, where "downloading" is just local prep that won't fail.
  const isYoutubeFetch = status === "downloading" && sourceKind === "youtube";
  // Local disable between click and the next poll (which flips cancellable→false) so a
  // double-click can't fire two cancels.
  const [stopping, setStopping] = useState(false);

  // Прогресс-бар: серверный progress, с полом по стадии чтобы бар никогда не выглядел
  // застрявшим на 0, и не дёргался назад (берём максимум из server и стадийного пола).
  const stageFloor = [0, 8, 35, 60, 80, 100][Math.min(cur, 5)] ?? 8;
  const pct = Math.min(99, Math.max(progress ?? 0, stageFloor));

  // Reserve a realistic number of clip slots (cap so the skeleton grid stays tidy).
  const skeletonCount = Math.min(6, Math.max(2, requestedClips));

  // Live telemetry — only the readings the worker has reported so far.
  const telemetry = [
    {
      label: t("telemetry.source"),
      value: sourceMinutes != null ? t("count.minutes", { value: sourceMinutes }) : "—",
    },
    {
      label: t("telemetry.words"),
      value: transcriptWords != null ? transcriptWords.toLocaleString() : "—",
    },
    { label: t("telemetry.moments"), value: momentsFound != null ? String(momentsFound) : "—" },
  ];

  return (
    <div className="mx-auto w-full max-w-3xl">
      {/* header: stage readout + elapsed + stop */}
      <div className="flex items-end justify-between gap-4 border-b border-line pb-4">
        <div>
          <Eyebrow tone="accent">{t("processing")}</Eyebrow>
          <h2 className="mt-1.5 font-display text-h3 text-ink">
            {isYoutubeFetch ? t("fetchingYoutube") : stageHint}
          </h2>
        </div>
        <div className="flex items-end gap-4">
          <div className="text-right" aria-live="polite">
            <Eyebrow tone="faint" className="block">
              {t("elapsed")}
            </Eyebrow>
            <Numeral className="mt-1 block text-base text-muted">{mmss(elapsed)}</Numeral>
          </div>
          {cancellable && onStop && (
            <button
              type="button"
              disabled={stopping}
              onClick={() => {
                setStopping(true);
                onStop();
              }}
              className="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-sm text-muted transition hover:border-line-strong hover:text-ink disabled:opacity-50"
            >
              <X className="size-4" />
              {stopping ? t("stopping") : t("stop")}
            </button>
          )}
        </div>
      </div>

      {/* overall progress meter + telemetry readouts */}
      <div className="mt-5 flex items-center gap-3">
        <Meter value={pct / 100} tone="accent" aria-label="Overall progress" className="flex-1" />
        <Numeral className="shrink-0 text-xs text-muted">{Math.round(pct)}%</Numeral>
      </div>
      <div className="mt-5 grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-line bg-line">
        {telemetry.map((t) => (
          <div key={t.label} className="bg-surface px-4 py-3">
            <Eyebrow tone="faint" className="block">
              {t.label}
            </Eyebrow>
            <Numeral className="mt-1.5 block text-base text-ink">{t.value}</Numeral>
          </div>
        ))}
      </div>

      {isYoutubeFetch && (
        <p className="mt-5 rounded-lg border border-line bg-surface px-4 py-3 text-xs leading-relaxed text-muted">
          {t("youtubeNote")}
        </p>
      )}

      {/* timeline spine: hairline rail + dot nodes (coral active / thought done / hollow pending) */}
      <ol className="relative mt-7 ml-1.5">
        {/* the vertical rail */}
        <span className="absolute left-[5px] top-2 bottom-2 w-px bg-line" aria-hidden />
        {STEP_KEYS.map((key) => {
          const i = ORDER.indexOf(key);
          const done = cur > i;
          const active = cur === i;
          // Live count for this stage (shown once the worker reports it).
          const count =
            key === "downloading" && sourceMinutes != null
              ? t("count.minutes", { value: sourceMinutes })
              : key === "transcribing" && transcriptWords != null
                ? t("count.words", { value: transcriptWords.toLocaleString() })
                : key === "selecting" && momentsFound != null
                  ? t("count.found", { value: momentsFound })
                  : null;
          return (
            <li key={key} className="relative flex items-center gap-3.5 py-2.5 pl-6">
              <span
                className={`absolute left-0 z-10 size-[11px] rounded-pill border-2 transition ${
                  active
                    ? "border-accent bg-accent motion-safe:animate-pulse"
                    : done
                      ? "border-thought bg-thought"
                      : "border-line-strong bg-bg"
                }`}
                aria-hidden
              />
              <span
                className={`text-sm font-medium ${active || done ? "text-ink" : "text-muted"}`}
              >
                {key === "downloading" && sourceKind === "youtube"
                  ? t("fetchingYoutube")
                  : t(`step.${key}`)}
              </span>
              {count && <Numeral className="text-xs text-muted">· {count}</Numeral>}
            </li>
          );
        })}
      </ol>

      <p className="mt-5 text-xs leading-relaxed text-faint">{t("keepRunning")}</p>

      {/* skeletons of the clips to come — reserve the grid space so the handoff doesn't jump */}
      <div className="mt-7 grid grid-cols-2 gap-4 sm:grid-cols-3">
        {Array.from({ length: skeletonCount }).map((_, i) => (
          <div key={i}>
            <Skeleton className="aspect-[9/16] rounded-lg" />
            <Skeleton className="mt-2 h-3 w-2/3" />
          </div>
        ))}
      </div>
    </div>
  );
}
