import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { AuthDevNotice } from "@/components/auth/AuthDevNotice";
import { AuthForm } from "@/components/auth/AuthForm";
import { isSupabaseConfigured } from "@/lib/supabase/config";

export const metadata: Metadata = { title: "Sign in", robots: { index: false } };

/** Only allow internal relative redirect targets (no open-redirect). */
function safeNext(next: string | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const sp = await searchParams;
  const next = safeNext(sp.next);
  const t = await getTranslations("auth.login");
  return (
    <div className="rounded-xl border border-line bg-surface p-7">
      <h1 className="font-display text-h3 text-ink">{t("title")}</h1>
      <p className="mt-1 text-sm text-muted">{t("subtitle")}</p>
      {sp.error && (
        <p
          role="alert"
          className="mt-4 rounded-md border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad"
        >
          {sp.error}
        </p>
      )}
      <div className="mt-6">
        {isSupabaseConfigured ? <AuthForm mode="login" next={next} /> : <AuthDevNotice next={next} />}
      </div>
      <p className="mt-5 text-center text-sm text-muted">
        {t("newToQuip")}{" "}
        <Link href="/signup" className="font-medium text-accent hover:underline">
          {t("createAccount")}
        </Link>
      </p>
    </div>
  );
}
