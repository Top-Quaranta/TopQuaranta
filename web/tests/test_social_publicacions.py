"""Guards for the unified publications endpoint (distribution-views
llesca 2, 2026-06-08).

- `social_list`: filters (canal / estat / tipus / setmana) + free-text
  search + sort + pagination, and the row serializer's clickable-URL
  contract.
- A no-N+1 guard: the query count must NOT scale with the number of
  rows on the page.
"""

from __future__ import annotations

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from social.models import SocialPost
from web.api.staff.social._common import _public_url, _serialize

MONDAY = datetime.date(2026, 6, 1)
PREV_MONDAY = datetime.date(2026, 5, 25)


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="publicacions_tester",
        email="pub@example.com",
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


def _mk(platform, tipus, territori, setmana, status):
    return SocialPost.objects.create(
        platform=platform,
        tipus=tipus,
        territori=territori,
        setmana=setmana,
        status=status,
    )


@pytest.fixture
def sample_posts(db):
    return [
        _mk("mastodon", "top_ppcc", "", MONDAY, SocialPost.STATUS_PUBLICAT),
        _mk("bluesky", "top_ppcc", "", MONDAY, SocialPost.STATUS_ERROR),
        _mk("telegram", "top_territorial", "VAL", MONDAY, SocialPost.STATUS_PUBLICAT),
        _mk("instagram_feed", "top_ppcc", "", PREV_MONDAY, SocialPost.STATUS_PUBLICAT),
        _mk("instagram_story", "top_ppcc", "", PREV_MONDAY, SocialPost.STATUS_PENDENT),
    ]


# ── filters ──────────────────────────────────────────────────────────


def test_canal_filter_spans_instagram_platforms(staff_client, sample_posts):
    r = staff_client.get("/api/v1/staff/social/?canal=instagram")
    assert r.status_code == 200, r.content
    plats = {row["platform"] for row in r.data["results"]}
    assert plats == {"instagram_feed", "instagram_story"}


def test_estat_and_tipus_and_setmana_filters(staff_client, sample_posts):
    r = staff_client.get("/api/v1/staff/social/?estat=publicat")
    assert {row["status"] for row in r.data["results"]} == {"publicat"}

    r = staff_client.get("/api/v1/staff/social/?tipus=top_territorial")
    assert {row["tipus"] for row in r.data["results"]} == {"top_territorial"}

    r = staff_client.get(f"/api/v1/staff/social/?setmana={MONDAY.isoformat()}")
    assert {row["setmana"] for row in r.data["results"]} == {MONDAY.isoformat()}
    assert r.data["total"] == 3


def test_search_matches_platform_or_territori(staff_client, sample_posts):
    r = staff_client.get("/api/v1/staff/social/?q=telegram")
    assert [row["platform"] for row in r.data["results"]] == ["telegram"]
    r = staff_client.get("/api/v1/staff/social/?q=VAL")
    assert [row["territori"] for row in r.data["results"]] == ["VAL"]


def test_invalid_filter_values_are_ignored(staff_client, sample_posts):
    # Unknown canal / estat / tipus must not 500 nor over-filter.
    r = staff_client.get("/api/v1/staff/social/?canal=zzz&estat=zzz&tipus=zzz")
    assert r.status_code == 200
    assert r.data["total"] == len(sample_posts)


# ── pagination ───────────────────────────────────────────────────────


def test_pagination_meta_and_default_page_size(staff_client, sample_posts):
    """Pagination contract: the meta keys are present and self-consistent,
    the default page size is a sane bounded value that fits the sample
    (not a pinned literal), and `per_page` is honoured when requested."""
    import math

    r = staff_client.get("/api/v1/staff/social/")
    for k in ("page", "num_pages", "total", "per_page", "has_next", "has_previous"):
        assert k in r.data
    n = len(sample_posts)
    assert r.data["total"] == n
    assert n <= r.data["per_page"] <= 200  # staff default fits the sample, ≤ cap
    assert r.data["page"] == 1 and r.data["num_pages"] == 1
    assert r.data["has_next"] is False and r.data["has_previous"] is False
    assert len(r.data["results"]) == n

    # A requested per_page is honoured and the meta stays consistent.
    r2 = staff_client.get("/api/v1/staff/social/?per_page=2")
    assert r2.data["per_page"] == 2
    assert len(r2.data["results"]) == 2
    assert r2.data["num_pages"] == math.ceil(n / 2)
    assert r2.data["has_next"] is True and r2.data["has_previous"] is False


# ── no-N+1: query count must not scale with rows ─────────────────────


def test_query_count_does_not_scale_with_rows(staff_client, db):
    # Warm up one-time lazy setup (content types, etc.) so it doesn't
    # pollute the comparison.
    staff_client.get("/api/v1/staff/social/?per_page=200")

    # Unique (platform, tipus, territori, setmana) per row → vary setmana.
    for i in range(3):
        _mk(
            "mastodon",
            "top_ppcc",
            "",
            MONDAY - datetime.timedelta(weeks=i + 1),
            SocialPost.STATUS_PUBLICAT,
        )
    with CaptureQueriesContext(connection) as ctx_small:
        staff_client.get("/api/v1/staff/social/?per_page=200")
    n_small = len(ctx_small)

    for i in range(20):
        _mk(
            "bluesky",
            "top_ppcc",
            "",
            MONDAY - datetime.timedelta(weeks=i + 10),
            SocialPost.STATUS_PUBLICAT,
        )
    with CaptureQueriesContext(connection) as ctx_big:
        staff_client.get("/api/v1/staff/social/?per_page=200")
    n_big = len(ctx_big)

    assert n_small == n_big, (
        f"social_list scales with rows: {n_small} queries for a small page, "
        f"{n_big} for a large one (N+1 in the serializer?)"
    )


# ── clickable-URL constructor ────────────────────────────────────────


def test_public_url_mastodon_uses_status_url():
    p = SocialPost(
        platform="mastodon",
        metadata={"external_id": "https://mastodont.cat/@tq/123"},
    )
    assert _public_url(p) == "https://mastodont.cat/@tq/123"


def test_public_url_bluesky_rewrites_at_uri():
    p = SocialPost(
        platform="bluesky",
        metadata={"external_id": "at://did:plc:abc/app.bsky.feed.post/xyz"},
    )
    assert _public_url(p) == "https://bsky.app/profile/did:plc:abc/post/xyz"


def test_public_url_telegram_uses_metadata_url():
    p = SocialPost(
        platform="telegram",
        metadata={"url": "https://t.me/topquaranta/42", "message_ids": [42]},
    )
    assert _public_url(p) == "https://t.me/topquaranta/42"


def test_public_url_instagram_without_permalink_is_empty():
    # No Graph permalink lookup at render time: a bare media id → no URL.
    p = SocialPost(platform="instagram_feed", instagram_media_id="17900000000000000")
    assert _public_url(p) == ""


# ── column contract: the serializer must keep feeding the table ──────


def test_serialize_exposes_table_columns(db):
    p = _mk("telegram", "top_territorial", "VAL", MONDAY, SocialPost.STATUS_PUBLICAT)
    row = _serialize(p)
    # Data / Canal / Objectiu / Setmana / Estat / Enllaç all sourced here.
    for k in (
        "published_at",
        "created_at",
        "platform",
        "tipus",
        "territori_label",
        "setmana",
        "project_week",
        "status",
        "url",
    ):
        assert k in row
