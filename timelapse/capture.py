"""Capture one still: fetch (direct JPEG) -> overlay -> dedup -> save.

MVP path is `still_image` (see CLAUDE.md). Two idiosyncrasies handled here:
  * cache-busting  — these sources update the image in place at the same URL, so
    without a `?_t=` param an HTTP cache may hand back an identical frame.
  * MO DNR itok    — the Drupal derivative URL carries a `?itok=` token; the bare
    URL 404s when the style cache is flushed and the token can rotate. On a 404 we
    re-scrape the camera's page_url for the current `framegrab.jpg?itok=` URL.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
import time
from datetime import datetime

import httpx
from PIL import Image, UnidentifiedImageError

from . import store
from .config import Camera, Settings
from .overlay import apply_overlay

log = logging.getLogger("wxcam.capture")

USER_AGENT = "wxcam-timelapse/0.1 (+https://github.com/kawfey)"
_ITOK_RE = re.compile(r'https?://[^\s"\'<>]*?framegrab\.jpg\?itok=[^\s"\'<>&]+')


class CaptureError(RuntimeError):
    pass


def _cache_bust(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}_t={int(time.time() * 1000)}"


def _rescrape_itok(client: httpx.Client, page_url: str) -> str | None:
    """Find the current framegrab.jpg?itok= URL on the DNR camera page."""
    try:
        resp = client.get(page_url, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("itok re-scrape failed for %s: %s", page_url, e)
        return None
    m = _ITOK_RE.search(resp.text)
    if m:
        log.info("re-scraped fresh itok URL from %s", page_url)
        return m.group(0)
    return None


def fetch_still(cam: Camera, settings: Settings, client: httpx.Client) -> bytes:
    """Fetch the raw JPEG bytes for a `still_image` camera, handling cache-bust
    and (for DNR) an itok re-scrape on 404."""
    if cam.type != "still_image":
        raise CaptureError(
            f"{cam.name!r} is type {cam.type!r}; only 'still_image' is supported in the MVP"
        )

    base_url = cam.stream_url
    url = _cache_bust(base_url) if settings.cache_bust else base_url
    headers = {"User-Agent": USER_AGENT}

    resp = client.get(url, headers=headers)
    if resp.status_code == 404 and "itok=" in base_url and cam.page_url:
        fresh = _rescrape_itok(client, cam.page_url)
        if fresh:
            url = _cache_bust(fresh) if settings.cache_bust else fresh
            resp = client.get(url, headers=headers)

    resp.raise_for_status()
    data = resp.content
    if not data:
        raise CaptureError(f"empty response body from {url}")
    return data


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture_once(
    cam: Camera,
    settings: Settings,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> store.Frame | None:
    """Fetch -> overlay -> save one still. Returns the saved Frame, or None if the
    frame was a byte-identical duplicate of the previous one (dedup) and skipped."""
    owns_client = client is None
    client = client or httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        raw = fetch_still(cam, settings, client)
    finally:
        if owns_client:
            client.close()

    # Dedup on the *source* bytes (before overlay), since the overlay embeds a
    # timestamp that differs every frame.
    if settings.dedup_identical:
        prev = store.latest_frame(settings, cam.slug)
        if prev is not None and _sidecar_hash(prev.path) == _hash(raw):
            log.info("dedup: %s unchanged since %s, skipped", cam.slug, prev.when)
            return None

    when = now or datetime.now(settings.tz)
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise CaptureError(f"response from {cam.name!r} was not a decodable image: {e}")

    stamped = apply_overlay(img, cam.name, when)
    out = store.still_path(settings, cam.slug, when)
    out.parent.mkdir(parents=True, exist_ok=True)
    stamped.save(out, format="JPEG", quality=90)
    _write_sidecar_hash(out, _hash(raw))
    log.info("captured %s -> %s", cam.slug, out.relative_to(settings.data_dir))
    return store.Frame(path=out, when=when)


# Store the source-bytes hash alongside each still so dedup survives restarts
# without re-downloading. Sidecar keeps the JPEG itself clean.
def _sidecar(path):
    return path.with_suffix(".sha256")


def _write_sidecar_hash(path, digest: str) -> None:
    _sidecar(path).write_text(digest, encoding="ascii")


def _sidecar_hash(path) -> str | None:
    sc = _sidecar(path)
    try:
        return sc.read_text(encoding="ascii").strip()
    except OSError:
        return None
