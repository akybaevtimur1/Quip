"use client";

import { Link2, Minus, Plus, Scissors, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";

const MIN_CLIPS = 1;
const MAX_CLIPS = 10;
const DEFAULT_CLIPS = 6;
const MAX_UPLOAD_MB = 500;

export function SourceForm({
  onSubmit,
  onSubmitFile,
  busy,
}: {
  onSubmit: (url: string, maxClips: number) => void;
  onSubmitFile: (file: File, maxClips: number) => void;
  busy: boolean;
}) {
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [count, setCount] = useState(DEFAULT_CLIPS);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const urlValid = /youtu\.?be/i.test(url) && url.trim().length > 12;
  const canSubmit = !busy && (file != null || urlValid);
  const clamp = (n: number) => Math.max(MIN_CLIPS, Math.min(MAX_CLIPS, n));

  function pickFile(f: File | null) {
    setFileError(null);
    if (!f) {
      setFile(null);
      return;
    }
    if (!f.type.startsWith("video/")) {
      setFileError("Нужен видеофайл");
      return;
    }
    if (f.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setFileError(`Файл больше ${MAX_UPLOAD_MB} МБ`);
      return;
    }
    setFile(f);
    setUrl(""); // выбран файл → URL очищаем (файл приоритетнее)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    if (file) onSubmitFile(file, count);
    else onSubmit(url.trim(), count);
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-xl">
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Link2 className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-muted" />
          <input
            type="url"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Вставь ссылку на YouTube-видео"
            disabled={busy || file != null}
            aria-label="Ссылка на YouTube-видео"
            className="h-12 w-full rounded-sm border border-line bg-surface pl-10 pr-3 text-ink placeholder:text-faint outline-none transition-colors duration-200 ease-snappy hover:border-line-strong focus:border-accent/60 disabled:opacity-50"
          />
        </div>
        <Button
          type="submit"
          variant="accent"
          size="lg"
          loading={busy}
          disabled={!canSubmit}
          className="h-12"
        >
          {!busy && <Scissors className="size-5" />}
          {busy ? "Запуск…" : "Нарезать"}
        </Button>
      </div>

      {/* Загрузка файла: drop-zone или плашка выбранного файла */}
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
          aria-label="Загрузить видеофайл"
          className={`mt-3 flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed px-4 py-3 text-sm text-muted transition duration-200 ease-snappy hover:border-line-strong hover:text-ink ${
            dragging ? "border-accent bg-surface-2" : "border-line bg-surface"
          } ${busy ? "pointer-events-none opacity-50" : ""}`}
        >
          <Upload className="size-4" />
          Перетащи видео сюда или <span className="font-medium text-ink">выбери файл</span>
        </div>
      ) : (
        <div className="mt-3 flex items-center justify-between gap-2 rounded-md border border-line bg-surface px-4 py-3">
          <span className="flex items-center gap-2 truncate text-sm text-ink">
            <Upload className="size-4 shrink-0 text-accent" />
            <span className="truncate">{file.name}</span>
          </span>
          <IconButton
            onClick={() => pickFile(null)}
            disabled={busy}
            aria-label="Убрать файл"
            size="sm"
          >
            <X className="size-4" />
          </IconButton>
        </div>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        hidden
        onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
      />
      {fileError ? <p className="mt-1 pl-1 text-sm text-bad">{fileError}</p> : null}

      <div className="mt-3 flex items-center gap-3 pl-1">
        <span className="text-sm text-muted">Сколько клипов:</span>
        <div className="inline-flex items-center gap-1 rounded-md border border-line bg-surface p-1">
          <IconButton
            onClick={() => setCount((c) => clamp(c - 1))}
            disabled={busy || count <= MIN_CLIPS}
            aria-label="Меньше клипов"
            size="sm"
            className="text-ink hover:text-ink"
          >
            <Minus className="size-4" />
          </IconButton>
          <span className="w-6 text-center font-mono text-base font-semibold tabular-nums text-ink">
            {count}
          </span>
          <IconButton
            onClick={() => setCount((c) => clamp(c + 1))}
            disabled={busy || count >= MAX_CLIPS}
            aria-label="Больше клипов"
            size="sm"
            className="text-ink hover:text-ink"
          >
            <Plus className="size-4" />
          </IconButton>
        </div>
        <span className="text-xs text-muted">ИИ предложит — лишние снимешь сам</span>
      </div>
      <p className="mt-2 pl-1 text-sm text-muted">
        Один спикер, до 90 минут. YouTube-ссылка или файл с компа.
      </p>
    </form>
  );
}
