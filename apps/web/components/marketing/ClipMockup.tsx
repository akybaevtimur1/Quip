import { cn } from "@/lib/cn";

/** A faithful 9:16 clip preview: dark talking-head scene + coral hook plate on
 *  top + burned-in subtitle with an emphasized word + progress scrubber.
 *  Mirrors what Quip actually renders (hook plate color = HookOverlay.box_color). */
export function ClipMockup({
  hook = "The mistake that cost me 3 years",
  subtitle = "so i ",
  emphasis = "rebuilt",
  subtitleTail = " the whole thing",
  progress = 0.42,
  className,
}: {
  hook?: string;
  subtitle?: string;
  emphasis?: string;
  subtitleTail?: string;
  progress?: number;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative aspect-[9/16] w-full overflow-hidden rounded-xl border border-line-strong bg-black @container",
        "shadow-[0_40px_90px_-30px_rgba(0,0,0,.85)]",
        className,
      )}
      role="img"
      aria-label={`Vertical clip preview. Hook: ${hook}. Caption: ${subtitle}${emphasis}${subtitleTail}`}
    >
      {/* lit scene: cool base + warm key light on the subject */}
      <div className="absolute inset-0 bg-[radial-gradient(120%_85%_at_60%_38%,#2a211c_0%,#161519_46%,#0a0a0d_100%)]" />
      <div className="absolute inset-0 mix-blend-screen bg-[radial-gradient(46%_30%_at_62%_40%,rgba(255,176,138,.26),transparent_62%)]" />
      {/* head + shoulders silhouette */}
      <div className="absolute left-1/2 top-[52%] size-[42%] -translate-x-1/2 -translate-y-1/2 rounded-[50%_50%_46%_46%] bg-[radial-gradient(circle_at_50%_34%,#6d5346,#34261f_72%)]" />
      <div className="absolute bottom-[16%] left-1/2 h-[34%] w-[58%] -translate-x-1/2 rounded-t-[44%] bg-[#241a14]" />

      {/* hook plate (coral, top) */}
      <div className="absolute inset-x-3 top-3">
        <span className="inline-block rounded-md bg-accent px-2.5 py-1.5 font-display text-[clamp(11px,2.6cqw,15px)] font-extrabold uppercase leading-tight tracking-tight text-white shadow-[0_6px_18px_-6px_rgba(0,0,0,.6)]">
          {hook}
        </span>
      </div>

      {/* burned subtitle with one emphasized word */}
      <div className="absolute inset-x-3 bottom-[16%] text-center">
        <p className="font-display text-[clamp(15px,5cqw,26px)] font-extrabold uppercase leading-[1.05] tracking-tight text-white [text-shadow:0_2px_0_rgba(0,0,0,.55)]">
          {subtitle}
          <span className="text-accent">{emphasis}</span>
          {subtitleTail}
        </p>
      </div>

      {/* scrubber */}
      <div className="absolute inset-x-3 bottom-4 h-[3px] overflow-hidden rounded-full bg-white/20">
        <div className="h-full rounded-full bg-accent" style={{ width: `${progress * 100}%` }} />
      </div>
    </div>
  );
}
