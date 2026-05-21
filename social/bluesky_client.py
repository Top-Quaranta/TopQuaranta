"""Tiny Bluesky (AT Protocol) client for posting cover images + text.

Auth flow:
  1. POST /xrpc/com.atproto.server.createSession with handle +
     app_password → returns accessJwt + refreshJwt.
  2. Upload images via /xrpc/com.atproto.repo.uploadBlob.
  3. Create a feed post via /xrpc/com.atproto.repo.createRecord with
     collection=app.bsky.feed.post, embed=app.bsky.embed.images.

We don't use the official `atproto` Python SDK because the surface
we need is small (3 endpoints) and the SDK pulls in a heavy
protobuf stack. The session JWT is cached in process memory for
the lifetime of one cron run; we don't persist it.
"""

from __future__ import annotations

import datetime
import logging
import time
from pathlib import Path

import requests

from social.constants import (
    BLUESKY_UPLOAD_BACKOFF_S,
    BLUESKY_UPLOAD_RETRIES,
    BLUESKY_UPLOAD_TIMEOUT_S,
    HTTP_TIMEOUT_S as TIMEOUT_S,
)
from social.models import BlueskyAuth

logger = logging.getLogger(__name__)

PDS_BASE = "https://bsky.social"

# Process-local session cache keyed by handle (so two consecutive
# posts in the same cron run share one login).
_SESSIONS: dict[str, dict] = {}


def _row() -> BlueskyAuth | None:
    return BlueskyAuth.load()


def is_dry_run() -> bool:
    row = _row()
    return not (row and row.handle and row.app_password)


def _session() -> dict:
    """Return a cached `{accessJwt, refreshJwt, did}` dict."""
    row = _row()
    cached = _SESSIONS.get(row.handle)
    if cached:
        return cached
    r = requests.post(
        f"{PDS_BASE}/xrpc/com.atproto.server.createSession",
        json={"identifier": row.handle, "password": row.app_password},
        timeout=TIMEOUT_S,
    )
    if not r.ok:
        raise RuntimeError(f"Bluesky createSession {r.status_code}: {r.text[:300]}")
    body = r.json()
    sess = {
        "accessJwt": body["accessJwt"],
        "refreshJwt": body["refreshJwt"],
        "did": body["did"],
    }
    _SESSIONS[row.handle] = sess
    # Persist the DID for record (does not change between sessions).
    if row.did != sess["did"]:
        row.did = sess["did"]
        row.save(update_fields=["did", "updated_at"])
    return sess


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_session()['accessJwt']}"}


def upload_blob(image_path: Path) -> dict:
    """Upload an image. Returns the AT Proto blob ref dict.

    Retry policy (ADR-0005): up to BLUESKY_UPLOAD_RETRIES attempts
    with back-off between them, only for transient network failures
    (`ReadTimeout`, `ConnectionError`). HTTP 4xx responses (auth,
    payload errors) are NOT retried — those won't fix themselves.
    """
    if is_dry_run():
        return {
            "$type": "blob",
            "ref": {"$link": "dry-blob"},
            "mimeType": "image/png",
            "size": 1,
        }
    with image_path.open("rb") as fh:
        data = fh.read()

    last_exc: Exception | None = None
    for attempt in range(1, BLUESKY_UPLOAD_RETRIES + 1):
        try:
            r = requests.post(
                f"{PDS_BASE}/xrpc/com.atproto.repo.uploadBlob",
                data=data,
                headers={**_auth_headers(), "Content-Type": "image/png"},
                timeout=BLUESKY_UPLOAD_TIMEOUT_S,
            )
        except (requests.ReadTimeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt >= BLUESKY_UPLOAD_RETRIES:
                logger.warning(
                    "Bluesky uploadBlob exhausted retries (%d/%d): %s",
                    attempt,
                    BLUESKY_UPLOAD_RETRIES,
                    exc,
                )
                raise
            backoff = BLUESKY_UPLOAD_BACKOFF_S[
                min(attempt - 1, len(BLUESKY_UPLOAD_BACKOFF_S) - 1)
            ]
            logger.info(
                "Bluesky uploadBlob attempt %d failed (%s); retrying in %ds",
                attempt,
                type(exc).__name__,
                backoff,
            )
            time.sleep(backoff)
            continue
        if not r.ok:
            # 4xx / 5xx — don't retry; the response carries actionable
            # info (auth expired, payload rejected, etc.).
            raise RuntimeError(
                f"Bluesky uploadBlob {r.status_code}: {r.text[:300]}"
            )
        return r.json()["blob"]

    # Unreachable in practice (the loop either returns or raises),
    # but quiets the linter.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Bluesky uploadBlob: unknown failure")


def create_post(
    text: str, image_blobs: list[dict] | None = None, alt_texts: list[str] | None = None
) -> str:
    """Post a feed item. Returns the AT URI of the created record."""
    if is_dry_run():
        return f"at://dry/post/{abs(hash(text)) & 0xffff:04x}"
    sess = _session()
    record = {
        "$type": "app.bsky.feed.post",
        "text": text[:300],
        "createdAt": datetime.datetime.utcnow().isoformat() + "Z",
        "langs": ["ca"],
    }
    if image_blobs:
        alt_texts = alt_texts or []
        record["embed"] = {
            "$type": "app.bsky.embed.images",
            "images": [
                {
                    "alt": (alt_texts[i] if i < len(alt_texts) else "")[:300],
                    "image": blob,
                }
                # Bluesky caps embed images at 4 per post.
                for i, blob in enumerate(image_blobs[:4])
            ],
        }
    body = {
        "repo": sess["did"],
        "collection": "app.bsky.feed.post",
        "record": record,
    }
    r = requests.post(
        f"{PDS_BASE}/xrpc/com.atproto.repo.createRecord",
        json=body,
        headers=_auth_headers(),
        timeout=TIMEOUT_S,
    )
    if not r.ok:
        raise RuntimeError(f"Bluesky createRecord {r.status_code}: {r.text[:300]}")
    return r.json().get("uri", "")


def delete_post(at_uri: str) -> tuple[bool, str]:
    """Delete a previously-created feed post.

    `at_uri` is the AT URI returned by `create_post`, formatted as
    `at://{did}/{collection}/{rkey}`. We parse the rkey and call
    `com.atproto.repo.deleteRecord`. Returns `(ok, message)`.
    """
    if is_dry_run():
        return True, "DRY-RUN: no es crida l'API de Bluesky"
    if not at_uri.startswith("at://"):
        return False, f"AT URI invàlid: {at_uri}"
    parts = at_uri[len("at://") :].split("/")
    if len(parts) != 3:
        return False, f"AT URI no parsejable: {at_uri}"
    repo, collection, rkey = parts
    r = requests.post(
        f"{PDS_BASE}/xrpc/com.atproto.repo.deleteRecord",
        json={"repo": repo, "collection": collection, "rkey": rkey},
        headers=_auth_headers(),
        timeout=TIMEOUT_S,
    )
    if not r.ok:
        return False, f"Bluesky deleteRecord {r.status_code}: {r.text[:300]}"
    return True, f"deleteRecord {rkey} → 200 OK"


def get_post_metrics(at_uri: str) -> dict:
    """Fetch engagement counters for a single feed post.

    Uses `app.bsky.feed.getPosts?uris=...` (a single API call returns
    full counts for up to 25 URIs). For our case we ask one at a
    time so the cron stays trivially restartable per row. Returns
    `{likes, shares, replies, raw}` with quote/repost merged into
    `shares` to keep the cross-platform schema flat.
    """
    if is_dry_run():
        return {"likes": 0, "shares": 0, "replies": 0, "raw": {"dry_run": True}}
    if not at_uri or not at_uri.startswith("at://"):
        return {"likes": 0, "shares": 0, "replies": 0, "raw": {"error": "bad_uri"}}
    r = requests.get(
        f"{PDS_BASE}/xrpc/app.bsky.feed.getPosts",
        params={"uris": at_uri},
        headers=_auth_headers(),
        timeout=TIMEOUT_S,
    )
    if not r.ok:
        return {
            "likes": 0,
            "shares": 0,
            "replies": 0,
            "raw": {"http_status": r.status_code, "body": r.text[:300]},
        }
    posts = (r.json() or {}).get("posts") or []
    if not posts:
        return {"likes": 0, "shares": 0, "replies": 0, "raw": {"empty": True}}
    p = posts[0]
    # Quotes and reposts both signal "amplification" — merge so the
    # `shares` column has the same meaning as a Mastodon reblog.
    shares = int(p.get("repostCount") or 0) + int(p.get("quoteCount") or 0)
    return {
        "likes": int(p.get("likeCount") or 0),
        "shares": shares,
        "replies": int(p.get("replyCount") or 0),
        "raw": p,
    }


def get_account_stats() -> dict:
    """Snapshot of the account's followers / follows / posts."""
    if is_dry_run():
        return {
            "followers": 0,
            "following": 0,
            "posts_total": 0,
            "raw": {"dry_run": True},
        }
    handle = _row().handle
    r = requests.get(
        f"{PDS_BASE}/xrpc/app.bsky.actor.getProfile",
        params={"actor": handle},
        headers=_auth_headers(),
        timeout=TIMEOUT_S,
    )
    if not r.ok:
        return {
            "followers": 0,
            "following": 0,
            "posts_total": 0,
            "raw": {"http_status": r.status_code, "body": r.text[:300]},
        }
    body = r.json()
    return {
        "followers": int(body.get("followersCount") or 0),
        "following": int(body.get("followsCount") or 0),
        "posts_total": int(body.get("postsCount") or 0),
        "raw": body,
    }


def whoami() -> dict:
    """Lightweight credential check. Returns the resolved DID."""
    if is_dry_run():
        return {"dry_run": True}
    sess = _session()
    return {"handle": _row().handle, "did": sess["did"]}
