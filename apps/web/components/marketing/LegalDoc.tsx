import { Container } from "@/components/ui/Container";

export interface LegalSection {
  heading: string;
  /** Each item is one paragraph (rendered as a string expression, so apostrophes
   *  and quotes are safe — no react/no-unescaped-entities lint). */
  body: string[];
}

/** Shared layout for long-form legal pages (Privacy, Terms). Plain, readable,
 *  consistent with the marketing design tokens. */
export function LegalDoc({
  title,
  updated,
  intro,
  sections,
}: {
  title: string;
  updated: string;
  intro: string;
  sections: LegalSection[];
}) {
  return (
    <Container className="max-w-3xl py-20 sm:py-28">
      <h1 className="font-display text-h2 text-ink sm:text-display-lg">{title}</h1>
      <p className="mt-3 font-mono text-sm text-faint">Last updated: {updated}</p>
      <p className="mt-6 text-lead text-muted">{intro}</p>

      <div className="mt-12 space-y-10">
        {sections.map((s, i) => (
          <section key={s.heading}>
            <h2 className="font-display text-h3 text-ink">
              <span className="mr-2 font-mono text-sm tabular-nums text-accent">
                {String(i + 1).padStart(2, "0")}
              </span>
              {s.heading}
            </h2>
            <div className="mt-3 space-y-3">
              {s.body.map((p, j) => (
                <p key={j} className="text-sm leading-relaxed text-muted">
                  {p}
                </p>
              ))}
            </div>
          </section>
        ))}
      </div>
    </Container>
  );
}
