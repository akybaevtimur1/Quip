import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";

// Calm status report — the run didn't complete. The message reads as plain body text
// (not a raw mono <pre> dump), so a failure feels like an honest reading from the
// instrument, not a stack trace.
export function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="w-full max-w-xl rounded-lg border border-bad/40 bg-bad/[0.06] p-6">
      <Eyebrow tone="faint">Run stopped</Eyebrow>
      <h2 className="mt-2 font-display text-h3 text-bad">Something went wrong</h2>
      <p className="mt-2 text-sm leading-relaxed text-muted">{message}</p>
      <Button variant="accent" size="sm" onClick={onRetry} className="mt-5">
        <RotateCcw className="size-4" />
        Try again
      </Button>
    </div>
  );
}
