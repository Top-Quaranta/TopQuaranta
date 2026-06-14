"""Guards for the Bing Webmaster cron (mirror of the GSC test).

Locks in: the response envelope/`/Date/`/`÷10` parsing; the clean
no-op when the API key is absent (so CI + local stay green without the
secret); and the hard STOP when the site is not a verified property.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from analytics.models import (
    MetricaBingCrawl,
    MetricaBingLinks,
    MetricaBingPage,
    MetricaBingQuery,
    MetricaBingTraffic,
)

# One crafted envelope per Bing method. `/Date(1700000000000)/` is
# 2023-11-14 UTC; positions are ×10 (63 -> 6.3).
_RESPONSES = {
    "GetSites": {"d": [{"Url": "https://www.topquaranta.cat/", "IsVerified": True}]},
    "GetRankAndTrafficStats": {
        "d": [{"Date": "/Date(1700000000000)/", "Clicks": 5, "Impressions": 100}]
    },
    "GetQueryStats": {
        "d": [
            {
                "Query": "no callarem",
                "Clicks": 3,
                "Impressions": 50,
                "AvgClickPosition": 63,
                "AvgImpressionPosition": 71,
            }
        ]
    },
    "GetPageStats": {
        "d": [
            {
                "Query": "https://www.topquaranta.cat/album/x",
                "Clicks": 2,
                "Impressions": 40,
                "AvgClickPosition": 50,
                "AvgImpressionPosition": 60,
            }
        ]
    },
    "GetCrawlStats": {
        "d": [
            {
                "Date": "/Date(1700000000000)/",
                "CrawledPages": 120,
                "InLinks": 340,
                "CrawlErrors": 2,
                "BlockedByRobotsTxtPages": 1,
            }
        ]
    },
    "GetUrlLinks": {
        "d": [
            {"Url": "https://example.com/a"},
            {"Url": "https://example.com/b"},
            {"Url": "https://other.org/c"},
        ]
    },
}


def _fake_get(responses):
    def _get(url, params=None, timeout=None):
        method = url.rsplit("/", 1)[1]
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = responses.get(method, {"d": []})
        return resp

    return _get


@pytest.mark.django_db
@override_settings(BING_WEBMASTER_API_KEY="")
def test_no_key_clean_skip():
    """Without the key the cron must no-op cleanly (CI/local green)."""
    with patch(
        "analytics.management.commands.recollir_metrics_bing.requests.get"
    ) as mock_get:
        call_command("recollir_metrics_bing")
        mock_get.assert_not_called()
    assert MetricaBingTraffic.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    BING_WEBMASTER_API_KEY="k",
    BING_WEBMASTER_SITE_URL="https://www.topquaranta.cat",
)
def test_parses_envelope_quirks():
    with patch(
        "analytics.management.commands.recollir_metrics_bing.requests.get",
        side_effect=_fake_get(_RESPONSES),
    ):
        call_command("recollir_metrics_bing")

    import datetime

    expected_day = datetime.date(2023, 11, 14)  # /Date(1700000000000)/
    traffic = MetricaBingTraffic.objects.get(data=expected_day)
    assert traffic.clicks == 5 and traffic.impressions == 100

    q = MetricaBingQuery.objects.get(query="no callarem")
    assert q.avg_click_position == pytest.approx(6.3)
    assert q.avg_impression_position == pytest.approx(7.1)

    assert MetricaBingPage.objects.filter(
        page="https://www.topquaranta.cat/album/x"
    ).exists()

    crawl = MetricaBingCrawl.objects.get(data=expected_day)
    assert crawl.in_links == 340 and crawl.crawled_pages == 120

    links = MetricaBingLinks.objects.latest("data")
    assert links.inbound_links == 3
    assert links.linking_domains == 2  # example.com + other.org


@pytest.mark.django_db
@override_settings(
    BING_WEBMASTER_API_KEY="k",
    BING_WEBMASTER_SITE_URL="https://www.topquaranta.cat",
)
def test_unverified_site_stops():
    """A site that is not a verified property must STOP with an error,
    not invent data."""
    responses = dict(_RESPONSES)
    responses["GetSites"] = {
        "d": [{"Url": "https://www.topquaranta.cat/", "IsVerified": False}]
    }
    with patch(
        "analytics.management.commands.recollir_metrics_bing.requests.get",
        side_effect=_fake_get(responses),
    ):
        with pytest.raises(CommandError, match="verificada"):
            call_command("recollir_metrics_bing")
    assert MetricaBingTraffic.objects.count() == 0
