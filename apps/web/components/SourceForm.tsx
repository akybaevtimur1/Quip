"use client";

import { Link2, Minus, Plus, Scissors, Upload, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import { Numeral } from "@/components/ui/Numeral";
import { cn } from "@/lib/cn";
import { isAcceptedVideoFile } from "@/lib/videoFile";

const MIN_CLIPS = 1;
const MAX_CLIPS = 30; // продуктовый потолок (Auto = «сколько найдётся, до 30»)
const DEFAULT_CLIPS = 8;
// Quip is for long-form (podcasts, talks). Uploads >100 MB go via R2 multipart (parallel,
// resumable parts) so the old 5 GB single-PUT ceiling is gone — the REAL limit is length
// (3 h, worker-side billing.MAX_VIDEO_MINUTES). This MB number is just a sane guard against
// absurd uploads (a 3 h 1080p source is ~2–6 GB); bump it freely.
const MAX_UPLOAD_MB = 10000;
const MAX_UPLOAD_LABEL = "10 GB";

// YouTube-link import is DISABLED for now. Server-side download bot-gates on Modal's DC-IP often
// enough that users would just get an error in the face, so we hide the entry point until it's
// solved properly (residential proxy / founder-IP tunnel). The WHOLE path behind this — the form
// handler, createJob(youtube), the worker download + multi-cookie fallback — is intact; flip this
// to true to restore the "or paste a link" field. See docs/JOURNAL.md 2026-06-25.
const YOUTUBE_LINK_ENABLED: boolean = false;

/** Client-side YouTube-URL sanity check (server still validates + downloads best-effort).
 *  Loose by design: matches youtube.com / youtu.be and asks for a plausible length. */
function isLikelyYoutubeUrl(url: string): boolean {
  return /youtu\.?be/i.test(url) && url.trim().length > 12;
}

export function SourceForm({
  onSubmit,
  onSubmitFile,
  busy,
}: {
  // onSubmit = YouTube-link path (best-effort import). Optional for back-compat: callers that
  // don't pass it simply don't offer the link field. Upload is the primary affordance.
  onSubmit?: (url: string, maxClips: number) => void;
  onSubmitFile: (file: File, maxClips: number, language: string | null) => void;
  busy: boolean;
}) {
  const t = useTranslations("sourceForm");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  // YouTube link — a SECONDARY option under the drop-zone (best-effort; may fall back to upload).
  const [url, setUrl] = useState("");
  // auto = «сколько найдётся, максимум 30» (без жёсткого выбора числа); custom = ровно N клипов.
  const [auto, setAuto] = useState(true);
  const [count, setCount] = useState(DEFAULT_CLIPS);
  const [dragging, setDragging] = useState(false);
  const [kazakh, setKazakh] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const urlValid = isLikelyYoutubeUrl(url);
  // A file always wins; otherwise a valid YouTube link (only if the link path is wired in).
  const canSubmit = !busy && (file != null || (onSubmit != null && urlValid));
  const clamp = (n: number) => Math.max(MIN_CLIPS, Math.min(MAX_CLIPS, n));
  // Auto → шлём потолок (30): воркер вернёт ДО стольких сильных моментов, сколько найдёт.
  const clipsRequested = auto ? MAX_CLIPS : count;

  function pickFile(f: File | null) {
    setFileError(null);
    if (!f) {
      setFile(null);
      return;
    }
    // Accept by MIME OR (empty MIME + video extension): browsers report "" for some valid
    // containers (.mkv/.mov/.webm/.avi), and the old MIME-only check silently rejected them.
    if (!isAcceptedVideoFile(f.name, f.type)) {
      setFileError(t("notVideo"));
      return;
    }
    if (f.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setFileError(t("tooLarge", { label: MAX_UPLOAD_LABEL }));
      return;
    }
    setFile(f);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    // A picked file is the primary path; a YouTube link is the best-effort secondary path.
    if (file) {
      onSubmitFile(file, clipsRequested, kazakh ? "kk" : null);
    } else if (onSubmit && urlValid) {
      onSubmit(url.trim(), clipsRequested);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      {/* Intake: a measured instrument frame (corner ticks + a 9:16 target marker), not a
          limp centered dashed box. Or the selected-file plate once a file is chosen. */}
      {file == null ? (
        <div
          onClick={() => !busy && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            if (!busy) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (!busy) pickFile(e.dataTransfer.files?.[0] ?? null);
          }}
          role="button"
          tabIndex={0}
          aria-label={t("uploadAria")}
          className={cn(
            "group relative cursor-pointer overflow-hidden rounded-lg border bg-surface px-5 py-7 transition duration-200 ease-snappy",
            dragging ? "border-accent bg-surface-2" : "border-line hover:border-line-strong",
            busy && "pointer-events-none opacity-50",
          )}
        >
          {/* corner ticks — the measured-frame signature */}
          {(["left-2.5 top-2.5 border-l border-t", "right-2.5 top-2.5 border-r border-t", "left-2.5 bottom-2.5 border-l border-b", "right-2.5 bottom-2.5 border-r border-b"] as const).map(
            (pos) => (
              <span
                key={pos}
                aria-hidden
                className={cn(
                  "pointer-events-none absolute size-3 transition-colors",
                  pos,
                  dragging ? "border-accent" : "border-line-strong",
                )}
              />
            ),
          )}
          <div className="flex items-center gap-4">
            {/* 9:16 target marker */}
            <span
              aria-hidden
              className={cn(
                "grid h-14 w-[31.5px] shrink-0 place-items-center rounded-sm border transition-colors",
                dragging ? "border-accent bg-accent-tint" : "border-line-strong bg-surface-2",
              )}
            >
              {/* the 9:16 target marker is structure, not a CTA — keep coral scarce for the
                  "choose a file" affordance + the Make clips button. */}
              <Upload className={cn("size-4 transition-colors", dragging ? "text-accent" : "text-muted")} />
            </span>
            <div className="min-w-0">
              <Eyebrow tone="faint">{t("intake")}</Eyebrow>
              <p className="mt-1.5 text-sm text-ink">
                {dragging
                  ? t("dropToLoad")
                  : t.rich("dropOrChoose", {
                      choose: (chunks) => <span className="font-medium text-accent">{chunks}</span>,
                    })}
              </p>
              <p className="mt-1 font-mono text-eyebrow uppercase tabular-nums text-faint">
                {t("formats", { label: MAX_UPLOAD_LABEL })}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-line bg-surface px-4 py-3.5">
          <span className="flex min-w-0 items-center gap-2.5 truncate text-sm text-ink">
            <Upload className="size-4 shrink-0 text-accent" />
            <span className="truncate font-medium">{file.name}</span>
          </span>
          <IconButton
            onClick={() => pickFile(null)}
            disabled={busy}
            aria-label={t("removeFile")}
            size="sm"
            className="size-10 sm:size-7"
          >
            <X className="size-4" />
          </IconButton>
        </div>
      )}
      <input
        ref={inputRef}
        type="file"
        // video/* PLUS explicit extensions: some OS dialogs grey out valid containers (.mkv/.mov/
        // .webm/.avi) under a bare `video/*` because they report no MIME for them.
        accept="video/*,.mp4,.m4v,.mov,.qt,.webm,.mkv,.avi,.wmv,.flv,.mpg,.mpeg,.ts,.mts,.m2ts,.3gp,.3g2,.ogv"
        hidden
        onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
      />
      {fileError ? <p className="mt-2 text-sm text-bad">{fileError}</p> : null}

      {/* Secondary option: a YouTube link (best-effort import — may not work for every video, in
          which case we ask you to upload the file). Hidden once a file is picked (file wins).
          Only rendered when the link path is wired (onSubmit) so upload-only callers stay clean. */}
      {YOUTUBE_LINK_ENABLED && onSubmit && file == null ? (
        <div className="mt-4">
          <div className="flex items-center gap-3">
            <span className="h-px flex-1 bg-line" />
            <span className="font-mono text-eyebrow uppercase tracking-wide text-faint">
              {t("orPasteLink")}
            </span>
            <span className="h-px flex-1 bg-line" />
          </div>
          {/* The INPUT is the single bordered element (icon sits inside, absolute) so the global
              :focus-visible ring hugs that one border = one box. The old wrapper-label-with-border +
              ring-on-input gave a DOUBLE border (the global ring is unlayered → can't be killed by a
              layered utility). Mirrors components/ui/Input: border stays neutral, coral = the ring. */}
          <div className="relative mt-3">
            <Link2
              className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted"
              aria-hidden
            />
            <input
              type="text"
              inputMode="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={busy}
              aria-label={t("youtubeAria")}
              aria-invalid={url.length > 0 && !urlValid}
              placeholder={t("youtubePlaceholder")}
              className={cn(
                "h-11 w-full rounded-lg border bg-surface pl-10 pr-3.5 text-sm text-ink placeholder:text-faint transition-colors duration-200 ease-snappy",
                url.length > 0 && !urlValid ? "border-bad" : "border-line hover:border-line-strong",
                busy && "pointer-events-none opacity-50",
              )}
            />
          </div>
          {url.length > 0 && !urlValid ? (
            <p className="mt-2 text-sm text-bad">{t("youtubeInvalid")}</p>
          ) : (
            <p className="mt-2 text-xs leading-relaxed text-faint">{t("youtubeHint")}</p>
          )}
        </div>
      ) : null}

      {/* Both settings are compact, same weight — one grouped row (not two full-width stacked
          sections) reads as one settings cluster instead of a longer scanning list. */}
      <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2">
        <div>
          <Eyebrow tone="faint">{t("clipCount")}</Eyebrow>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            {/* Auto («сколько найдётся, до 30») vs Custom (ровно N). */}
            <div className="inline-flex rounded-md border border-line bg-surface p-0.5">
              {([true, false] as const).map((isAuto) => (
                <button
                  key={String(isAuto)}
                  type="button"
                  onClick={() => setAuto(isAuto)}
                  disabled={busy}
                  aria-pressed={auto === isAuto}
                  className={cn(
                    "rounded-sm px-3.5 py-1.5 text-sm font-medium transition disabled:opacity-50",
                    auto === isAuto
                      ? "bg-surface-3 text-ink shadow-[0_0_0_1px_var(--color-line-strong)]"
                      : "text-muted hover:text-ink",
                  )}
                >
                  {isAuto ? t("auto") : t("custom")}
                </button>
              ))}
            </div>
            {!auto && (
              <div className="inline-flex items-center gap-1 rounded-md border border-line bg-surface p-1">
                <IconButton
                  onClick={() => setCount((c) => clamp(c - 1))}
                  disabled={busy || count <= MIN_CLIPS}
                  aria-label={t("fewerClips")}
                  size="sm"
                  className="size-9 text-ink hover:text-ink sm:size-7"
                >
                  <Minus className="size-4" />
                </IconButton>
                <Numeral className="w-7 text-center text-base font-semibold text-ink">{count}</Numeral>
                <IconButton
                  onClick={() => setCount((c) => clamp(c + 1))}
                  disabled={busy || count >= MAX_CLIPS}
                  aria-label={t("moreClips")}
                  size="sm"
                  className="size-9 text-ink hover:text-ink sm:size-7"
                >
                  <Plus className="size-4" />
                </IconButton>
              </div>
            )}
            <span className="font-mono text-eyebrow uppercase tabular-nums text-faint">
              {auto ? t("autoHint", { max: MAX_CLIPS }) : t("customHint", { count })}
            </span>
          </div>
        </div>

        <div>
          <Eyebrow tone="faint">{t("language")}</Eyebrow>
          <div className="mt-2 flex items-center gap-3">
            <button
              type="button"
              role="switch"
              aria-checked={kazakh}
              onClick={() => setKazakh((k) => !k)}
              disabled={busy}
              aria-label={t("kazakhAria")}
              className={cn(
                "relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors duration-200 ease-snappy focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                kazakh ? "bg-accent" : "bg-surface-3",
                busy && "opacity-50",
              )}
            >
              <span
                className={cn(
                  "inline-block size-5 rounded-full bg-white shadow-sm transition-transform duration-200 ease-snappy",
                  kazakh ? "translate-x-4" : "translate-x-0",
                )}
              />
            </button>
            <span className="text-sm text-ink">{t("kazakh")}</span>
            <span className="font-mono text-eyebrow uppercase tabular-nums text-faint">
              {kazakh ? t("kazakhOn") : t("kazakhOff")}
            </span>
          </div>
        </div>
      </div>

      <Button
        type="submit"
        variant="accent"
        size="lg"
        loading={busy}
        disabled={!canSubmit}
        className="mt-6 h-12 w-full sm:w-auto"
      >
        {!busy && <Scissors className="size-5" />}
        {busy ? t("starting") : t("makeClips")}
      </Button>

      <p className="mt-3 text-sm text-muted">{t("creditNote")}</p>
    </form>
  );
}
