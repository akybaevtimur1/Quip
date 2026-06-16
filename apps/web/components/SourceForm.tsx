"use client";

import { Minus, Plus, Scissors, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";

const MIN_CLIPS = 1;
const MAX_CLIPS = 10;
const DEFAULT_CLIPS = 6;
const MAX_UPLOAD_MB = 500;

export function SourceForm({
  onSubmitFile,
  busy,
}: {
  // onSubmit (YouTube-link path) kept optional for compatibility — the link input is hidden
  // for now (upload-only); re-add the URL field here to restore it.
  onSubmit?: (url: string, maxClips: number) => void;
  onSubmitFile: (file: File, maxClips: number) => void;
  busy: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [count, setCount] = useState(DEFAULT_CLIPS);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const canSubmit = !busy && file != null;
  const clamp = (n: number) => Math.max(MIN_CLIPS, Math.min(MAX_CLIPS, n));

  function pickFile(f: File | null) {
    setFileError(null);
    if (!f) {
      setFile(null);
      return;
    }
    if (!f.type.startsWith("video/")) {
      setFileError("Please choose a video file");
      return;
    }
    if (f.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setFileError(`File is larger than ${MAX_UPLOAD_MB} MB`);
      return;
    }
    setFile(f);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || !file) return;
    onSubmitFile(file, count);
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-xl">
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
          aria-label="Upload a video file"
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed px-4 py-10 text-center text-sm text-muted transition duration-200 ease-snappy hover:border-line-strong hover:text-ink ${
            dragging ? "border-accent bg-surface-2" : "border-line bg-surface"
          } ${busy ? "pointer-events-none opacity-50" : ""}`}
        >
          <Upload className="size-6 text-accent" />
          <span>
            Drag a video here or <span className="font-medium text-ink">choose a file</span>
          </span>
          <span className="text-xs text-faint">MP4, MOV… up to {MAX_UPLOAD_MB} MB</span>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-2 rounded-md border border-line bg-surface px-4 py-3">
          <span className="flex items-center gap-2 truncate text-sm text-ink">
            <Upload className="size-4 shrink-0 text-accent" />
            <span className="truncate">{file.name}</span>
          </span>
          <IconButton
            onClick={() => pickFile(null)}
            disabled={busy}
            aria-label="Remove file"
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
        accept="video/*"
        hidden
        onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
      />
      {fileError ? <p className="mt-1 pl-1 text-sm text-bad">{fileError}</p> : null}

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 pl-1">
        <span className="text-sm text-muted">Clips:</span>
        <div className="inline-flex items-center gap-1 rounded-md border border-line bg-surface p-1">
          <IconButton
            onClick={() => setCount((c) => clamp(c - 1))}
            disabled={busy || count <= MIN_CLIPS}
            aria-label="Fewer clips"
            size="sm"
            className="size-9 text-ink hover:text-ink sm:size-7"
          >
            <Minus className="size-4" />
          </IconButton>
          <span className="w-6 text-center font-mono text-base font-semibold tabular-nums text-ink">
            {count}
          </span>
          <IconButton
            onClick={() => setCount((c) => clamp(c + 1))}
            disabled={busy || count >= MAX_CLIPS}
            aria-label="More clips"
            size="sm"
            className="size-9 text-ink hover:text-ink sm:size-7"
          >
            <Plus className="size-4" />
          </IconButton>
        </div>
        <span className="text-xs text-muted">AI suggests — uncheck any you don’t want</span>
      </div>

      <Button
        type="submit"
        variant="accent"
        size="lg"
        loading={busy}
        disabled={!canSubmit}
        className="mt-4 h-12 w-full sm:w-auto"
      >
        {!busy && <Scissors className="size-5" />}
        {busy ? "Starting…" : "Make clips"}
      </Button>

      <p className="mt-3 pl-1 text-sm text-muted">
        Upload any video — its length just has to fit your remaining minutes (and up to 3 hours per
        video). 1 credit = 60 minutes.
      </p>
    </form>
  );
}
