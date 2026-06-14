"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

type Step = "email" | "code" | "password";

/** Multi-method auth against Supabase:
 *  - Google OAuth (one tap → /auth/callback exchanges the session).
 *  - Passwordless email code (signInWithOtp → user types the 6-digit {{ .Token }} →
 *    verifyOtp binds it to the SAME email, so the code is valid only for that user).
 *  - Classic email + password (secondary, behind a toggle) for people who prefer it.
 */
export function AuthForm({ mode, next }: { mode: "login" | "signup"; next: string }) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Normalised once and reused for BOTH signInWithOtp and verifyOtp → the code is
  // checked against the exact same account that requested it (founder requirement).
  const cleanEmail = email.trim().toLowerCase();
  const callbackUrl = () =>
    `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`;

  function fail(e: unknown, fallback: string) {
    setError(e instanceof Error ? e.message : fallback);
  }

  async function signInGoogle() {
    setError(null);
    setLoading(true);
    try {
      const { error: err } = await createSupabaseBrowserClient().auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: callbackUrl() },
      });
      if (err) throw err;
      // On success the browser redirects to Google; nothing else runs here.
    } catch (e) {
      fail(e, "Couldn't start Google sign-in. Try again.");
      setLoading(false);
    }
  }

  // Send a fresh 6-digit code to the entered email (works for new and existing users).
  async function doSendCode() {
    setError(null);
    setLoading(true);
    try {
      const { error: err } = await createSupabaseBrowserClient().auth.signInWithOtp({
        email: cleanEmail,
        options: { shouldCreateUser: true, emailRedirectTo: callbackUrl() },
      });
      if (err) throw err;
      setCode("");
      setStep("code");
    } catch (e) {
      fail(e, "Couldn't send the code. Check the email and try again.");
    } finally {
      setLoading(false);
    }
  }

  function onSendCode(e: React.FormEvent) {
    e.preventDefault();
    void doSendCode();
  }

  // Verify the typed code against the SAME email → session for that exact user.
  async function onVerifyCode(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { data, error: err } = await createSupabaseBrowserClient().auth.verifyOtp({
        email: cleanEmail,
        token: code.trim(),
        type: "email",
      });
      if (err) throw err;
      if (!data.session) throw new Error("Invalid or expired code.");
      router.replace(next);
      router.refresh();
    } catch (e) {
      fail(e, "Invalid or expired code. Request a new one.");
    } finally {
      setLoading(false);
    }
  }

  // Classic password fallback (login / signup).
  async function onPassword(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const supabase = createSupabaseBrowserClient();
      if (mode === "signup") {
        const { data, error: err } = await supabase.auth.signUp({
          email: cleanEmail,
          password,
          options: { emailRedirectTo: callbackUrl() },
        });
        if (err) throw err;
        if (data.session) {
          router.replace(next);
          router.refresh();
        } else {
          // Project requires confirmation → finish via the code we just emailed.
          setStep("code");
        }
      } else {
        const { error: err } = await supabase.auth.signInWithPassword({
          email: cleanEmail,
          password,
        });
        if (err) throw err;
        router.replace(next);
        router.refresh();
      }
    } catch (e) {
      fail(e, "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  // ─────────────────────────── code step ───────────────────────────
  if (step === "code") {
    return (
      <form onSubmit={onVerifyCode} className="space-y-4" noValidate>
        <div>
          <Label htmlFor="code">Enter your code</Label>
          <p className="mb-2.5 mt-1 text-sm text-muted">
            We sent a 6-digit code to <span className="text-ink">{cleanEmail}</span>.
          </p>
          {/* Supabase OTP length is configurable (6–8). Accept up to 8, enable at 6+,
              so it works whatever the project's "Email OTP Length" is set to. */}
          <Input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]*"
            maxLength={8}
            required
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
            placeholder="••••••"
            className="h-14 text-center text-2xl font-semibold tracking-[0.4em]"
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-bad">
            {error}
          </p>
        )}
        <Button type="submit" loading={loading} disabled={code.length < 6} className="w-full">
          Verify & continue
        </Button>
        <div className="flex items-center justify-between text-sm">
          <button
            type="button"
            onClick={() => void doSendCode()}
            disabled={loading}
            className="text-muted transition-colors hover:text-ink disabled:opacity-50"
          >
            Resend code
          </button>
          <button
            type="button"
            onClick={() => {
              setStep("email");
              setError(null);
            }}
            className="text-muted transition-colors hover:text-ink"
          >
            Use a different email
          </button>
        </div>
      </form>
    );
  }

  // ─────────────────────────── password step ───────────────────────────
  if (step === "password") {
    return (
      <form onSubmit={onPassword} className="space-y-4" noValidate>
        <div>
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-bad">
            {error}
          </p>
        )}
        <Button type="submit" loading={loading} className="w-full">
          {mode === "signup" ? "Create account" : "Sign in"}
        </Button>
        <button
          type="button"
          onClick={() => {
            setStep("email");
            setError(null);
          }}
          className="block w-full text-center text-sm text-muted transition-colors hover:text-ink"
        >
          ← Use an email code instead
        </button>
      </form>
    );
  }

  // ─────────────────────────── email step (default) ───────────────────────────
  return (
    <div className="space-y-4">
      <Button
        type="button"
        variant="secondary"
        loading={loading}
        onClick={() => void signInGoogle()}
        className="w-full"
      >
        <GoogleIcon />
        Continue with Google
      </Button>

      <div className="flex items-center gap-3 text-xs text-faint">
        <span className="h-px flex-1 bg-line" />
        or
        <span className="h-px flex-1 bg-line" />
      </div>

      <form onSubmit={onSendCode} className="space-y-4" noValidate>
        <div>
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-bad">
            {error}
          </p>
        )}
        <Button type="submit" loading={loading} disabled={!email.trim()} className="w-full">
          Continue with email
        </Button>
      </form>

      <button
        type="button"
        onClick={() => {
          setStep("password");
          setError(null);
        }}
        className="block w-full text-center text-sm text-muted transition-colors hover:text-ink"
      >
        Sign in with a password instead
      </button>
    </div>
  );
}

/** Google "G" mark (official 4-colour), inline so it works without external assets. */
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"
      />
    </svg>
  );
}
