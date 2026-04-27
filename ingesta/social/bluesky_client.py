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
from pathlib import Path

import requests

from social.models import BlueskyAuth

logger = logging.getLogger(__name__)

PDS_BASE = "https://bsky.social"
TIMEOUT_S = 60

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
    """Upload an image. Returns the AT Proto blob ref dict."""
    if is_dry_run():
        return {
            "$type": "blob",
            "ref": {"$link": "dry-blob"},
            "mimeType": "image/png",
            "size": 1,
        }
    with image_path.open("rb") as fh:
        r = requests.post(
            f"{PDS_BASE}/xrpc/com.atproto.repo.uploadBlob",
            data=fh.read(),
            headers={**_auth_headers(), "Content-Type": "image/png"},
            timeout=TIMEOUT_S,
        )
    if not r.ok:
        raise RuntimeError(f"Bluesky uploadBlob {r.status_code}: {r.text[:300]}")
    return r.json()["blob"]


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


def whoami() -> dict:
    """Lightweight credential check. Returns the resolved DID."""
    if is_dry_run():
        return {"dry_run": True}
    sess = _session()
    return {"handle": _row().handle, "did": sess["did"]}
