import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { AuthDevNotice } from "@/components/auth/AuthDevNotice";
import { AuthForm } from "@/components/auth/AuthForm";
import { isSupabaseConfigured } from "@/lib/supabase/config";

export const metadata: Metadata = { title: "Create account", robots: { index: false } };

function safeNext(next: string | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const next = safeNext((await searchParams).next);
  const t = await getTranslations("auth.signup");
  return (
    <div className="rounded-xl border border-line bg-surface p-7">
      <h1 className="font-display text-h3 text-ink">{t("title")}</h1>
      <p className="mt-1 text-sm text-muted">{t("subtitle")}</p>
      <div className="mt-6">
        {isSupabaseConfigured ? (
          <AuthForm mode="signup" next={next} />
        ) : (
          <AuthDevNotice next={next} />
        )}
      </div>
      <p className="mt-5 text-center text-sm text-muted">
        {t("haveAccount")}{" "}
        <Link href="/login" className="font-medium text-accent hover:underline">
          {t("signIn")}
        </Link>
      </p>
    </div>
  );
}
