import { FOOTER } from "@/lib/landingContent";
import { Container } from "../components/primitives";
import { Logo } from "./Nav";

export function Footer() {
  return (
    <footer className="relative border-t border-line pt-20">
      <Container>
        <div className="grid gap-12 pb-16 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,2fr)]">
          <div className="max-w-[30ch]">
            <Logo />
            <p className="mt-5 text-[14px] leading-relaxed text-muted">{FOOTER.tagline}</p>
            <a
              href="mailto:ceo@quip.ink"
              className="mt-6 inline-block font-mono text-[12px] tracking-[0.04em] text-faint transition-colors hover:text-muted"
            >
              {FOOTER.support}
            </a>
          </div>

          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3">
            {FOOTER.cols.map((col) => (
              <div key={col.title}>
                <h3 className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint">{col.title}</h3>
                <ul className="mt-4 flex flex-col gap-3">
                  {col.links.map((link) => (
                    <li key={link.label}>
                      <a href={link.href} className="text-[14px] text-muted transition-colors hover:text-ink">
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </Container>

      <div className="border-t border-line">
        <Container>
          <div className="flex flex-col items-center justify-between gap-2 py-6 text-center sm:flex-row sm:text-left">
            <p className="font-mono text-[11.5px] tracking-[0.04em] text-faint">{FOOTER.stripe}</p>
            <p className="font-mono text-[11.5px] tracking-[0.04em] text-faint">{FOOTER.honesty}</p>
          </div>
        </Container>
      </div>
    </footer>
  );
}
