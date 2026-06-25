import { describe, expect, it, vi } from "vitest";

// The validator lives in the client component (its only consumer), which also imports
// `@/…` UI + supabase modules. vitest (node env, no path alias) can't resolve those at
// runtime, so we stub them — the validator itself is pure and pulls in none of them.
vi.mock("@/components/ui/Button", () => ({ Button: () => null }));
vi.mock("@/components/ui/Eyebrow", () => ({ Eyebrow: () => null }));
vi.mock("@/components/ui/Input", () => ({ Input: () => null, Label: () => null }));
vi.mock("@/lib/supabase/client", () => ({ createSupabaseBrowserClient: () => ({}) }));
vi.mock("@/lib/supabase/config", () => ({ isSupabaseConfigured: false }));

const { validatePassword } = await import("../../components/app/AccountSecurity");

describe("validatePassword", () => {
  it("accepts an 8+ char password that matches its confirmation", () => {
    expect(validatePassword("hunter2!", "hunter2!")).toBeNull();
    expect(validatePassword("a-very-long-passphrase", "a-very-long-passphrase")).toBeNull();
  });

  it("rejects passwords shorter than 8 characters (boundary)", () => {
    expect(validatePassword("short7!", "short7!")).toBe(
      "Password must be at least 8 characters.",
    );
    // Exactly 8 is allowed (>= 8, not > 8) — guards an off-by-one in the boundary check.
    expect(validatePassword("eightchr", "eightchr")).toBeNull();
  });

  it("rejects when the two fields don't match", () => {
    expect(validatePassword("hunter2!", "hunter2?")).toBe("Passwords don't match.");
  });

  it("checks length before match, so a short mismatched pair reports the length error", () => {
    // Length is the first gate — a too-short pair should never surface the match error.
    expect(validatePassword("abc", "xyz")).toBe("Password must be at least 8 characters.");
  });
});
