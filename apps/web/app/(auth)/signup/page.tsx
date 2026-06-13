import type { Metadata } from "next";
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
  return (
    <div className="rounded-xl border border-line bg-surface p-7">
      <h1 className="font-display text-h3 text-ink">Create your account</h1>
      <p className="mt-1 text-sm text-muted">2 free videos every month. No card required.</p>
      <div className="mt-6">
        {isSupabaseConfigured ? (
          <AuthForm mode="signup" next={next} />
        ) : (
          <AuthDevNotice next={next} />
        )}
      </div>
      <p className="mt-5 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
