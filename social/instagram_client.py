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


def _get(path: str, params: dict | None = None) -> dict:
    """Live GET; raises on non-200."""
    import requests

    p = {**(params or {}), "access_token": _token()}
    r = requests.get(f"{GRAPH_BASE}/{path}", params=p, timeout=30)
    if not r.ok:
        raise RuntimeError(f"IG API {r.status_code}: {r.text[:300]}")
    return r.json()


def wait_until_finished(
    container_id: str, *, timeout_s: int = 90, interval_s: float = 2.0
) -> None:
    """Block until the container reaches `FINISHED` status.

    Required before `publish_container` for both single-image and
    carousel posts — Meta processes uploads asynchronously and
    refuses to publish a container that's still IN_PROGRESS or
    PUBLISHED. Caught 2026-04-27 with code 9007 / subcode 2207027
    ("Media ID is not available") on the very first real publish.

    Raises `RuntimeError` if the status reaches `ERROR` or if the
    timeout elapses without ever seeing `FINISHED`.
    """
    if is_dry_run():
        return
    deadline = time.time() + timeout_s
    last_status = "?"
    while time.time() < deadline:
        body = _get(container_id, {"fields": "status_code,status"})
        last_status = body.get("status_code") or last_status
        if last_status == "FINISHED":
            logger.info("container %s ready", container_id)
            return
        if last_status == "ERROR":
            raise RuntimeError(
                f"IG container {container_id} entered ERROR state: "
                f"{body.get('status', '')[:300]}"
            )
        time.sleep(interval_s)
    raise RuntimeError(
        f"IG container {container_id} not FINISHED after {timeout_s}s "
        f"(last status: {last_status})"
    )


# ── Public surface ──────────────────────────────────────────────────


def upload_carousel_item(
    image_url: str,
    *,
    user_tags: list[dict] | None = None,
    alt_text: str | None = None,
) -> str:
    """Upload one image as a carousel child. Returns container ID.

    `user_tags` is the Meta `user_tags` payload — a list of
    `{"username": str, "x": float, "y": float}` (coordinates 0..1).
    Capped at 20 per image by Meta. We don't validate locally; the
    API will reject invalid handles silently (untagged) or raise.

    `alt_text` is the per-image accessibility label (Meta's
    `alt_text` field, capped at 1 000 chars). Surfaced to screen
    readers on Instagram. We already do this for Mastodon/Bluesky
    — IG was the last channel without it.
    """
    if is_dry_run():
        cid = f"dry-item-{int(time.time()*1000)}-{abs(hash(image_url)) & 0xffff:04x}"
        logger.info(
            "[DRY] upload_carousel_item %s tags=%d alt=%dch → %s",
            image_url,
            len(user_tags or []),
            len(alt_text or ""),
            cid,
        )
        return cid
    body = {
        "image_url": image_url,
        "is_carousel_item": "true",
    }
    if user_tags:
        import json

        body["user_tags"] = json.dumps(user_tags[:20])
    if alt_text:
        body["alt_text"] = alt_text[:1000]
    return _post(f"{_user_id()}/media", body)["id"]


def create_carousel(
    child_ids: list[str], caption: str, *, collaborators: list[str] | None = None
) -> str:
    """Create the parent carousel container. Returns its ID.

    `collaborators` is Meta's `collaborators` field — up to 3 IG
    usernames invited as co-authors (the post lands on their grid once
    they accept). Feed/reels/carousels only. Omitted entirely when falsy,
    so the byte-for-byte payload is unchanged for the (default) no-collab
    path. See ADR-0015."""
    if is_dry_run():
        cid = f"dry-carousel-{int(time.time()*1000)}"
        logger.info(
            "[DRY] create_carousel children=%d collab=%d → %s",
            len(child_ids),
            len(collaborators or []),
            cid,
        )
        return cid
    body = {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption[:2200],
    }
    if collaborators:
        import json

        body["collaborators"] = json.dumps(collaborators[:3])
    return _post(f"{_user_id()}/media", body)["id"]


def upload_image(
    image_url: str,
    caption: str,
    *,
    user_tags: list[dict] | None = None,
    alt_text: str | None = None,
    collaborators: list[str] | None = None,
) -> str:
    """Single-image feed post. Returns container ID.

    `alt_text` is the per-image accessibility label (Meta's `alt_text`
    field, capped at 1 000 chars). `collaborators` — up to 3 IG usernames
    invited as co-authors (see `create_carousel`); omitted when falsy so
    the no-collab payload is unchanged.
    """
    if is_dry_run():
        cid = f"dry-image-{int(time.time()*1000)}"
        logger.info(
            "[DRY] upload_image %s tags=%d alt=%dch collab=%d → %s",
            image_url,
            len(user_tags or []),
            len(alt_text or ""),
            len(collaborators or []),
            cid,
        )
        return cid
    body = {"image_url": image_url, "caption": caption[:2200]}
    if user_tags:
        import json

        body["user_tags"] = json.dumps(user_tags[:20])
    if alt_text:
        body["alt_text"] = alt_text[:1000]
    if collaborators:
        import json

        body["collaborators"] = json.dumps(collaborators[:3])
    return _post(f"{_user_id()}/media", body)["id"]


def upload_story(image_url: str, *, user_tags: list[dict] | None = None) -> str:
    """Story (image, no caption). Returns container ID.

    `user_tags` — Meta `user_tags` payload (stories accept mentions
    since 2025-07-09; NO collaborators/product tags — feed only).
    Omitted when falsy so the no-mention payload is unchanged.
    """
    if is_dry_run():
        cid = f"dry-story-{int(time.time()*1000)}-{abs(hash(image_url)) & 0xffff:04x}"
        logger.info(
            "[DRY] upload_story %s tags=%d → %s",
            image_url,
            len(user_tags or []),
            cid,
        )
        return cid
    body = {"image_url": image_url, "media_type": "STORIES"}
    if user_tags:
        import json

        body["user_tags"] = json.dumps(user_tags[:20])
    return _post(f"{_user_id()}/media", body)["id"]


def publish_container(container_id: str) -> str:
    """Publish a media container. Returns the final media ID."""
    if is_dry_run():
        mid = f"dry-published-{int(time.time()*1000)}"
        logger.info("[DRY] publish_container %s → %s", container_id, mid)
        return mid
    return _post(f"{_user_id()}/media_publish", {"creation_id": container_id})["id"]


def get_post_metrics(media_id: str, *, is_story: bool = False) -> dict:
    """Fetch insights for a published media (feed or story).

    Uses the Graph API `{media-id}/insights?metric=...` endpoint.
    Required permission: `instagram_manage_insights` — already granted
    on the long-lived token we use for publishing. Story insights
    expire ~24 h after the story ends; we still try and degrade
    gracefully on the inevitable 400 once the window is over.

    Returns the lowest-common-denominator dict
    `{likes, replies, shares, reach, impressions, raw}`.
    """
    if is_dry_run():
        return {
            "likes": 0,
            "replies": 0,
            "shares": 0,
            "reach": 0,
            "impressions": 0,
            "raw": {"dry_run": True},
        }
    if not media_id:
        return {
            "likes": 0,
            "replies": 0,
            "shares": 0,
            "reach": 0,
            "impressions": 0,
            "raw": {"error": "missing_media_id"},
        }
    # Story insights expose a smaller set; feed posts get the full
    # bundle. Total interactions is a Meta-side rollup (likes +
    # comments + shares + saves) — we keep `likes` separate but
    # still log it raw for the UI.
    # Meta deprecated `impressions` for some media product types
    # in 2024 — IG returns 400 for the *whole* call if any single
    # metric isn't supported. Try the rich set first; on failure
    # retry with the safe core that's supported on every type.
    if is_story:
        attempts = [
            "reach,replies,impressions",
            "reach,replies",
        ]
    else:
        attempts = [
            "likes,comments,shares,saved,reach,impressions,total_interactions",
            "likes,comments,shares,saved,reach,total_interactions",
            "likes,comments,shares,reach",
        ]
    body: dict = {}
    last_err: str | None = None
    for metric_set in attempts:
        try:
            body = _get(f"{media_id}/insights", {"metric": metric_set})
            break
        except RuntimeError as exc:
            last_err = str(exc)[:300]
            continue
    else:
        return {
            "likes": 0,
            "replies": 0,
            "shares": 0,
            "reach": 0,
            "impressions": 0,
            "raw": {"error": last_err},
        }
    flat: dict[str, int] = {}
    for entry in body.get("data") or []:
        name = entry.get("name")
        values = entry.get("values") or [{}]
        flat[name] = int(values[0].get("value") or 0)
    return {
        "likes": flat.get("likes", 0),
        # Stories have `replies`; feed posts get `comments`. Map
        # both into the same column so the dashboard doesn't have
        # to special-case stories.
        "replies": flat.get("replies", flat.get("comments", 0)),
        "shares": flat.get("shares", 0),
        "reach": flat.get("reach", 0),
        "impressions": flat.get("impressions", 0),
        "raw": body,
    }


# NOTE: there is deliberately no `get_collaborators` here. Reading
# invite acceptance programmatically is unviable with this app's API
# flavour (ADR-0015 §5.5, verified 2026-07-13): Instagram Login lacks
# the `/collaborators` edge, and a Facebook-Login user token returns
# it empty for pending invitations. Acceptances are marked manually
# from the staff social panel.


def get_account_stats() -> dict:
    """Snapshot of follower + media counts for the IG business account."""
    if is_dry_run():
        return {
            "followers": 0,
            "posts_total": 0,
            "raw": {"dry_run": True},
        }
    try:
        body = _get(_user_id(), {"fields": "followers_count,media_count"})
    except RuntimeError as exc:
        return {
            "followers": 0,
            "posts_total": 0,
            "raw": {"error": str(exc)[:300]},
        }
    return {
        "followers": int(body.get("followers_count") or 0),
        "posts_total": int(body.get("media_count") or 0),
        "raw": body,
    }


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
