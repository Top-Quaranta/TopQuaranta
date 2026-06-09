"""Fase 3 quick wins (problems 3, 4, 6 — 2026-05-18).

Three discrete improvements to the SocialTab payload:
  - Problem 4: `newsletter_audience` counts `Usuari(vol_newsletter=True,
    is_active=True)` so the followers strip can render Newsletter
    alongside the social platforms.
  - Problem 6: `social_omes` mirrors `social` but filters
    `status=omès`, exposing the volume of slots the distribution
    matrix is filtering.
  - Problem 3 is purely frontend (computed from existing
    `followers_series`), so no backend assertion here.
"""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from comptes.models import PerfilUsuari, Usuari
from social.models import SocialPost


@pytest.fixture
def staff_client(db):
    user = Usuari.objects.create_user(
        username="qw_tester",
        email="qw@example.com",
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
def test_newsletter_audience_counts_active_subscribers(staff_client):
    """Only `PerfilUsuari.vol_newsletter=True AND Usuari.is_active=True`
    count. The flag lives on PerfilUsuari (created via post_save signal
    on Usuari) and defaults to False, so we must explicitly opt-in
    each test user."""

    def _create_with_perfil(username, email, *, is_active, vol_newsletter):
        u = Usuari.objects.create_user(
            username=username, email=email, password="x", is_active=is_active
        )
        # PerfilUsuari is created by the post_save signal at this point.
        PerfilUsuari.objects.filter(usuari=u).update(vol_newsletter=vol_newsletter)
        return u

    _create_with_perfil(
        "sub_yes_active", "a@example.com", is_active=True, vol_newsletter=True
    )
    _create_with_perfil(
        "sub_yes_inactive", "b@example.com", is_active=False, vol_newsletter=True
    )
    _create_with_perfil("sub_no", "c@example.com", is_active=True, vol_newsletter=False)

    r = staff_client.get("/api/v1/staff/analytics/summary/?days=30")
    assert r.status_code == 200, r.content
    # Only sub_yes_active contributes; the staff fixture user defaults
    # to vol_newsletter=False. Newsletter audience == 1.
    assert r.json()["newsletter_audience"] == 1


@pytest.mark.django_db
def test_social_omes_lists_omes_publications_per_channel(staff_client):
    """`social_omes` mirrors `social` shape but only `status=omes`."""
    today = timezone.localdate()
    setmana = _monday_of(today)
    # 3 omes on IG feed, 1 omes on Mastodon, 1 publicat (must NOT
    # appear in social_omes).
    for i in range(3):
        SocialPost.objects.create(
            platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
            tipus=SocialPost.TIPUS_TOP_PPCC,
            territori=f"T{i}",
            setmana=setmana,
            status=SocialPost.STATUS_OMES,
        )
    SocialPost.objects.create(
        platform=SocialPost.PLATFORM_MASTODON,
        tipus=SocialPost.TIPUS_TOP_PPCC,
        territori="PPCC",
        setmana=setmana,
        status=SocialPost.STATUS_OMES,
    )
    SocialPost.objects.create(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
        tipus=SocialPost.TIPUS_NOUS_SINGLES,
        territori="PPCC",
        setmana=setmana,
        status=SocialPost.STATUS_PUBLICAT,
    )

    r = staff_client.get("/api/v1/staff/analytics/summary/?days=30")
    assert r.status_code == 200
    data = r.json()

    omes_by_channel = {}
    for row in data["social_omes"]:
        omes_by_channel.setdefault(row["channel"], 0)
        omes_by_channel[row["channel"]] += row["total"]
    assert omes_by_channel.get(SocialPost.PLATFORM_INSTAGRAM_FEED) == 3
    assert omes_by_channel.get(SocialPost.PLATFORM_MASTODON) == 1

    # social (publicat) must contain only the one IG feed row.
    pub_by_channel = {row["channel"]: row["total"] for row in data["social"]}
    assert pub_by_channel.get(SocialPost.PLATFORM_INSTAGRAM_FEED) == 1
    assert pub_by_channel.get(SocialPost.PLATFORM_MASTODON, 0) == 0


@pytest.mark.django_db
def test_payload_shape_with_empty_db(staff_client):
    """Smoke test: with no data, the new fields are present and
    empty (the frontend must not crash on `data.social_omes ?? []`)."""
    r = staff_client.get("/api/v1/staff/analytics/summary/?days=30")
    assert r.status_code == 200
    data = r.json()
    assert data["social_omes"] == []
    assert data["newsletter_audience"] == 0
