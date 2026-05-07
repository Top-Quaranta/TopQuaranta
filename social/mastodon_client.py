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

from social.constants import HTTP_TIMEOUT_S as TIMEOUT_S
from social.models import MastodonAuth

logger = logging.getLogger(__name__)


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


def delete_status(status_id_or_url: str) -> tuple[bool, str]:
    """Delete a previously-toot'd status.

    Accepts either a bare numeric id or the full status URL — the
    latter has the id as its trailing path component on every major
    Mastodon flavour. Returns `(ok, message)`.
    """
    if is_dry_run():
        return True, "DRY-RUN: no es crida l'API de Mastodon"
    sid = status_id_or_url.rstrip("/").rsplit("/", 1)[-1]
    if not sid.isdigit():
        return False, f"id de status no parsejable: {status_id_or_url}"
    r = requests.delete(
        f"{_base()}/api/v1/statuses/{sid}",
        headers=_headers(),
        timeout=TIMEOUT_S,
    )
    if not r.ok:
        return False, f"Mastodon DELETE /statuses/{sid} {r.status_code}: {r.text[:300]}"
    return True, f"DELETE /statuses/{sid} → 200 OK"


def get_status_metrics(status_id_or_url: str) -> dict:
    """Fetch engagement counters for a previously-toot'd status.

    Mastodon's `/api/v1/statuses/:id` returns `favourites_count`,
    `reblogs_count` and `replies_count` on every status, no scope
    needed beyond the basic read access the app token already has.
    Returns the lowest-common-denominator dict the analytics
    pipeline expects: `{likes, shares, replies, raw}`.
    """
    if is_dry_run():
        return {"likes": 0, "shares": 0, "replies": 0, "raw": {"dry_run": True}}
    sid = (status_id_or_url or "").rstrip("/").rsplit("/", 1)[-1]
    if not sid.isdigit():
        return {"likes": 0, "shares": 0, "replies": 0, "raw": {"error": "bad_id"}}
    r = requests.get(
        f"{_base()}/api/v1/statuses/{sid}",
        headers=_headers(),
        timeout=TIMEOUT_S,
    )
    if not r.ok:
        return {
            "likes": 0,
            "shares": 0,
            "replies": 0,
            "raw": {"http_status": r.status_code, "body": r.text[:300]},
        }
    body = r.json()
    return {
        "likes": int(body.get("favourites_count") or 0),
        "shares": int(body.get("reblogs_count") or 0),
        "replies": int(body.get("replies_count") or 0),
        "raw": body,
    }


def get_account_stats() -> dict:
    """Snapshot of account-level counters (followers, posts, etc.)."""
    if is_dry_run():
        return {
            "followers": 0,
            "following": 0,
            "posts_total": 0,
            "raw": {"dry_run": True},
        }
    body = whoami()
    return {
        "followers": int(body.get("followers_count") or 0),
        "following": int(body.get("following_count") or 0),
        "posts_total": int(body.get("statuses_count") or 0),
        "raw": body,
    }


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
