import { RotateCcw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/Button";

export function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="w-full max-w-xl rounded-2xl border border-bad/40 bg-bad/10 p-6">
      <div className="flex items-center gap-2 text-bad">
        <TriangleAlert className="size-5" />
        <h2 className="font-display text-lg font-bold">Something went wrong</h2>
      </div>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-lg bg-surface p-3 font-mono text-xs text-muted">
        {message}
      </pre>
      <Button variant="accent" size="sm" onClick={onRetry} className="mt-4">
        <RotateCcw className="size-4" />
        Try again
      </Button>
    </div>
  );
}
