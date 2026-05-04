"""Local cache of downloaded album cover images.

The renderer needs the album artwork as a real PIL.Image. Caching it
avoids hammering Deezer's CDN every render and keeps `--dry-run`
preview cheap. Cache key is the SHA-1 of the URL so renames don't
collide; entries older than `TTL_DAYS` are pruned on access.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

import requests
from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)

TTL_SECONDS = 7 * 86400


def _cache_dir() -> Path:
    """Returns the writable cache directory; falls back to /tmp on
    permission errors so a broken FS doesn't crash a renderer run."""
    base = Path(getattr(settings, "SOCIAL_CACHE_DIR", "/tmp/tq_social"))
    covers = base / "covers"
    try:
        covers.mkdir(parents=True, exist_ok=True)
        return covers
    except OSError:
        fallback = Path("/tmp/tq_social/covers")
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning("SOCIAL_CACHE_DIR %s unwritable; using %s", base, fallback)
        return fallback


def _path_for(url: str) -> Path:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return _cache_dir() / f"{h}.jpg"


def fetch(url: str | None) -> Image.Image | None:
    """Return a `PIL.Image` for `url`, or None on any failure.

    The renderer must accept a None and substitute a coloured tile
    so a single bad URL never blocks a publication."""
    if not url:
        return None
    p = _path_for(url)
    fresh = p.exists() and (time.time() - p.stat().st_mtime) < TTL_SECONDS
    if not fresh:
        try:
            r = requests.get(url, timeout=10, stream=True)
            r.raise_for_status()
            tmp = p.with_suffix(".tmp")
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(8192):
                    fh.write(chunk)
            os.replace(tmp, p)
        except Exception as exc:  # noqa: BLE001 — never crash a render
            logger.warning("cover fetch failed for %s: %s", url, exc)
            return None
    try:
        return Image.open(p).convert("RGB")
    except Exception as exc:  # noqa: BLE001 — corrupted file → drop
        logger.warning("cover decode failed for %s: %s", p, exc)
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
        return None
