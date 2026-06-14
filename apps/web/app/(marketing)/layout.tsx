import { CursorGlow } from "@/components/marketing/CursorGlow";
import { Footer } from "@/components/marketing/Footer";
import { MarketingNav } from "@/components/marketing/MarketingNav";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {/* behind content (z-0); shows through transparent sections only */}
      <CursorGlow />
      <div className="relative z-10 flex min-h-dvh flex-col">
        <MarketingNav />
        <main className="flex-1">{children}</main>
        <Footer />
      </div>
    </>
  );
}
