"""Free proxy pool: fetch from proxyscrape.com → test against YouTube → persist in R2.

Free proxies have ~10-40% live rate and short lifetimes; we test in parallel and keep
only working ones. HTTP proxies are tested via urllib; SOCKS proxies are excluded (urllib
limitation — add socks support when switching to paid proxies).

FLOW (run.py import branch):
  1. load_proxy_pool()    — load pool from R2 ([] on miss/error).
  2. If len < min_size:   — refresh_proxy_pool() + save_proxy_pool().
  3. Outer proxy loop:    — try each proxy; inner cookie loop unchanged.
  4. All jars gated:      — that proxy's IP is blocked → try next proxy.
  5. After success:       — rotate winning proxy to front, save updated pool.

R2 key: internal/ytdlp_proxy_pool.json (private, not under public CDN path).
"""

from __future__ import annotations

import concurrent.futures
import json
import tempfile
import urllib.request
from pathlib import Path

from app import storage
from app.config import get_settings

PROXY_POOL_R2_KEY = "internal/ytdlp_proxy_pool.json"
# proxyscrape.com public API — returns one proxy per line in 'protocol://host:port' format.
_PROXYSCRAPE_API = (
    "https://api.proxyscrape.com/v4/free-proxy-list/get"
    "?request=display_proxies&proxy_format=protocolipport"
    "&format=text&timeout=5000&country=all&ssl=all&anonymity=all"
)
_YOUTUBE_TEST_URL = "https://www.youtube.com/robots.txt"


# ─────────────────────────── pure / contained helpers ───────────────────────────


def pool_enabled() -> bool:
    """True only in cloud mode (R2 available). Mirrors ytdlp_cookies.cookies_enabled()."""
    return get_settings().storage_backend == "r2"


def _proxy_pool_r2_key() -> str:
    s = get_settings()
    return (s.ytdlp_proxy_pool_r2_key or "").strip() or PROXY_POOL_R2_KEY


def _test_http_proxy(proxy: str, timeout: float = 3.0) -> bool:
    """Return True if an HTTP proxy can reach YouTube robots.txt. SOCKS → False (filtered out)."""
    if not proxy.lower().startswith("http"):
        return False  # SOCKS proxies need the 'socks' package; skip for now
    try:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler)
        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
        with opener.open(_YOUTUBE_TEST_URL, timeout=timeout) as resp:
            return bool(resp.status < 500)
    except Exception:
        return False


# ─────────────────────────── public API ───────────────────────────


def fetch_free_proxies() -> list[str]:
    """Fetch proxy list from proxyscrape.com API. Returns 'protocol://host:port' strings."""
    try:
        req = urllib.request.Request(_PROXYSCRAPE_API, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode()
        proxies = [line.strip() for line in text.splitlines() if line.strip()]
        print(f"[proxy-pool] fetched {len(proxies)} raw proxies from proxyscrape")
        return proxies
    except Exception as e:
        print(f"[proxy-pool] fetch FAILED ({type(e).__name__}: {e}); returning empty list")
        return []


def refresh_proxy_pool(target: int = 20, max_workers: int = 50) -> list[str]:
    """Fetch proxies, test in parallel, return up to `target` working HTTP proxies."""
    proxies = fetch_free_proxies()
    if not proxies:
        return []

    working: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_proxy = {ex.submit(_test_http_proxy, p): p for p in proxies}
        for fut in concurrent.futures.as_completed(future_to_proxy):
            p = future_to_proxy[fut]
            try:
                if fut.result():
                    working.append(p)
                    print(f"[proxy-pool] OK: {p}")
                    if len(working) >= target:
                        for pending in future_to_proxy:
                            pending.cancel()
                        break
            except Exception:
                pass

    print(f"[proxy-pool] refresh: {len(working)} working HTTP proxies (of {len(proxies)} fetched)")
    return working


def load_proxy_pool() -> list[str]:
    """Load proxy pool from R2. Returns [] on miss/error (never raises)."""
    s = get_settings()
    key = _proxy_pool_r2_key()
    tmp = Path(tempfile.mktemp(suffix=".json"))
    try:
        storage._r2_client().download_file(s.r2_bucket, key, str(tmp))
        data = tmp.read_text(encoding="utf-8")
        tmp.unlink(missing_ok=True)
        pool: list[str] = json.loads(data)
        print(f"[proxy-pool] loaded {len(pool)} proxies from r2://{key}")
        return pool
    except Exception as e:
        tmp.unlink(missing_ok=True)
        print(
            f"[proxy-pool] load MISS for r2://{key} ({type(e).__name__}: {e}); "
            "proceeding without proxy pool"
        )
        return []


def save_proxy_pool(proxies: list[str]) -> None:
    """Save proxy pool to R2. Best-effort + logged (never raises)."""
    s = get_settings()
    key = _proxy_pool_r2_key()
    tmp = Path(tempfile.mktemp(suffix=".json"))
    try:
        tmp.write_text(json.dumps(proxies), encoding="utf-8")
        storage._r2_client().upload_file(
            str(tmp),
            s.r2_bucket,
            key,
            ExtraArgs={"ContentType": "application/json"},
        )
        tmp.unlink(missing_ok=True)
        print(f"[proxy-pool] saved {len(proxies)} proxies to r2://{key}")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        print(f"[proxy-pool] save FAILED for r2://{key} ({type(e).__name__}: {e})")
