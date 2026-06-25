import { Container } from "@/components/ui/Container";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Section } from "@/components/ui/Section";

// ────────────────────────────────────────────────────────────────────────────
// PipelineDemo — the page climax: a REAL montaged run of the pipeline (upload →
// moments → vertical clips), replacing the old interactive QuipStudio concept
// sim. Silent 1876×964 landscape montage: autoplays muted in a loop, poster
// shown until it plays. Same frame/tokens as the rest of the landing for
// consistency. Plain <video> (HTML attrs) → server component, no client JS.
// ────────────────────────────────────────────────────────────────────────────

export function PipelineDemo() {
  return (
    <Section id="demo" className="relative">
      <Container className="relative">
        <div className="mx-auto max-w-2xl text-center">
          <Eyebrow tone="accent" className="inline-flex items-center gap-2">
            <span className="size-1.5 rounded-pill bg-accent" aria-hidden />
            The real pipeline
          </Eyebrow>
          <h2 className="mt-4 font-display text-h2 text-ink sm:text-display-lg">
            Here&rsquo;s how it cuts &mdash; and <span className="text-accent">why</span> exactly like that.
          </h2>
          <p className="mt-4 text-lead text-muted">
            A real run, end to end: upload &rarr; find the moments &rarr; cut vertical clips, each with a
            reason.
          </p>
        </div>

        <div className="mx-auto mt-12 max-w-4xl overflow-hidden rounded-lg border border-line-strong bg-surface shadow-[0_32px_80px_-32px_rgba(0,0,0,.6)]">
          <video
            className="block h-auto w-full"
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
            poster="/demo/pipeline-demo-poster.jpg"
            aria-label="Quip pipeline demo: from an uploaded video to finished vertical clips"
          >
            <source src="/demo/pipeline-demo.mp4" type="video/mp4" />
          </video>
        </div>
      </Container>
    </Section>
  );
}
