"use client";

import { Link2, Loader2, Minus, Plus, Scissors } from "lucide-react";
import { useState } from "react";

const MIN_CLIPS = 1;
const MAX_CLIPS = 10;
const DEFAULT_CLIPS = 6;

export function SourceForm({
  onSubmit,
  busy,
}: {
  onSubmit: (url: string, maxClips: number) => void;
  busy: boolean;
}) {
  const [url, setUrl] = useState("");
  const [count, setCount] = useState(DEFAULT_CLIPS);
  const valid = /youtu\.?be/i.test(url) && url.trim().length > 12;

  const clamp = (n: number) => Math.max(MIN_CLIPS, Math.min(MAX_CLIPS, n));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && !busy) onSubmit(url.trim(), count);
      }}
      className="w-full max-w-xl"
    >
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Link2 className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-muted" />
          <input
            type="url"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Вставь ссылку на YouTube-видео"
            disabled={busy}
            aria-label="Ссылка на YouTube-видео"
            className="h-12 w-full rounded-xl border border-line bg-surface pl-10 pr-3 text-ink placeholder:text-muted outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
          />
        </div>
        <button
          type="submit"
          disabled={!valid || busy}
          className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-accent px-5 font-semibold text-white transition hover:bg-accent-2 focus:outline-none focus:ring-2 focus:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? (
            <Loader2 className="size-5 animate-spin" />
          ) : (
            <Scissors className="size-5" />
          )}
          {busy ? "Запуск…" : "Нарезать"}
        </button>
      </div>
      <div className="mt-3 flex items-center gap-3 pl-1">
        <span className="text-sm text-muted">Сколько клипов:</span>
        <div className="inline-flex items-center gap-2 rounded-xl border border-line bg-surface p-1">
          <button
            type="button"
            onClick={() => setCount((c) => clamp(c - 1))}
            disabled={busy || count <= MIN_CLIPS}
            aria-label="Меньше клипов"
            className="inline-flex size-8 items-center justify-center rounded-lg text-ink transition hover:bg-surface-2 focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <Minus className="size-4" />
          </button>
          <span className="w-6 text-center font-mono text-base font-semibold tabular-nums text-ink">
            {count}
          </span>
          <button
            type="button"
            onClick={() => setCount((c) => clamp(c + 1))}
            disabled={busy || count >= MAX_CLIPS}
            aria-label="Больше клипов"
            className="inline-flex size-8 items-center justify-center rounded-lg text-ink transition hover:bg-surface-2 focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <Plus className="size-4" />
          </button>
        </div>
        <span className="text-xs text-muted">ИИ предложит — лишние снимешь сам</span>
      </div>
      <p className="mt-2 pl-1 text-sm text-muted">
        Один спикер, до 90 минут. Загрузка файла — позже.
      </p>
    </form>
  );
}
