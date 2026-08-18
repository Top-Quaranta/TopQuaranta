"""Guards for the master distribution switch + honest per-channel state
endpoint (2026-06-07).

- `social_toggle`: `channel=global` writes `distribucio_activa`; a missing
  channel now 400s (the old default-to-instagram footgun is gone).
- `social_estat_canals`: per-channel effective state + last send.
"""

from __future__ import annotations

import datetime

import pytest
from rest_framework.test import APIClient

from ranking.models import ConfiguracioGlobal
from social.models import SocialPost


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="master_switch_tester",
        email="ms@example.com",
        password="x",
        is_staff=True,
    )
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ── toggle endpoint ──────────────────────────────────────────────────


def test_toggle_global_writes_master(staff_client):
    cfg = ConfiguracioGlobal.load()
    assert cfg.distribucio_activa is True
    r = staff_client.post(
        "/api/v1/staff/social/toggle/",
        {"channel": "global", "actiu": False},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["distribucio_activa"] is False
    cfg.refresh_from_db()
    assert cfg.distribucio_activa is False


def test_toggle_missing_channel_is_400(staff_client):
    """The footgun is gone: no channel → 400, never a silent Instagram
    toggle."""
    before = ConfiguracioGlobal.load().instagram_actiu
    r = staff_client.post(
        "/api/v1/staff/social/toggle/", {"actiu": False}, format="json"
    )
    assert r.status_code == 400
    assert ConfiguracioGlobal.load().instagram_actiu == before  # untouched


def test_toggle_per_channel_still_works(staff_client):
    r = staff_client.post(
        "/api/v1/staff/social/toggle/",
        {"channel": "newsletter", "actiu": True},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["newsletter_actiu"] is True
    assert ConfiguracioGlobal.load().newsletter_actiu is True


# ── estat-canals endpoint ────────────────────────────────────────────


def _mk_post(platform, *, published, status=SocialPost.STATUS_PUBLICAT):
    return SocialPost.objects.create(
        platform=platform,
        tipus=SocialPost.TIPUS_TOP_PPCC,
        territori="PPCC",
        setmana=datetime.date(2026, 6, 1),
        status=status,
        published_at=published,
    )


def test_estat_canals_shapes_and_states(staff_client):
    cfg = ConfiguracioGlobal.load()
    cfg.distribucio_activa = True
    cfg.mastodon_actiu = True
    cfg.newsletter_actiu = False
    cfg.save()
    _mk_post(
        SocialPost.PLATFORM_MASTODON,
        published=datetime.datetime(2026, 6, 6, 9, 40, tzinfo=datetime.timezone.utc),
    )
    r = staff_client.get("/api/v1/staff/social/estat-canals/")
    assert r.status_code == 200, r.content
    canals = r.data["canals"]
    # Property: every known channel is reported (a superset is fine — a
    # new channel must not break this), each entry carries the honest
    # state fields, and the master/channel switches resolve as promised.
    assert {"instagram", "mastodon", "bluesky", "telegram", "newsletter", "rss"} <= set(
        canals
    )
    for entry in canals.values():
        assert {
            "efectiu",
            "mestre_actiu",
            "canal_actiu",
            "ultim_enviament",
            "font",
        } <= set(entry)
        assert entry["efectiu"] in {"actiu", "pausat_global", "pausat_canal"}
        assert entry["mestre_actiu"] is True
    assert canals["mastodon"]["efectiu"] == "actiu"
    assert canals["mastodon"]["canal_actiu"] is True
    assert canals["mastodon"]["ultim_enviament"].startswith("2026-06-06")
    assert canals["mastodon"]["font"] == "socialpost"
    assert canals["newsletter"]["efectiu"] == "pausat_canal"
    assert canals["newsletter"]["canal_actiu"] is False
    # RSS is pull-based: no send timestamp can exist.
    assert canals["rss"]["ultim_enviament"] is None
    assert canals["rss"]["font"] == "none"


def test_estat_canals_master_off_marks_all_global(staff_client):
    cfg = ConfiguracioGlobal.load()
    cfg.distribucio_activa = False
    cfg.mastodon_actiu = True  # channel on, but master off
    cfg.save()
    r = staff_client.get("/api/v1/staff/social/estat-canals/")
    assert r.status_code == 200, r.content
    canals = r.data["canals"]
    assert all(c["efectiu"] == "pausat_global" for c in canals.values())
    # raw channel switch still surfaced so the UI shows both reasons.
    assert canals["mastodon"]["canal_actiu"] is True
    assert canals["mastodon"]["mestre_actiu"] is False
