"""Guards for `social_metrics_summary` — per-platform engagement totals
from the latest MetricaSocialPost snapshot of each post (additive,
read-only; never touches the publications row list).
"""

from __future__ import annotations

import datetime

import pytest
from rest_framework.test import APIClient

from analytics.models import MetricaSocialPost
from social.models import SocialPost

URL = "/api/v1/staff/social/metrics-summary/"
MONDAY = datetime.date(2026, 6, 1)


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="metrics_tester",
        email="m@example.com",
        password="x",
        is_staff=True,
    )
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _post(platform, setmana=MONDAY):
    return SocialPost.objects.create(
        platform=platform,
        tipus="top_ppcc",
        territori="",
        setmana=setmana,
        status=SocialPost.STATUS_PUBLICAT,
    )


def _metric(post, data, **counts):
    return MetricaSocialPost.objects.create(socialpost=post, data=data, **counts)


def test_requires_staff(db):
    assert APIClient().get(URL).status_code in (401, 403)


@pytest.mark.django_db
def test_aggregates_latest_snapshot_per_platform(staff_client):
    p_mast = _post("mastodon")
    p_blue = _post("bluesky")
    # Two snapshots for the mastodon post: the LATER date must win.
    _metric(p_mast, MONDAY, likes=5, reach=100)
    _metric(p_mast, MONDAY + datetime.timedelta(days=1), likes=8, reach=160)
    _metric(p_blue, MONDAY, likes=3, reach=40)

    r = staff_client.get(URL)
    assert r.status_code == 200
    rows = {row["platform"]: row for row in r.data["per_platform"]}
    assert rows["mastodon"]["likes"] == 8  # latest snapshot, not 5+8
    assert rows["mastodon"]["reach"] == 160
    assert rows["mastodon"]["n_posts"] == 1
    assert rows["bluesky"]["likes"] == 3
    assert rows["bluesky"]["n_posts"] == 1


@pytest.mark.django_db
def test_sums_across_posts_of_same_platform(staff_client):
    a = _post("telegram")
    b = _post("telegram", setmana=MONDAY + datetime.timedelta(days=7))
    _metric(a, MONDAY, likes=2, shares=1)
    _metric(b, MONDAY, likes=4, shares=3)
    r = staff_client.get(URL)
    tg = next(x for x in r.data["per_platform"] if x["platform"] == "telegram")
    assert tg["n_posts"] == 2 and tg["likes"] == 6 and tg["shares"] == 4


@pytest.mark.django_db
def test_query_count_is_constant_no_n_plus_1(
    staff_client, django_assert_max_num_queries
):
    """The latest-per-post + group-by-platform aggregate is a single
    metrics query (select_related on the post) + Python grouping. It must
    NOT scale with the number of posts: a per-post N+1 over 10 posts would
    blow past this ceiling."""
    base = MONDAY
    for i in range(10):
        p = _post("mastodon", setmana=base + datetime.timedelta(days=7 * i))
        _metric(p, base, likes=i, reach=i * 10)
    # Measured constant at 7 (1 metrics aggregate + auth/permission); a
    # per-post N+1 over 10 posts would be ~17, so 9 is the tripwire.
    with django_assert_max_num_queries(9):
        r = staff_client.get(URL)
    assert r.status_code == 200
    row = next(x for x in r.data["per_platform"] if x["platform"] == "mastodon")
    assert row["n_posts"] == 10


@pytest.mark.django_db
def test_post_without_metrics_absent(staff_client):
    _post("newsletter")  # published but no snapshot yet
    r = staff_client.get(URL)
    assert all(x["platform"] != "newsletter" for x in r.data["per_platform"])
    assert r.data["per_platform"] == []
