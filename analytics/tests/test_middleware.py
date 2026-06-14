"""Tests for AnalyticsMiddleware."""

from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from analytics.middleware import AnalyticsMiddleware
from analytics.models import MetricaEsdeveniment


def _mw(status: int = 200):
    return AnalyticsMiddleware(lambda req: HttpResponse(status=status))


_BOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
_HUMAN_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0 Safari/537.36"
)


@pytest.mark.django_db
def test_pageview_counted_for_public_get():
    rf = RequestFactory()
    _mw()(rf.get("/top"))
    assert MetricaEsdeveniment.objects.filter(
        clau="pageview", dimensio_1="/top"
    ).exists()


@pytest.mark.django_db
def test_pageview_bot_ua_classified_as_bot():
    rf = RequestFactory()
    _mw()(rf.get("/top", HTTP_USER_AGENT=_BOT_UA))
    assert MetricaEsdeveniment.objects.filter(
        clau="pageview", dimensio_1="/top", dimensio_2="bot"
    ).exists()


@pytest.mark.django_db
def test_pageview_human_ua_classified_as_human():
    rf = RequestFactory()
    _mw()(rf.get("/top", HTTP_USER_AGENT=_HUMAN_UA))
    assert MetricaEsdeveniment.objects.filter(
        clau="pageview", dimensio_1="/top", dimensio_2="human"
    ).exists()


@pytest.mark.django_db
def test_pageview_skipped_for_api_path():
    rf = RequestFactory()
    _mw()(rf.get("/api/v1/ranking/"))
    assert not MetricaEsdeveniment.objects.filter(clau="pageview").exists()


@pytest.mark.django_db
def test_pageview_skipped_for_static():
    rf = RequestFactory()
    _mw()(rf.get("/static/foo.css"))
    _mw()(rf.get("/staff/dashboard"))
    _mw()(rf.get("/favicon.ico"))
    assert not MetricaEsdeveniment.objects.filter(clau="pageview").exists()


@pytest.mark.django_db
def test_pageview_skipped_for_post():
    rf = RequestFactory()
    _mw()(rf.post("/foo"))
    assert not MetricaEsdeveniment.objects.filter(clau="pageview").exists()


@pytest.mark.django_db
def test_pageview_skipped_for_404():
    rf = RequestFactory()
    _mw(status=404)(rf.get("/missing"))
    assert not MetricaEsdeveniment.objects.filter(clau="pageview").exists()


@pytest.mark.django_db
def test_utm_landing_recorded():
    rf = RequestFactory()
    _mw()(rf.get("/", {"utm_source": "Mastodon", "utm_campaign": "Top_PPCC"}))
    row = MetricaEsdeveniment.objects.get(clau="utm_landing")
    # source + campaign normalized to lowercase
    assert row.dimensio_1 == "mastodon"
    assert row.dimensio_2 == "top_ppcc"


@pytest.mark.django_db
def test_utm_landing_works_on_skipped_paths():
    """We still want UTM credit for clicks landing on /staff/."""
    rf = RequestFactory()
    _mw()(rf.get("/staff/foo", {"utm_source": "newsletter"}))
    assert MetricaEsdeveniment.objects.filter(
        clau="utm_landing", dimensio_1="newsletter"
    ).exists()


@pytest.mark.django_db
def test_pageview_path_truncated_to_80_chars():
    rf = RequestFactory()
    long_path = "/" + ("a" * 200)
    _mw()(rf.get(long_path))
    row = MetricaEsdeveniment.objects.get(clau="pageview")
    assert len(row.dimensio_1) == 80
