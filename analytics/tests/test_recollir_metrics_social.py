"""Tests for the recollir_metrics_social cron command."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from analytics.models import MetricaSocialPlatform, MetricaSocialPost
from social.models import SocialPost


def _make_post(platform, ext_id, *, days_ago=1) -> SocialPost:
    setmana = (timezone.localdate() - datetime.timedelta(days=7)).replace()
    # Snap to Monday so unique_together holds across runs in same test.
    setmana = setmana - datetime.timedelta(days=setmana.weekday())
    post = SocialPost.objects.create(
        platform=platform,
        tipus=SocialPost.TIPUS_TOP_PPCC,
        territori="",
        setmana=setmana,
        status=SocialPost.STATUS_PUBLICAT,
        published_at=timezone.now() - datetime.timedelta(days=days_ago),
    )
    if platform == SocialPost.PLATFORM_INSTAGRAM_FEED:
        post.instagram_media_id = ext_id
    else:
        post.metadata = {"external_id": ext_id}
    post.save()
    return post


_FAKE_METRICS = {
    "likes": 12,
    "replies": 3,
    "shares": 4,
    "reach": 800,
    "impressions": 1000,
    "raw": {"ok": True},
}

_FAKE_ACCOUNT = {"followers": 250, "posts_total": 18, "raw": {"acct": True}}


@pytest.mark.django_db
def test_recollir_metrics_creates_per_post_rows():
    post = _make_post(SocialPost.PLATFORM_MASTODON, "1234")
    with (
        patch("social.mastodon_client.get_status_metrics", return_value=_FAKE_METRICS),
        patch("social.bluesky_client.get_post_metrics", return_value=_FAKE_METRICS),
        patch("social.instagram_client.get_post_metrics", return_value=_FAKE_METRICS),
        patch("social.telegram_client.get_post_metrics", return_value=_FAKE_METRICS),
        patch("social.mastodon_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch("social.bluesky_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch("social.instagram_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch(
            "social.telegram_client.get_account_stats",
            return_value={"members": 99, "raw": {}},
        ),
    ):
        call_command("recollir_metrics_social")
    row = MetricaSocialPost.objects.get(socialpost=post)
    assert row.likes == 12
    assert row.shares == 4


@pytest.mark.django_db
def test_recollir_metrics_idempotent_same_day():
    post = _make_post(
        SocialPost.PLATFORM_BLUESKY, "at://did:plc:abc/app.bsky.feed.post/xyz"
    )
    with (
        patch("social.mastodon_client.get_status_metrics", return_value=_FAKE_METRICS),
        patch("social.bluesky_client.get_post_metrics", return_value=_FAKE_METRICS),
        patch("social.instagram_client.get_post_metrics", return_value=_FAKE_METRICS),
        patch("social.telegram_client.get_post_metrics", return_value=_FAKE_METRICS),
        patch("social.mastodon_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch("social.bluesky_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch("social.instagram_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch(
            "social.telegram_client.get_account_stats",
            return_value={"members": 99, "raw": {}},
        ),
    ):
        call_command("recollir_metrics_social")
        call_command("recollir_metrics_social")
    assert MetricaSocialPost.objects.filter(socialpost=post).count() == 1


@pytest.mark.django_db
def test_recollir_metrics_skips_post_without_external_id():
    """A SocialPost with neither instagram_media_id nor metadata.external_id
    can't be fetched — the row is skipped silently, not errored."""
    post = SocialPost.objects.create(
        platform=SocialPost.PLATFORM_MASTODON,
        tipus=SocialPost.TIPUS_TOP_PPCC,
        territori="",
        setmana=timezone.localdate(),
        status=SocialPost.STATUS_PUBLICAT,
        published_at=timezone.now(),
    )
    with (
        patch(
            "social.mastodon_client.get_status_metrics", return_value=_FAKE_METRICS
        ) as fetch_mst,
        patch("social.mastodon_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch("social.bluesky_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch("social.instagram_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch(
            "social.telegram_client.get_account_stats",
            return_value={"members": 99, "raw": {}},
        ),
    ):
        call_command("recollir_metrics_social")
    fetch_mst.assert_not_called()
    assert not MetricaSocialPost.objects.filter(socialpost=post).exists()


@pytest.mark.django_db
def test_recollir_metrics_swallows_per_post_errors():
    """One platform raising must not stop ingest of the others."""
    p1 = _make_post(SocialPost.PLATFORM_MASTODON, "111")
    p2 = _make_post(
        SocialPost.PLATFORM_BLUESKY, "at://did/app.bsky.feed.post/zzz", days_ago=2
    )
    with (
        patch(
            "social.mastodon_client.get_status_metrics",
            side_effect=RuntimeError("boom"),
        ),
        patch("social.bluesky_client.get_post_metrics", return_value=_FAKE_METRICS),
        patch("social.mastodon_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch("social.bluesky_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch("social.instagram_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch(
            "social.telegram_client.get_account_stats",
            return_value={"members": 99, "raw": {}},
        ),
    ):
        call_command("recollir_metrics_social")
    assert not MetricaSocialPost.objects.filter(socialpost=p1).exists()
    assert MetricaSocialPost.objects.filter(socialpost=p2).exists()


@pytest.mark.django_db
def test_recollir_metrics_writes_account_gauges():
    with (
        patch("social.mastodon_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch("social.bluesky_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch("social.instagram_client.get_account_stats", return_value=_FAKE_ACCOUNT),
        patch(
            "social.telegram_client.get_account_stats",
            return_value={"members": 99, "raw": {}},
        ),
    ):
        call_command("recollir_metrics_social")
    today = timezone.localdate()
    assert MetricaSocialPlatform.objects.filter(
        data=today, platform="mastodon", metric="followers", valor=250
    ).exists()
    assert MetricaSocialPlatform.objects.filter(
        data=today, platform="telegram", metric="members", valor=99
    ).exists()
