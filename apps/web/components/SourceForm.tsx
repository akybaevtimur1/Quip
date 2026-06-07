"use client";

import { Link2, Loader2, Scissors } from "lucide-react";
import { useState } from "react";

export function SourceForm({
  onSubmit,
  busy,
}: {
  onSubmit: (url: string) => void;
  busy: boolean;
}) {
  const [url, setUrl] = useState("");
  const valid = /youtu\.?be/i.test(url) && url.trim().length > 12;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && !busy) onSubmit(url.trim());
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
      <p className="mt-2 pl-1 text-sm text-muted">
        Один спикер, до 90 минут. Загрузка файла — позже.
      </p>
    </form>
  );
}
