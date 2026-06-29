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
import time
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
# Speed-test target: a well-known YouTube thumbnail (~150 KB).
# Testing against YT CDN (not a generic host) measures the actual proxy→YouTube throughput,
# which is what matters for yt-dlp downloads. Rick Astley maxres = ~150 KB, always available.
_SPEED_TEST_URL = "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg"
# Minimum speed to keep a proxy. 0.5 Mbps = 500 KB/s — at this rate a 300 MB (30-min 720p)
# video takes ~80 min. Empirical: free proxies from Modal DC-IP top out at ~1.0-1.5 Mbps
# against YouTube CDN, so 0.5 is a realistic floor that keeps the pool populated.
# Pool is sorted fastest-first so the best proxy is always tried first.
_MIN_SPEED_MBPS: float = 0.5


# ─────────────────────────── pure / contained helpers ───────────────────────────


def pool_enabled() -> bool:
    """True only in cloud mode (R2 available). Mirrors ytdlp_cookies.cookies_enabled()."""
    return get_settings().storage_backend == "r2"


def _proxy_pool_r2_key() -> str:
    s = get_settings()
    return (s.ytdlp_proxy_pool_r2_key or "").strip() or PROXY_POOL_R2_KEY


def _test_proxy_speed(proxy: str, timeout: float = 8.0) -> tuple[bool, float]:
    """Download a YouTube thumbnail through the proxy; return (passes_threshold, speed_mbps).

    Speed-tests against YouTube CDN rather than a generic host so we measure the path
    that actually matters for yt-dlp (proxy → YouTube servers). SOCKS → (False, 0.0).
    """
    if not proxy.lower().startswith("http"):
        return False, 0.0  # SOCKS needs the 'socks' package; skip
    try:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler)
        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
        t0 = time.monotonic()
        with opener.open(_SPEED_TEST_URL, timeout=timeout) as resp:
            data = resp.read()
        elapsed = max(time.monotonic() - t0, 0.001)
        mbps = round((len(data) * 8) / (elapsed * 1_000_000), 2)
        return mbps >= _MIN_SPEED_MBPS, mbps
    except Exception:
        return False, 0.0


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
    """Fetch proxies, speed-test against YouTube CDN, return fastest HTTP proxies sorted desc."""
    proxies = fetch_free_proxies()
    if not proxies:
        return []

    # (speed_mbps, proxy) pairs that passed the threshold — collected until we hit target.
    results: list[tuple[float, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_proxy = {ex.submit(_test_proxy_speed, p): p for p in proxies}
        for fut in concurrent.futures.as_completed(future_to_proxy):
            p = future_to_proxy[fut]
            try:
                ok, mbps = fut.result()
                if ok:
                    results.append((mbps, p))
                    print(f"[proxy-pool] PASS {mbps:.1f} Mbps: {p}")
                    if len(results) >= target:
                        for pending in future_to_proxy:
                            pending.cancel()
                        break
                # (slow/dead proxies are silently skipped — noise in logs otherwise)
            except Exception:
                pass

    # Sort fastest-first so run.py tries the best proxy on the first attempt.
    results.sort(key=lambda x: x[0], reverse=True)
    working = [p for _, p in results]

    if results:
        speeds = [s for s, _ in results]
        avg = sum(speeds) / len(speeds)
        median = sorted(speeds)[len(speeds) // 2]
        print(
            f"[proxy-pool] refresh done: {len(working)} proxies ≥{_MIN_SPEED_MBPS} Mbps "
            f"| fastest {results[0][0]:.1f} Mbps | avg {avg:.1f} Mbps | median {median:.1f} Mbps"
        )
        # ETA estimates: fastest proxy, 700 MB video (30-min 1080p)
        video_mb = 700
        for label, mbps in [("fastest", results[0][0]), ("median", median)]:
            eta_min = (video_mb * 8) / (mbps * 60) if mbps > 0 else 999
            print(f"[proxy-pool] ETA 700MB via {label} proxy ({mbps:.1f} Mbps): {eta_min:.0f} min")
    else:
        print(
            f"[proxy-pool] refresh done: 0 proxies passed {_MIN_SPEED_MBPS} Mbps threshold "
            f"(tested {len(proxies)} raw)"
        )
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
