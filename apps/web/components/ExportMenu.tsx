"use client";

import { Captions, ChevronDown, Download, FileText, Film, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { captionedDownloadUrl, clipCleanExportUrl, clipSrtUrl } from "@/lib/api";

// Меню «Скачать» — экспорт-свобода: юзер уносит клип в любой редактор.
//  • С субтитрами (MP4)  — прожжённый клип. Если есть СВЕЖИЙ рендер (bakedUrl) — отдаём его
//    (быстро); иначе рендерим на лету из ТЕКУЩЕГО edit-state (всегда совпадает с превью).
//  • Без субтитров (MP4) — чистая 9:16-вертикалка (рендер на лету, текущий edit-state).
//  • Субтитры (.SRT)     — тайминги совпадают с видео, импорт в CapCut/Premiere/Resolve.
//
// FEEDBACK: «С/без субтитрами» рендерятся на лету (десятки секунд) — раньше это были голые
// `<a download>`, и пока сервер рендерил, НИЧЕГО не происходило → юзер кликал по 3 раза. Теперь
// клик качает через fetch + показывает спиннер «Preparing…» и блокирует пункт, пока файл не готов;
// при ошибке (CORS/сеть) — фолбэк на прямую ссылку. Имя файла — из Content-Disposition, иначе дефолт.

const WORKER_BASE = process.env.NEXT_PUBLIC_WORKER_URL ?? "";

/** Fetch a (possibly on-demand-rendered) export as a blob and save it to disk. Filename comes
 *  from Content-Disposition when present, else `fallbackName`. Exported so the grid's "Download
 *  all" reuses the exact same blob-download path (no duplicated logic). Throws on a non-OK
 *  response so callers can fall back to a direct link / surface the failure (no silent swallow). */
export async function downloadFile(url: string, fallbackName: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition");
  const name = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd ?? "")?.[1] ?? fallbackName;
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = decodeURIComponent(name);
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objUrl), 10_000);
}

export function ExportMenu({
  jobId,
  clipId,
  bakedUrl = null,
  cleanBakedUrl = null,
  dirty = false,
  align = "right",
  placement = "down",
  className = "",
}: {
  jobId: string;
  clipId: string;
  /** Свежий прожжённый рендер (render_url после «Рендер»). null → рендерим на лету. */
  bakedUrl?: string | null;
  /** Stable CLEAN (no-caption) clip already on the CDN — `clip.video_url` from the grid. When
   *  present, "No captions" streams THIS instantly instead of re-rendering `export/clean.mp4`.
   *  The editor leaves it null (edits may diverge from the baked clean clip) → on-demand render. */
  cleanBakedUrl?: string | null;
  /** Есть НЕ-отрендеренные правки (изменён шрифт хука и т.п.)? → bakedUrl устарел,
   *  скачиваем свежий on-demand рендер, а не протухший CDN-снимок. */
  dirty?: boolean;
  align?: "left" | "right";
  placement?: "up" | "down";
  className?: string;
}) {
  const t = useTranslations("exportMenu");
  const [open, setOpen] = useState(false);
  // Which item is currently being prepared/downloaded (its key), or null. Disables clicks + spins.
  const [busy, setBusy] = useState<string | null>(null);
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

  // No captions: prefer the stable clean CDN clip (instant) when the caller has it; else render
  // a fresh clean export on demand.
  const cleanInstant = !!cleanBakedUrl;
  const cleanUrl = cleanBakedUrl ?? clipCleanExportUrl(WORKER_BASE, jobId, clipId);
  const srtUrl = clipSrtUrl(WORKER_BASE, jobId, clipId);
  // С субтитрами: baked-рендер ТОЛЬКО когда нет невыданных правок (dirty=false). При dirty
  // (юзер сменил шрифт хука и т.п.) baked устарел → on-demand рендер текущего edit-state.
  const captionedUrl = captionedDownloadUrl(WORKER_BASE, jobId, clipId, bakedUrl, dirty);

  // A baked CDN render is instant (no server render) → don't bother with the fetch path. The on-demand
  // endpoints render on the fly → fetch + spinner so the user sees progress instead of dead-clicking.
  const captionedInstant = !!bakedUrl && !dirty;

  const pick = async (key: string, url: string, fallbackName: string, instant: boolean) => {
    if (busy) return;
    if (instant) {
      // Stable CDN artifact — let the browser stream it to disk natively (no render wait).
      const a = document.createElement("a");
      a.href = url;
      a.download = fallbackName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setOpen(false);
      return;
    }
    setBusy(key);
    try {
      await downloadFile(url, fallbackName);
      setOpen(false);
    } catch (e) {
      // CORS/network → fall back to a direct navigation (native download, no progress UI).
      console.warn("[export] blob download failed, falling back to direct link:", e);
      window.location.href = url;
    } finally {
      setBusy(null);
    }
  };

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
        {t("download")}
        <ChevronDown className={`size-3.5 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute z-30 min-w-[238px] max-w-[calc(100vw-1.5rem)] overflow-hidden rounded-md border border-line-strong bg-surface shadow-[0_16px_40px_-12px_rgba(0,0,0,.7)] ${
            align === "right" ? "right-0" : "left-0"
          } ${placement === "up" ? "bottom-full mb-1" : "mt-1"}`}
        >
          <ExportItem
            icon={<Captions className="size-4" />}
            title={t("captioned.title")}
            sub={captionedInstant ? t("captioned.subRendered") : t("captioned.subRender")}
            busy={busy === "captioned"}
            busyLabel={t("preparingClip")}
            disabled={!!busy && busy !== "captioned"}
            onPick={() => pick("captioned", captionedUrl, `${clipId}-captioned.mp4`, captionedInstant)}
          />
          <ExportItem
            icon={<Film className="size-4" />}
            title={t("clean.title")}
            sub={cleanInstant ? t("clean.subInstant") : t("clean.subRender")}
            busy={busy === "clean"}
            busyLabel={t("preparingClip")}
            disabled={!!busy && busy !== "clean"}
            onPick={() => pick("clean", cleanUrl, `${clipId}-clean.mp4`, cleanInstant)}
          />
          <ExportItem
            icon={<FileText className="size-4" />}
            title={t("srt.title")}
            sub={t("srt.sub")}
            busy={busy === "srt"}
            busyLabel={t("preparing")}
            disabled={!!busy && busy !== "srt"}
            onPick={() => pick("srt", srtUrl, `${clipId}.srt`, false)}
          />
        </div>
      )}
    </div>
  );
}

function ExportItem({
  icon,
  title,
  sub,
  busy = false,
  busyLabel,
  disabled,
  onPick,
}: {
  icon: ReactNode;
  title: string;
  sub: string;
  busy?: boolean;
  /** Required: the localized "preparing" copy shown while this item renders on demand. */
  busyLabel: string;
  disabled?: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled || busy}
      aria-busy={busy}
      onClick={onPick}
      className={`flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition ${
        disabled ? "pointer-events-none opacity-40" : "hover:bg-surface-2"
      }`}
    >
      <span className="mt-0.5 text-muted">
        {busy ? <Loader2 className="size-4 animate-spin text-accent" /> : icon}
      </span>
      <span className="flex flex-col">
        <span className="text-sm font-semibold text-ink">{title}</span>
        <span className="text-xs text-muted">{busy ? busyLabel : sub}</span>
      </span>
    </button>
  );
}
