import { getLocale } from "next-intl/server";
import { LocaleSwitcher } from "@/components/i18n/LocaleSwitcher";
import { resolveLocale } from "@/i18n/locale";
import { getLandingContent } from "@/lib/landingContent";
import { Container } from "../components/primitives";
import { Logo } from "./Nav";

export async function Footer() {
  const footer = getLandingContent(resolveLocale(await getLocale())).footer;
  return (
    <footer className="relative border-t border-line pt-20">
      <Container>
        <div className="grid gap-12 pb-16 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,2fr)]">
          <div className="max-w-[30ch]">
            <Logo />
            <p className="mt-5 text-[14px] leading-relaxed text-muted">{footer.tagline}</p>
            <a
              href="mailto:ceo@quip.ink"
              className="mt-6 inline-block font-mono text-[12px] tracking-[0.04em] text-faint transition-colors hover:text-muted"
            >
              {footer.support}
            </a>
            <div className="mt-6">
              <LocaleSwitcher />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3">
            {footer.cols.map((col) => (
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
            <p className="font-mono text-[11.5px] tracking-[0.04em] text-faint">{footer.stripe}</p>
            <p className="font-mono text-[11.5px] tracking-[0.04em] text-faint">{footer.honesty}</p>
          </div>
        </Container>
      </div>
    </footer>
  );
}
