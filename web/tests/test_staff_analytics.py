"""Tests for `web/api/staff/analytics.py::analytics_summary`.

Bug 1 of Fase 3 (2026-05-18): the social-publications counter must
derive from `SocialPost` (canonical, idempotent source) rather than
from `MetricaEsdeveniment(clau="social_publicat")` (append-only,
fragile — broken twice over: legacy posts before `register()` was
wired, and story-sets over-counting until PR #31).
"""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from social.models import SocialPost


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="analytics_tester",
        email="at@example.com",
        password="x",
        is_staff=True,
    )
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _monday_of(date_):
    return date_ - datetime.timedelta(days=date_.weekday())


@pytest.mark.django_db
def test_social_counter_derives_from_socialpost_publicat(staff_client):
    """A 30-day summary must reflect every `status=publicat` SocialPost
    whose `setmana` falls inside the window; `omes` rows must NOT
    contribute, regardless of any `MetricaEsdeveniment` rows. This
    locks in the Bug 1 contract."""
    today = timezone.localdate()
    setmana = _monday_of(today)

    # 4 IG feed publicats — must all be counted.
    for tipus in (
        SocialPost.TIPUS_TOP_PPCC,
        SocialPost.TIPUS_TOP_TERRITORIAL,
        SocialPost.TIPUS_NOUS_ALBUMS,
        SocialPost.TIPUS_NOUS_SINGLES,
    ):
        SocialPost.objects.create(
            platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
            tipus=tipus,
            territori="PPCC",
            setmana=setmana,
            status=SocialPost.STATUS_PUBLICAT,
        )
    # 2 Mastodon publicats — different setmana (within window).
    setmana_prev = setmana - datetime.timedelta(days=7)
    for i, tipus in enumerate(
        (SocialPost.TIPUS_TOP_PPCC, SocialPost.TIPUS_NOUS_SINGLES)
    ):
        SocialPost.objects.create(
            platform=SocialPost.PLATFORM_MASTODON,
            tipus=tipus,
            territori="PPCC" if i == 0 else "",
            setmana=setmana_prev,
            status=SocialPost.STATUS_PUBLICAT,
        )
    # 1 IG feed omès — MUST NOT be counted.
    SocialPost.objects.create(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
        tipus=SocialPost.TIPUS_TOP_PPCC,
        territori="CAT",
        setmana=setmana,
        status=SocialPost.STATUS_OMES,
    )

    r = staff_client.get("/api/v1/staff/analytics/summary/?days=30")
    assert r.status_code == 200, r.content
    data = r.json()
    by_channel = {}
    for row in data.get("social", []):
        by_channel.setdefault(row["channel"], 0)
        by_channel[row["channel"]] += row["total"]

    assert by_channel.get(SocialPost.PLATFORM_INSTAGRAM_FEED) == 4, by_channel
    assert by_channel.get(SocialPost.PLATFORM_MASTODON) == 2, by_channel
    extras = {
        k: v for k, v in by_channel.items() if k not in {"instagram_feed", "mastodon"}
    }
    assert extras == {}, f"Unexpected channels in counter: {extras}"


@pytest.mark.django_db
def test_social_counter_window_excludes_out_of_range_setmana(staff_client):
    """A SocialPost with `setmana` older than the window must not
    appear in the counter (the unit of aggregation is the ISO week
    of `setmana`, not `published_at` or `created_at`)."""
    today = timezone.localdate()
    setmana = _monday_of(today)
    old_setmana = setmana - datetime.timedelta(days=120)

    SocialPost.objects.create(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
        tipus=SocialPost.TIPUS_TOP_PPCC,
        territori="PPCC",
        setmana=old_setmana,
        status=SocialPost.STATUS_PUBLICAT,
    )
    r = staff_client.get("/api/v1/staff/analytics/summary/?days=30")
    assert r.status_code == 200
    by_channel = {row["channel"]: row["total"] for row in r.json().get("social", [])}
    assert by_channel.get(SocialPost.PLATFORM_INSTAGRAM_FEED, 0) == 0
