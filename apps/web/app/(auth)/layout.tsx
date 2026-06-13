import { Logo } from "@/components/ui/Logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
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
          By continuing you agree to our{" "}
          <a href="/terms" className="underline hover:text-muted">
            Terms
          </a>{" "}
          and{" "}
          <a href="/privacy" className="underline hover:text-muted">
            Privacy Policy
          </a>
          .
        </p>
      </div>
    </div>
  );
}
