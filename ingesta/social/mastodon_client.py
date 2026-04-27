"""Tiny Mastodon REST client for posting cover images + captions.

We don't depend on `Mastodon.py` because:
  * The publishing flow needs only two endpoints (media + status),
    so the wrapper would add more surface than it saves.
  * Single-channel deps are easier to audit than a 1k-LOC library.

Auth: a permanent app access token created at the Mastodon
instance's settings → Development → New Application. Required
scopes: `write:media`, `write:statuses`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from social.models import MastodonAuth

logger = logging.getLogger(__name__)

# 60 s covers a slow toot upload comfortably without hanging the
# cron longer than necessary.
TIMEOUT_S = 60


def _row() -> MastodonAuth | None:
    return MastodonAuth.load()


def is_dry_run() -> bool:
    row = _row()
    return not (row and row.access_token and row.instance_url)


def _base() -> str:
    return _row().instance_url.rstrip("/")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_row().access_token}"}


def upload_media(image_path: Path, alt_text: str = "") -> str:
    """Upload an image to /api/v2/media. Returns the media ID."""
    if is_dry_run():
        return f"dry-mst-{abs(hash(str(image_path))) & 0xffff:04x}"
    with image_path.open("rb") as fh:
        r = requests.post(
            f"{_base()}/api/v2/media",
            headers=_headers(),
            files={"file": (image_path.name, fh, "image/png")},
            data={"description": alt_text[:1500]} if alt_text else None,
            timeout=TIMEOUT_S,
        )
    if not r.ok:
        raise RuntimeError(f"Mastodon /media {r.status_code}: {r.text[:300]}")
    return r.json()["id"]


def post_status(text: str, media_ids: list[str] | None = None) -> str:
    """Post a status. Returns the status URL (perma-link)."""
    if is_dry_run():
        return f"https://example.invalid/dry-toot-{abs(hash(text)) & 0xffff:04x}"
    body = {
        "status": text[:500],
        "visibility": "public",
        "language": "ca",
    }
    if media_ids:
        # `media_ids[]` is the form-encoded list shape Mastodon expects.
        body["media_ids[]"] = media_ids[:4]  # Mastodon caps at 4
    r = requests.post(
        f"{_base()}/api/v1/statuses",
        headers=_headers(),
        data=body,
        timeout=TIMEOUT_S,
    )
    if not r.ok:
        raise RuntimeError(f"Mastodon /statuses {r.status_code}: {r.text[:300]}")
    return r.json().get("url") or r.json().get("uri") or ""


def whoami() -> dict:
    """Lightweight credential check. Returns the verify_credentials
    payload (id, username, acct, display_name)."""
    if is_dry_run():
        return {"dry_run": True}
    r = requests.get(
        f"{_base()}/api/v1/accounts/verify_credentials",
        headers=_headers(),
        timeout=TIMEOUT_S,
    )
    if not r.ok:
        raise RuntimeError(f"Mastodon verify {r.status_code}: {r.text[:300]}")
    return r.json()
