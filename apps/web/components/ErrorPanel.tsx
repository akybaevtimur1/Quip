import { RotateCcw, TriangleAlert } from "lucide-react";

export function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="w-full max-w-xl rounded-2xl border border-accent/40 bg-accent/10 p-6">
      <div className="flex items-center gap-2 text-accent">
        <TriangleAlert className="size-5" />
        <h2 className="font-display text-lg font-bold">Что-то пошло не так</h2>
      </div>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-lg bg-surface p-3 font-mono text-xs text-muted">
        {message}
      </pre>
      <button
        onClick={onRetry}
        className="mt-4 inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 font-semibold text-white transition hover:bg-accent-2 focus:outline-none focus:ring-2 focus:ring-accent/50"
      >
        <RotateCcw className="size-4" />
        Попробовать снова
      </button>
    </div>
  );
}
