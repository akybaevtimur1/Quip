"use client";

import { Captions, ChevronDown, Download, FileText, Film } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

// Меню «Скачать» — экспорт-свобода: юзер уносит клип в любой редактор.
//  • С субтитрами (MP4)  — готовый прожжённый клип (последний рендер).
//  • Без субтитров (MP4) — чистая 9:16-вертикалка (рендер на лету, текущий edit-state).
//  • Субтитры (.SRT)     — тайминги совпадают с видео, импорт в CapCut/Premiere/Resolve.
// Clean/SRT всегда отражают ТЕКУЩИЕ правки (рендерятся из edit-state), MP4-с-субтитрами
// может быть устаревшим до «Рендер». Сервер ставит Content-Disposition → скачивание даже
// при кросс-доменном воркере.

const WORKER_BASE = process.env.NEXT_PUBLIC_WORKER_URL ?? "";

export function ExportMenu({
  jobId,
  clipId,
  subtitledUrl,
  align = "right",
  placement = "down",
  className = "",
}: {
  jobId: string;
  clipId: string;
  /** Готовый прожжённый mp4 (последний рендер). null → ещё не рендерился. */
  subtitledUrl: string | null;
  align?: "left" | "right";
  placement?: "up" | "down";
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const cleanUrl = `${WORKER_BASE}/jobs/${jobId}/clips/${clipId}/export/clean.mp4`;
  const srtUrl = `${WORKER_BASE}/jobs/${jobId}/clips/${clipId}/export.srt`;

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-sm border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-ink transition duration-200 ease-snappy hover:-translate-y-px hover:border-line-strong hover:bg-surface-3"
      >
        <Download className="size-4" />
        Скачать
        <ChevronDown className={`size-3.5 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute z-30 min-w-[238px] overflow-hidden rounded-md border border-line-strong bg-surface shadow-[0_16px_40px_-12px_rgba(0,0,0,.7)] ${
            align === "right" ? "right-0" : "left-0"
          } ${placement === "up" ? "bottom-full mb-1" : "mt-1"}`}
        >
          <ExportItem
            href={subtitledUrl ?? undefined}
            disabled={!subtitledUrl}
            icon={<Captions className="size-4" />}
            title="С субтитрами (MP4)"
            sub={subtitledUrl ? "Готовый клип" : "Сначала нажми «Рендер»"}
            onPick={() => setOpen(false)}
          />
          <ExportItem
            href={cleanUrl}
            icon={<Film className="size-4" />}
            title="Без субтитров (MP4)"
            sub="Чистая вертикалка · ~неск. сек"
            onPick={() => setOpen(false)}
          />
          <ExportItem
            href={srtUrl}
            icon={<FileText className="size-4" />}
            title="Субтитры (.SRT)"
            sub="Для CapCut / Premiere / Resolve"
            onPick={() => setOpen(false)}
          />
        </div>
      )}
    </div>
  );
}

function ExportItem({
  href,
  disabled,
  icon,
  title,
  sub,
  onPick,
}: {
  href?: string;
  disabled?: boolean;
  icon: ReactNode;
  title: string;
  sub: string;
  onPick: () => void;
}) {
  return (
    <a
      href={href}
      download
      role="menuitem"
      aria-disabled={disabled}
      onClick={() => {
        if (!disabled) onPick();
      }}
      className={`flex items-start gap-2.5 px-3 py-2.5 text-left transition ${
        disabled ? "pointer-events-none opacity-40" : "hover:bg-surface-2"
      }`}
    >
      <span className="mt-0.5 text-muted">{icon}</span>
      <span className="flex flex-col">
        <span className="text-sm font-semibold text-ink">{title}</span>
        <span className="text-xs text-muted">{sub}</span>
      </span>
    </a>
  );
}
