"use client";

import { RotateCcw, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";
import { Button } from "@/components/ui/Button";

// Граница ошибок для всей (app)-группы (dashboard + редактор). Любое необработанное
// исключение при рендере (напр. транзиентный сбой при переключении клипов) ловится ЗДЕСЬ
// и показывает дружелюбный экран с «Try again» (reset) — а не «выкидывает» юзера на пустую
// страницу / в корень (фидбек фаундера: «меня выкинуло один раз»). reset() перемонтирует
// сегмент без полной перезагрузки.
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Видимый лог в консоли (не тихо глотаем) — для диагностики, если повторится.
    console.error("App route error:", error);
  }, [error]);

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-bg px-6 text-center">
      <div className="w-full max-w-md rounded-2xl border border-bad/40 bg-bad/10 p-6">
        <div className="flex items-center justify-center gap-2 text-bad">
          <TriangleAlert className="size-5" />
          <h2 className="font-display text-lg font-bold">Something went wrong</h2>
        </div>
        <p className="mt-3 text-sm text-muted">
          The editor hit an unexpected error. Your saved edits are safe — try again, or go back to
          your clips.
        </p>
        <div className="mt-5 flex items-center justify-center gap-2">
          <Button variant="accent" size="sm" onClick={reset}>
            <RotateCcw className="size-4" />
            Try again
          </Button>
          <Link
            href="/dashboard"
            className="rounded-lg border border-line px-4 py-2 text-sm text-muted transition hover:border-line-strong hover:text-ink"
          >
            All clips
          </Link>
        </div>
      </div>
    </div>
  );
}
