"""Shared helpers for the staff/social subpackage.

Serializers, credential payload builders, masking, and the PNG file
server. Public callables live in `accounts`, `posts`, `controls`."""

from __future__ import annotations

import datetime

from music.dates import project_week_number
from social.calendari import publication_date_for, upcoming_week
from social.models import (
    BlueskyAuth,
    InstagramAuth,
    MastodonAuth,
    SocialPost,
    TelegramAuth,
)

# User-facing label map. PPCC is the legacy code; visitors see
# "Global". Mirrors the convention used everywhere in the public SPA.
TERRITORI_LABEL = {
    "PPCC": "Global",
    "CAT": "Catalunya",
    "VAL": "País Valencià",
    "BAL": "Illes Balears",
    "AND": "Andorra",
    "CNO": "Catalunya del Nord",
    "FRA": "Franja de Ponent",
    "ALG": "L'Alguer",
    "ALT": "Altres",
    "": "—",
}


def _serialize(post: SocialPost) -> dict:
    # The publication day for this slot's tipus (Saturday for PPCC,
    # Wednesday/Monday for territorial, etc.). Surfaces in the UI as
    # the human-meaningful date — the operator thinks about "the
    # post of dissabte", not "the Monday of the ISO week".
    pub_date = publication_date_for(post.tipus, post.setmana)
    return {
        "pk": post.pk,
        "platform": post.platform,
        "tipus": post.tipus,
        "territori": post.territori,
        "territori_label": TERRITORI_LABEL.get(post.territori, post.territori or "—"),
        "setmana": post.setmana.isoformat(),
        "publication_date": pub_date.isoformat(),
        "project_week": project_week_number(pub_date),
        "status": post.status,
        "instagram_media_id": post.instagram_media_id or "",
        "error_msg": post.error_msg or "",
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "metadata": post.metadata or {},
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


_DAY_CA = [
    "dilluns",
    "dimarts",
    "dimecres",
    "dijous",
    "divendres",
    "dissabte",
    "diumenge",
]


def _calendari_payload() -> list[dict]:
    """One row per slot of the current ISO week, with the territori
    already resolved (so the operator knows ahead of time which top
    will go out)."""
    out = []
    for slot, ter, pub_date in upcoming_week():
        out.append(
            {
                "platform": slot.platform,
                "tipus": slot.tipus,
                "territori": ter,
                "territori_label": TERRITORI_LABEL.get(ter, ter or "—"),
                "min_fase": slot.min_fase,
                "weekday": slot.weekday,
                "weekday_name": _DAY_CA[slot.weekday],
                "publication_date": pub_date.isoformat(),
                "project_week": project_week_number(pub_date),
            }
        )
    return out


def _credentials_payload() -> dict:
    """Token info for the staff page. Never returns the full token
    string — only first/last 4 chars so an admin can verify which
    one is active without exposing it on screen."""
    row = InstagramAuth.load()
    if row and row.access_token:
        t = row.access_token
        return {
            "configured": True,
            "source": "db",
            "token_masked": f"{t[:4]}…{t[-4:]}",
            "instagram_user_id": row.instagram_user_id,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by.username if row.updated_by else None,
        }
    # Fallback: env-based credentials (dev / first-boot).
    from django.conf import settings as _s

    env_token = (getattr(_s, "INSTAGRAM_ACCESS_TOKEN", "") or "").strip()
    if env_token and env_token != "test":
        return {
            "configured": True,
            "source": "env",
            "token_masked": f"{env_token[:4]}…{env_token[-4:]}",
            "instagram_user_id": getattr(_s, "INSTAGRAM_USER_ID", "") or "",
            "expires_at": getattr(_s, "INSTAGRAM_TOKEN_EXPIRES_AT", "") or None,
            "updated_at": None,
            "updated_by": None,
        }
    return {
        "configured": False,
        "source": None,
        "token_masked": "",
        "instagram_user_id": "",
        "expires_at": None,
        "updated_at": None,
        "updated_by": None,
    }


def _mask(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "…" * len(secret)
    return f"{secret[:4]}…{secret[-4:]}"


def _mastodon_payload() -> dict:
    row = MastodonAuth.load()
    if row and row.access_token:
        return {
            "configured": True,
            "instance_url": row.instance_url,
            "handle": row.handle,
            "token_masked": _mask(row.access_token),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by.username if row.updated_by else None,
        }
    return {
        "configured": False,
        "instance_url": "",
        "handle": "",
        "token_masked": "",
        "updated_at": None,
        "updated_by": None,
    }


def _telegram_payload() -> dict:
    row = TelegramAuth.load()
    if row and row.bot_token and row.chat_id:
        return {
            "configured": True,
            "chat_id": row.chat_id,
            "bot_username": row.bot_username,
            "token_masked": _mask(row.bot_token),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by.username if row.updated_by else None,
        }
    return {
        "configured": False,
        "chat_id": "",
        "bot_username": "",
        "token_masked": "",
        "updated_at": None,
        "updated_by": None,
    }


def _bluesky_payload() -> dict:
    row = BlueskyAuth.load()
    if row and row.app_password:
        return {
            "configured": True,
            "handle": row.handle,
            "did": row.did,
            "password_masked": _mask(row.app_password),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by.username if row.updated_by else None,
        }
    return {
        "configured": False,
        "handle": "",
        "did": "",
        "password_masked": "",
        "updated_at": None,
        "updated_by": None,
    }


def _serve_png(filename: str):
    """Shared file-serving helper used by both the staff-only
    endpoint and the public one Meta needs to fetch PNGs from."""
    import re
    from pathlib import Path

    from django.conf import settings as _s
    from django.http import FileResponse, Http404

    if not re.fullmatch(r"[A-Za-z0-9_.\-]+\.png", filename):
        raise Http404()
    base = Path(getattr(_s, "SOCIAL_CACHE_DIR", "/tmp/tq_social")) / "renders"
    candidate = base / filename
    if not candidate.exists():
        candidate = Path("/tmp/tq_social/renders") / filename
    if not candidate.exists() or not candidate.is_file():
        raise Http404()
    resp = FileResponse(open(candidate, "rb"), content_type="image/png")
    # Tell intermediaries (and Meta's fetcher) it's safe to cache.
    resp["Cache-Control"] = "public, max-age=86400"
    return resp
