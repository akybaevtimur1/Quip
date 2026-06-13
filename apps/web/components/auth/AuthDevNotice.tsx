import Link from "next/link";
import { buttonVariants } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

/** Shown on auth pages when Supabase isn't connected yet (founder plugs it in
 *  later). Lets local testing reach the app without a real account. */
export function AuthDevNotice({ next }: { next: string }) {
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-line bg-surface-2 p-3.5 text-sm leading-relaxed text-muted">
        Accounts run through Supabase, which isn&rsquo;t connected in this environment yet. You can
        explore the app in dev mode for now.
      </div>
      <Link href={next} className={cn("w-full", buttonVariants({ size: "md" }))}>
        Continue to the app
      </Link>
    </div>
  );
}
