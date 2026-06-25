"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Input, Label } from "@/components/ui/Input";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

const MIN_PASSWORD_LENGTH = 8;

/**
 * Pure client-side validation for the set/update-password form. Returns the error
 * message to show, or null when the input is valid. Length is the FIRST gate so a
 * too-short pair never surfaces the mismatch message. Exported for unit tests.
 */
export function validatePassword(password: string, confirm: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (password !== confirm) {
    return "Passwords don't match.";
  }
  return null;
}

/**
 * Optional "Set / update password" panel for the account page.
 *
 * Google-OAuth and email-code (OTP) users land WITHOUT a password, so the password
 * sign-in path is a dead-end for them until they set one. The (app) route group
 * guarantees an active session, so we set the password on the live session via
 * `supabase.auth.updateUser({ password })` — idempotent, so we always present it as
 * "set / update" rather than branching on unreliable "has password" detection (OTP
 * users also carry an email identity, so client-side detection is not trustworthy).
 *
 * On success we router.refresh() — auth/plan UI caches stale state after auth changes.
 */
export function AccountSecurity() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Without a configured Supabase project there's no session to update — hide the panel
  // entirely rather than render a control that would throw on submit.
  if (!isSupabaseConfigured) return null;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const invalid = validatePassword(password, confirm);
    if (invalid) {
      setError(invalid);
      return;
    }

    setLoading(true);
    try {
      const supabase = createSupabaseBrowserClient();
      const { error: err } = await supabase.auth.updateUser({ password });
      // Surface the Supabase error verbatim — no silent fallback. (If the project has
      // "Secure password change" / reauthentication enabled, Supabase returns a nonce
      // error here, which the user will see exactly rather than a generic failure.)
      if (err) throw err;
      setPassword("");
      setConfirm("");
      setSuccess("Password updated. You can now sign in with your email and password.");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't update your password. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-lg border border-line bg-surface">
      <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5 sm:px-6">
        <Eyebrow tone="muted" as="h2">
          Sign-in
        </Eyebrow>
      </header>

      <div className="px-5 py-5 sm:px-6 sm:py-6">
        <h3 className="text-base font-medium text-ink">Password</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          Add a password so you can sign in with email and password, in addition to Google and
          email codes.
        </p>

        <form onSubmit={onSubmit} className="mt-5 space-y-4" noValidate>
          <div>
            <Label htmlFor="new-password">New password</Label>
            <Input
              id="new-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
            />
          </div>
          <div>
            <Label htmlFor="confirm-password">Confirm password</Label>
            <Input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Re-enter your password"
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-bad">
              {error}
            </p>
          )}
          {success && (
            <p role="status" className="text-sm text-thought">
              {success}
            </p>
          )}

          <Button
            type="submit"
            variant="accent"
            loading={loading}
            disabled={!password || !confirm}
          >
            Set / update password
          </Button>
        </form>
      </div>
    </section>
  );
}
