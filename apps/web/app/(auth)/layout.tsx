import { getTranslations } from "next-intl/server";
import { Logo } from "@/components/ui/Logo";

export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("auth");
  return (
    <div className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden px-5 py-12">
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-0 size-[600px] -translate-x-1/2 -translate-y-1/3 rounded-full bg-[radial-gradient(circle,rgba(255,90,61,.08),transparent_62%)]"
      />
      <div className="relative w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>
        {children}
        <p className="mt-6 text-center text-xs leading-relaxed text-faint">
          {t.rich("agree", {
            terms: (chunks) => (
              <a href="/terms" className="underline hover:text-muted">
                {chunks}
              </a>
            ),
            privacy: (chunks) => (
              <a href="/privacy" className="underline hover:text-muted">
                {chunks}
              </a>
            ),
          })}
        </p>
      </div>
    </div>
  );
}
