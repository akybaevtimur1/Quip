import { RefreshCw, WifiOff } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Spinner } from "@/components/ui/Spinner";

// Calm, reassuring banner shown while the poller is reconnecting after a connectivity blip.
// The job keeps processing SERVER-SIDE — this is NOT a failure, so it deliberately wears the
// amber `warn` tone (never the red ErrorPanel) and tells the user, immediately, that it's their
// internet, that the video is safe, and that we reconnect automatically. `onRetry` forces an
// immediate re-poll of the SAME job (it never resets to the upload form).
export function ReconnectBanner({ onRetry }: { onRetry: () => void }) {
  const t = useTranslations("reconnect");
  return (
    <div className="mx-auto w-full max-w-xl rounded-lg border border-warn/40 bg-warn/[0.06] p-6">
      <Eyebrow tone="faint" className="inline-flex items-center gap-1.5">
        <WifiOff className="size-3.5" aria-hidden />
        {t("eyebrow")}
      </Eyebrow>
      <h2 className="mt-2 font-display text-h3 text-ink">{t("title")}</h2>
      <p className="mt-2 text-sm leading-relaxed text-muted">{t("body")}</p>
      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-3">
        <Button variant="secondary" size="sm" onClick={onRetry}>
          <RefreshCw className="size-4" aria-hidden />
          {t("retry")}
        </Button>
        <span className="inline-flex items-center gap-2 text-xs text-muted" aria-live="polite">
          <Spinner size="sm" />
          {t("autoRetry")}
        </span>
      </div>
    </div>
  );
}
