"""Thin wrapper around the Instagram Graph API.

The two publishing flows we use:

  Single image / story
    1. POST /<IG_USER_ID>/media          → returns a `creation_id`
    2. POST /<IG_USER_ID>/media_publish  → publishes the container,
                                            returns the final `media_id`

  Carousel
    1. For each item, POST /<IG_USER_ID>/media with `is_carousel_item=true`
    2. POST /<IG_USER_ID>/media with `media_type=CAROUSEL`,
       `children=[id, id, ...]`, optionally a `caption`
    3. POST /<IG_USER_ID>/media_publish with the carousel container

Each "media" call requires the image to be reachable at a public
URL. We expose `<SOCIAL_CACHE_DIR>/renders/` via Caddy at
`/static/social/<basename>.png` so Meta can fetch it.

DRY_RUN
-------
When `INSTAGRAM_ACCESS_TOKEN` is empty or "test", every call is
simulated: returns synthetic IDs, logs what *would* have happened,
no network. The publication command's output remains identical so
staff can preview.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from django.conf import settings

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.instagram.com/v19.0"
LONG_LIVED_TTL_DAYS = 60


def _auth_row():
    """Lazily fetch the singleton InstagramAuth row. Lazy import so
    this module stays importable before Django apps are ready."""
    try:
        from social.models import InstagramAuth

        return InstagramAuth.load()
    except Exception:
        return None


def _token() -> str:
    """DB row first; .env settings as fallback."""
    row = _auth_row()
    if row and row.access_token:
        return row.access_token
    return getattr(settings, "INSTAGRAM_ACCESS_TOKEN", "") or ""


def _user_id() -> str:
    row = _auth_row()
    if row and row.instagram_user_id:
        return row.instagram_user_id
    return getattr(settings, "INSTAGRAM_USER_ID", "") or "DRY_USER"


def is_dry_run() -> bool:
    token = (_token() or "").strip()
    return token in ("", "test")


def _post(path: str, params: dict) -> dict:
    """Live POST; raises on non-200."""
    import requests

    params = {**params, "access_token": _token()}
    r = requests.post(f"{GRAPH_BASE}/{path}", data=params, timeout=30)
    if not r.ok:
        raise RuntimeError(f"IG API {r.status_code}: {r.text[:300]}")
    return r.json()


# ── Public surface ──────────────────────────────────────────────────


def upload_carousel_item(image_url: str) -> str:
    """Upload one image as a carousel child. Returns container ID."""
    if is_dry_run():
        cid = f"dry-item-{int(time.time()*1000)}-{abs(hash(image_url)) & 0xffff:04x}"
        logger.info("[DRY] upload_carousel_item %s → %s", image_url, cid)
        return cid
    body = {
        "image_url": image_url,
        "is_carousel_item": "true",
    }
    return _post(f"{_user_id()}/media", body)["id"]


def create_carousel(child_ids: list[str], caption: str) -> str:
    """Create the parent carousel container. Returns its ID."""
    if is_dry_run():
        cid = f"dry-carousel-{int(time.time()*1000)}"
        logger.info("[DRY] create_carousel children=%d → %s", len(child_ids), cid)
        return cid
    body = {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption[:2200],
    }
    return _post(f"{_user_id()}/media", body)["id"]


def upload_image(image_url: str, caption: str) -> str:
    """Single-image feed post. Returns container ID."""
    if is_dry_run():
        cid = f"dry-image-{int(time.time()*1000)}"
        logger.info("[DRY] upload_image %s → %s", image_url, cid)
        return cid
    body = {"image_url": image_url, "caption": caption[:2200]}
    return _post(f"{_user_id()}/media", body)["id"]


def upload_story(image_url: str) -> str:
    """Story (image, no caption). Returns container ID."""
    if is_dry_run():
        cid = f"dry-story-{int(time.time()*1000)}-{abs(hash(image_url)) & 0xffff:04x}"
        logger.info("[DRY] upload_story %s → %s", image_url, cid)
        return cid
    body = {"image_url": image_url, "media_type": "STORIES"}
    return _post(f"{_user_id()}/media", body)["id"]


def publish_container(container_id: str) -> str:
    """Publish a media container. Returns the final media ID."""
    if is_dry_run():
        mid = f"dry-published-{int(time.time()*1000)}"
        logger.info("[DRY] publish_container %s → %s", container_id, mid)
        return mid
    return _post(f"{_user_id()}/media_publish", {"creation_id": container_id})["id"]


def refresh_token() -> tuple[str, datetime]:
    """Refresh the long-lived token. Returns (new_token, new_expiry).

    Caller writes the new values back to .env and updates Django
    settings on the next reload."""
    if is_dry_run():
        logger.info("[DRY] refresh_token (no-op)")
        return _token(), datetime.now(timezone.utc) + timedelta(
            days=LONG_LIVED_TTL_DAYS
        )
    import requests

    r = requests.get(
        f"{GRAPH_BASE}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": _token()},
        timeout=20,
    )
    if not r.ok:
        raise RuntimeError(f"refresh_token: {r.status_code} {r.text[:300]}")
    body = r.json()
    new_token = body["access_token"]
    expires_in = int(body.get("expires_in", 60 * 86400))
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return new_token, expiry


def days_until_expiry() -> int | None:
    """How many days remain on the current token. None when unknown
    or DRY_RUN. Used by tq-health alerting."""
    if is_dry_run():
        return None
    # Prefer the DB row (refreshed in-place by the renew command); fall
    # back to settings string if the DB doesn't yet hold an expiry.
    row = _auth_row()
    if row and row.expires_at:
        delta = row.expires_at - datetime.now(timezone.utc)
        return delta.days
    raw = getattr(settings, "INSTAGRAM_TOKEN_EXPIRES_AT", "") or ""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = dt - datetime.now(timezone.utc)
        return delta.days
    except ValueError:
        return None
