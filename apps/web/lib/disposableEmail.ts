/**
 * Disposable / temp-mail domain blocklist — MIRRORS
 * services/worker/app/billing.py DISPOSABLE_EMAIL_DOMAINS (the enforcement source of truth).
 *
 * Anti-abuse: the free plan (2 videos) gets farmed with throwaway inboxes. The SERVER is the
 * authority (rejects disposable domains at the free-job gate); this client copy is UX only —
 * it blocks obvious throwaway domains before submit with a friendly message. Keep in sync when
 * billing.py changes.
 */
const DISPOSABLE_EMAIL_DOMAINS: ReadonlySet<string> = new Set([
  "0-mail.com",
  "10minutemail.com",
  "10minutemail.net",
  "20minutemail.com",
  "33mail.com",
  "boun.cr",
  "burnermail.io",
  "byom.de",
  "dispostable.com",
  "emailondeck.com",
  "fakeinbox.com",
  "getairmail.com",
  "getnada.com",
  "guerrillamail.com",
  "guerrillamail.net",
  "guerrillamail.org",
  "guerrillamailblock.com",
  "inboxbear.com",
  "inboxkitten.com",
  "mailcatch.com",
  "maildrop.cc",
  "mailinator.com",
  "mailnesia.com",
  "mintemail.com",
  "mohmal.com",
  "moakt.com",
  "mytemp.email",
  "nada.email",
  "sharklasers.com",
  "spam4.me",
  "tempmail.com",
  "tempmail.net",
  "tempmailo.com",
  "temp-mail.io",
  "temp-mail.org",
  "throwawaymail.com",
  "trashmail.com",
  "trashmail.de",
  "wegwerfmail.de",
  "yopmail.com",
  "yopmail.fr",
  "yopmail.net",
]);

/**
 * Is this email's domain a known disposable/temp-mail service? Case-insensitive, trims
 * whitespace, matches the domain or any of its subdomains (mail.guerrillamail.com) but not
 * lookalikes (notyopmail.com). Malformed input (no "@", empty domain) → false.
 */
export function isDisposableEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const domain = email.trim().toLowerCase().split("@")[1] ?? "";
  if (!domain || !domain.includes(".")) return false;
  for (const bad of DISPOSABLE_EMAIL_DOMAINS) {
    if (domain === bad || domain.endsWith(`.${bad}`)) return true;
  }
  return false;
}
