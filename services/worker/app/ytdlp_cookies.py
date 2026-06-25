"""YouTube-cookie store with AUTO-REFRESH on Cloudflare R2 (free bot-gate bypass).

WHY: YouTube bot-gates Modal datacenter IPs ("Sign in to confirm you are not a bot").
Authenticated cookies make yt-dlp look logged-in and pass the gate even from a DC-IP.

KEY MECHANISM: yt-dlp, given a WRITABLE ``--cookies`` FILE, REWRITES that file with
refreshed cookies after each run (the session self-rotates). On Modal the image is
read-only and containers are ephemeral, so that rotation would be lost — UNLESS we
persist the cookie file in shared storage and write the rotated file back after each
download. We use R2 (already wired in ``app.storage``) as the persistent cookie store:
every successful download keeps the session fresh.

FLOW (run.py import branch):
  1. ``pull_cookies(tmp)``  — download the R2 cookie object into a WRITABLE temp file.
  2. ``import_youtube(..., cookies_file=tmp)`` — yt-dlp reads + REWRITES ``tmp``.
  3. ``push_cookies(tmp)``  — upload the rotated ``tmp`` back to R2 (only on success).

KEEP-WARM (deploy/modal/worker.py cron): even with zero user traffic the session would
idle-expire; a scheduled lightweight ``--skip-download`` rotation keeps it alive.

Border: pure/contained decisions (``cookies_enabled``, ``cookies_temp_path``) are
testable functions; the R2 I/O (``pull_cookies``/``push_cookies``) is a thin wrapper
that REUSES the ``app.storage`` R2 client (no hand-rolled boto3). No silent fallbacks
(rule #8): every cookie miss / R2 error is LOGGED, never swallowed silently.
"""

from __future__ import annotations

from pathlib import Path

from app import storage
from app.config import get_settings

# Private R2 object key for the rotating cookie jar. Deliberately under ``internal/`` —
# NOT below the public CDN clip path ({job}/...) so it is never served to users even if
# the bucket is public-by-key. Overridable via ``YTDLP_COOKIES_R2_KEY`` (config default).
COOKIES_KEY = "internal/ytdlp_cookies.txt"

# Temp filename for the cookie jar inside a job's out_dir (writable, ephemeral). yt-dlp
# rewrites THIS file in place; we then push it back to R2. One stable name per job dir.
_TEMP_COOKIES_NAME = "ytdlp_cookies.txt"

# Keep-warm target: a long-standing, stable, public Creative Commons clip. "Big Buck
# Bunny" (Blender Foundation, CC-BY) has been public for years — safe for a
# ``--skip-download`` session ping that keeps the cookie session alive with zero traffic.
KEEP_WARM_VIDEO_URL = "https://www.youtube.com/watch?v=YE7VzlLtp-4"


# ─────────────────────────── pure / contained helpers (unit-tested) ───────────────────────────


def cookies_r2_key() -> str:
    """R2 object key for the cookie jar (config override → constant default). PURE-ish.

    Reads ``YTDLP_COOKIES_R2_KEY`` from settings so the founder can relocate the jar
    without a code change; falls back to ``COOKIES_KEY`` when unset/blank.
    """
    key = (get_settings().ytdlp_cookies_r2_key or "").strip()
    return key or COOKIES_KEY


def cookies_enabled() -> bool:
    """Should we use the R2 rotating cookie store (vs the local-dev config file)? PURE-ish.

    R2 path is live ONLY in cloud mode (``STORAGE_BACKEND=r2``). In local dev there is no
    R2, so we return False → run.py falls back to the plain ``YTDLP_COOKIES_FILE`` /
    ``YTDLP_COOKIES_BROWSER`` config (dev keeps working without any cloud).
    """
    return get_settings().storage_backend == "r2"


def cookies_temp_path(out_dir: Path) -> Path:
    """Writable temp path for the cookie jar inside a job's ``out_dir``. PURE.

    yt-dlp REWRITES this file with the rotated session; it must be writable (the baked
    image cookie file at /root/cookies.txt is read-only, so we never hand yt-dlp that).
    """
    return out_dir / _TEMP_COOKIES_NAME


# Baked cookie-jar POOL for multi-cookie fallback. The founder drops one or more
# www.youtube.com_cookies*.txt at the repo root; deploy/modal/worker.py bakes them into the image
# under this read-only dir. run.py tries each jar in turn (a bot-gated jar → next) and only gives
# up if ALL are bot-gated → far more resilient than one jar (stale burner cookies are common).
BAKED_COOKIES_DIR = Path("/root/cookies")


def baked_jars() -> list[Path]:
    """Baked cookie-jar files (the founder's dropped pool), sorted by name. [] if none. PURE-ish.

    Read-only IMAGE files — the caller COPIES each to a writable temp before yt-dlp (which rewrites
    the --cookies file with a rotated session). Sorted name order → deterministic, stable try order.
    """
    d = BAKED_COOKIES_DIR
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix == ".txt")


# ─────────────────────────── R2 I/O (reuses app.storage client; logged, never silent) ──────────


def pull_cookies(dest: Path) -> bool:
    """Download the R2 cookie object → ``dest`` (a writable temp path). Returns success.

    True  → the jar existed in R2 and was written to ``dest`` (pass it to yt-dlp).
    False → absent OR any R2 error (logged clearly; caller proceeds WITHOUT cookies —
            best-effort download still attempted, rule #8: the miss is never silent).
    """
    s = get_settings()
    key = cookies_r2_key()
    try:
        storage._r2_client().download_file(s.r2_bucket, key, str(dest))
    except Exception as e:  # noqa: BLE001 — absent jar or R2 blip: log + proceed w/o cookies
        print(
            f"[ytdlp-cookies] pull MISS for r2://{key} ({type(e).__name__}: {e}); "
            "proceeding WITHOUT cookies (bot-gate bypass disabled this run)"
        )
        return False
    print(f"[ytdlp-cookies] pulled rotating cookie jar from r2://{key} -> {dest}")
    return True


def push_cookies(src: Path) -> None:
    """Upload ``src`` (the yt-dlp-rotated jar) back to the R2 cookie key. Best-effort.

    Called ONLY after a SUCCESSFUL download (yt-dlp rewrote ``src`` with a fresh session).
    Best-effort but NOT silent (rule #8): success and failure are both logged clearly —
    a push failure just means the next run reuses the last-known-good jar (no crash).
    """
    s = get_settings()
    key = cookies_r2_key()
    if not src.exists():
        print(
            f"[ytdlp-cookies] push SKIP: rotated jar {src} missing "
            "(yt-dlp did not write cookies this run); keeping last-known-good in R2"
        )
        return
    try:
        storage._r2_client().upload_file(
            str(src), s.r2_bucket, key, ExtraArgs={"ContentType": "text/plain"}
        )
    except Exception as e:  # noqa: BLE001 — keep last-known-good jar; LOG, never swallow
        print(
            f"[ytdlp-cookies] push FAILED for r2://{key} ({type(e).__name__}: {e}); "
            "keeping last-known-good cookies in R2"
        )
        return
    print(f"[ytdlp-cookies] pushed rotated cookie jar {src} -> r2://{key} (session refreshed)")
