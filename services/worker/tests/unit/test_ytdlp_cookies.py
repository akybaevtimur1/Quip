"""Tests for app.ytdlp_cookies — the R2 rotating cookie store (R2 client MOCKED).

These cover the pure/contained decisions (enabled, temp-path, key override) and the thin
R2 I/O contract: pull returns False on absent/raises (and is LOGGED, never silent), push is
best-effort + logged, and — at the run.py wiring level — push happens after a SIMULATED
successful download and NOT after a failure. Real R2 upload/download is integration-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app import ytdlp_cookies
from app.config import Settings

# ─────────────────────────── settings + R2-client fakes (no real cloud) ───────────────────────────


def _settings(**over: Any) -> Settings:
    """Minimal Settings (deepgram key so the provider validator passes), overridable."""
    base: dict[str, Any] = {"deepgram_api_key": "k", "r2_bucket": "quip"}
    base.update(over)
    return Settings(**base)


class _FakeR2:
    """Records download/upload calls; can be told to raise to simulate an absent jar / R2 blip."""

    def __init__(self, *, download_raises: bool = False, upload_raises: bool = False) -> None:
        self.download_raises = download_raises
        self.upload_raises = upload_raises
        self.downloaded: list[tuple[str, str, str]] = []
        self.uploaded: list[tuple[str, str, str, dict[str, Any]]] = []

    def download_file(self, bucket: str, key: str, dest: str) -> None:
        if self.download_raises:
            raise RuntimeError("404 Not Found")  # absent jar / R2 error
        self.downloaded.append((bucket, key, dest))
        Path(dest).write_text("# rotated cookie jar\n", encoding="utf-8")

    def upload_file(self, src: str, bucket: str, key: str, ExtraArgs: dict[str, Any]) -> None:
        if self.upload_raises:
            raise RuntimeError("PutObject denied")
        self.uploaded.append((src, bucket, key, ExtraArgs))


@pytest.fixture
def patch_cloud(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Patch get_settings (r2 mode) + storage._r2_client; return a setter for the fake client."""

    def apply(client: _FakeR2, *, settings: Settings | None = None) -> _FakeR2:
        s = settings or _settings(storage_backend="r2")
        monkeypatch.setattr(ytdlp_cookies, "get_settings", lambda: s)
        monkeypatch.setattr(ytdlp_cookies.storage, "_r2_client", lambda: client)
        return client

    return apply


# ─────────────────────────── pure / contained decisions ───────────────────────────


def test_cookies_enabled_only_in_r2_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ytdlp_cookies, "get_settings", lambda: _settings(storage_backend="r2"))
    assert ytdlp_cookies.cookies_enabled() is True


def test_cookies_disabled_in_local_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    # local-dev fallback path: no R2 → run.py uses the plain config cookies_file/browser.
    monkeypatch.setattr(ytdlp_cookies, "get_settings", lambda: _settings(storage_backend="local"))
    assert ytdlp_cookies.cookies_enabled() is False


def test_cookies_temp_path_is_writable_child_of_out_dir(tmp_path: Path) -> None:
    p = ytdlp_cookies.cookies_temp_path(tmp_path)
    assert p.parent == tmp_path  # inside the job's writable out_dir, NOT the read-only image file
    assert p.name == "ytdlp_cookies.txt"


def test_cookies_r2_key_defaults_to_internal_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ytdlp_cookies, "get_settings", lambda: _settings(storage_backend="r2"))
    key = ytdlp_cookies.cookies_r2_key()
    assert key == ytdlp_cookies.COOKIES_KEY == "internal/ytdlp_cookies.txt"
    # NOT under the public CDN clip path ({job}/...): never served to users.
    assert not key.endswith(".mp4") and key.startswith("internal/")


def test_cookies_r2_key_honors_config_override(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(storage_backend="r2", ytdlp_cookies_r2_key="internal/custom_jar.txt")
    monkeypatch.setattr(ytdlp_cookies, "get_settings", lambda: s)
    assert ytdlp_cookies.cookies_r2_key() == "internal/custom_jar.txt"


# ─────────────────────────── pull_cookies (R2 download, mocked) ───────────────────────────


def test_pull_cookies_true_and_writes_dest_when_jar_exists(
    patch_cloud: Any, tmp_path: Path
) -> None:
    client = patch_cloud(_FakeR2())
    dest = tmp_path / "ytdlp_cookies.txt"
    assert ytdlp_cookies.pull_cookies(dest) is True
    assert dest.exists()  # jar written to the writable temp path for yt-dlp to rotate
    assert client.downloaded[0][1] == "internal/ytdlp_cookies.txt"  # pulled the right key


def test_pull_cookies_false_and_logs_when_absent_or_r2_error(
    patch_cloud: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Absent jar / any R2 error → False + clear log, NOT a crash (rule #8: never silent).
    patch_cloud(_FakeR2(download_raises=True))
    dest = tmp_path / "ytdlp_cookies.txt"
    assert ytdlp_cookies.pull_cookies(dest) is False
    assert not dest.exists()
    out = capsys.readouterr().out
    assert "[ytdlp-cookies] pull MISS" in out  # the miss is LOGGED


# ─────────────────────────── push_cookies (R2 upload, mocked) ───────────────────────────


def test_push_cookies_uploads_rotated_jar_to_cookie_key(patch_cloud: Any, tmp_path: Path) -> None:
    client = patch_cloud(_FakeR2())
    src = tmp_path / "ytdlp_cookies.txt"
    src.write_text("# rotated by yt-dlp\n", encoding="utf-8")
    ytdlp_cookies.push_cookies(src)
    assert len(client.uploaded) == 1
    up_src, _bucket, up_key, _extra = client.uploaded[0]
    assert up_src == str(src)
    assert up_key == "internal/ytdlp_cookies.txt"


def test_push_cookies_skips_when_src_missing(
    patch_cloud: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # yt-dlp did not write a jar this run → nothing to push; keep last-known-good (logged skip).
    client = patch_cloud(_FakeR2())
    ytdlp_cookies.push_cookies(tmp_path / "does_not_exist.txt")
    assert client.uploaded == []
    assert "push SKIP" in capsys.readouterr().out


def test_push_cookies_logs_failure_without_raising(
    patch_cloud: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # R2 upload error → best-effort: LOG, do not raise (keep last-known-good jar in R2).
    patch_cloud(_FakeR2(upload_raises=True))
    src = tmp_path / "ytdlp_cookies.txt"
    src.write_text("x\n", encoding="utf-8")
    ytdlp_cookies.push_cookies(src)  # must NOT raise
    assert "push FAILED" in capsys.readouterr().out


# ─────────────── run.py wiring contract: push AFTER success, NOT after failure ───────────────
# These drive the REAL run_pipeline import branch (pull → import → push) with the cookie I/O and
# downstream stages faked, so the "push only on a successful download" guard is unit-asserted
# end-to-end against run.py itself (not a re-implemented mirror) without touching R2 or yt-dlp.


class _StopPipeline(Exception):
    """Sentinel: halt run_pipeline right AFTER the import branch so the test stays cheap."""


def _wire_run_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, import_raises: bool
) -> dict[str, Any]:
    """Patch run.py's import-branch seams + cut the pipeline off right after the push point.

    Returns a dict recording pull/push calls and the cookies_file handed to import_youtube.
    """
    import app.run as run
    from app.errors import JobError

    rec: dict[str, Any] = {"pulled": [], "pushed": [], "cookies_file": None}

    monkeypatch.setattr(run, "get_settings", lambda: _settings(storage_backend="r2"))
    monkeypatch.setattr(run, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(run.ytdlp_cookies, "cookies_enabled", lambda: True)

    def fake_pull(dest: Path) -> bool:
        rec["pulled"].append(dest)
        dest.write_text("jar\n", encoding="utf-8")
        return True

    def fake_push(src: Path) -> None:
        rec["pushed"].append(src)

    monkeypatch.setattr(run.ytdlp_cookies, "pull_cookies", fake_pull)
    monkeypatch.setattr(run.ytdlp_cookies, "push_cookies", fake_push)

    def fake_import(url: str, out: Path, **kw: Any) -> object:
        rec["cookies_file"] = kw.get("cookies_file")
        if import_raises:
            raise JobError("import", "bot-gate")  # yt-dlp bot-gate → push must be SKIPPED
        return _FakeMeta()

    monkeypatch.setattr(run, "import_youtube", fake_import)
    # The line right after the import branch: stop the pipeline cheaply once we're past push.
    monkeypatch.setattr(
        run.db, "set_progress_detail", lambda *a, **k: (_ for _ in ()).throw(_StopPipeline())
    )
    return rec


class _FakeMeta:
    """Stand-in SourceMeta with just the fields run_pipeline reads before our cut-off."""

    duration = 120.0
    width = 1920
    height = 1080
    source = "youtube"


def test_wiring_pushes_after_successful_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import app.run as run

    rec = _wire_run_branch(monkeypatch, tmp_path, import_raises=False)
    with pytest.raises(_StopPipeline):  # halts right after the push point
        run.run_pipeline("job_seed", "https://youtube.com/watch?v=x")

    assert rec["pulled"], "pull must run before import"
    assert rec["pushed"], "push MUST run after a successful import"
    # The rotated WRITABLE temp jar (out_dir/ytdlp_cookies.txt) was handed to yt-dlp, not config.
    assert rec["cookies_file"] == str(run.ytdlp_cookies.cookies_temp_path(tmp_path / "job_seed"))


def test_wiring_does_not_push_after_failed_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import app.run as run
    from app.errors import JobError

    rec = _wire_run_branch(monkeypatch, tmp_path, import_raises=True)
    with pytest.raises(JobError):  # import bot-gate failure propagates
        run.run_pipeline("job_fail", "https://youtube.com/watch?v=x")

    assert rec["pulled"], "pull still runs before the (failing) import"
    assert rec["pushed"] == [], "push must NOT run after a failed import (keep last-known-good)"
