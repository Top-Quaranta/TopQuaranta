"""The two endpoints anyone on the internet can POST to.

`/api/v1/analytics/{pageview,event}/` are `AllowAny` and write a row per
call. The audit of 2026-08-15 found no test at all — not on the `clau`
allowlist that keeps the table's schema closed, not on the truncation
that bounds what a stranger can store, not on the refusal of non-string
input. Analytics rows are forever, so what gets in is what we live with.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from analytics.models import MetricaEsdeveniment

PAGEVIEW = "/api/v1/analytics/pageview/"
EVENT = "/api/v1/analytics/event/"


def _c():
    return APIClient()


def _files(clau):
    return MetricaEsdeveniment.objects.filter(clau=clau)


@pytest.mark.django_db
def test_a_pageview_is_recorded():
    assert _c().post(PAGEVIEW, {"path": "/top"}, format="json").status_code == 204
    assert _files("pageview").filter(dimensio_1="/top").exists()


@pytest.mark.django_db
def test_a_missing_path_still_records_something_sane():
    """Fire-and-forget beacon: a malformed body must not 500, and must
    not write an empty dimension either."""
    assert _c().post(PAGEVIEW, {}, format="json").status_code == 204
    assert _files("pageview").filter(dimensio_1="/").exists()


@pytest.mark.django_db
def test_utm_is_only_recorded_when_there_is_a_source():
    _c().post(PAGEVIEW, {"path": "/", "utm_campaign": "sense-font"}, format="json")
    assert not _files("utm_landing").exists()

    _c().post(
        PAGEVIEW,
        {"path": "/", "utm_source": "Mastodon", "utm_campaign": "Setmanal"},
        format="json",
    )
    fila = _files("utm_landing").get()
    # Lower-cased so "Mastodon" and "mastodon" don't split the report.
    assert fila.dimensio_1 == "mastodon" and fila.dimensio_2 == "setmanal"


@pytest.mark.django_db
def test_an_unknown_event_key_is_refused():
    """The allowlist is what keeps the schema closed: without it anyone
    could invent keys and the table stops being aggregatable."""
    r = _c().post(EVENT, {"clau": "el_meu_esdeveniment"}, format="json")
    assert r.status_code == 400
    assert MetricaEsdeveniment.objects.count() == 0


@pytest.mark.django_db
def test_a_known_event_key_is_recorded():
    r = _c().post(
        EVENT,
        {"clau": "share_click", "dim1": "canco", "dim2": "bluesky"},
        format="json",
    )
    assert r.status_code == 204
    fila = _files("share_click").get()
    assert fila.dimensio_1 == "canco" and fila.dimensio_2 == "bluesky"


@pytest.mark.django_db
def test_long_values_are_truncated_not_stored_whole():
    """The only bound on what a stranger can put in our database. Without
    it, a beacon becomes free storage — and the column would raise."""
    llarg = "x" * 5000
    assert (
        _c()
        .post(EVENT, {"clau": "search_query", "dim1": llarg}, format="json")
        .status_code
        == 204
    )
    assert len(_files("search_query").get().dimensio_1) == 80


@pytest.mark.django_db
def test_non_string_dimensions_are_dropped_not_coerced():
    """A dict or a list must not reach the column. `_clean` returns ""
    for anything that isn't a string — pinned because "just str() it"
    is the tempting change that would let structures through."""
    r = _c().post(
        EVENT,
        {"clau": "mapa_zoom", "dim1": {"a": 1}, "dim2": [1, 2, 3]},
        format="json",
    )
    assert r.status_code == 204
    fila = _files("mapa_zoom").get()
    assert fila.dimensio_1 == "" and fila.dimensio_2 == ""


@pytest.mark.django_db
def test_the_endpoints_take_no_notice_of_who_is_asking():
    """Documented as aggregate-only: the body is the entire input
    surface. Nothing may read IP, UA, referer or session — a beacon that
    quietly starts identifying people is a privacy regression, not a
    feature."""
    import inspect

    from web.api import analytics_ingest

    codi = inspect.getsource(analytics_ingest)
    for prohibit in (
        "META",
        "REMOTE_ADDR",
        "HTTP_USER_AGENT",
        "request.session",
        "COOKIES",
    ):
        assert prohibit not in codi, prohibit


@pytest.mark.django_db
def test_a_beacon_pageview_counts_as_human():
    """The weekly digest filters on `dimensio_2="human"`. Rows written
    without a class are invisible to it, which is how the week of 10/08
    reported 98 human visits — mostly sitemap fetches — while 373 real
    SPA visits sat unclassified (2026-08-17).

    Classified by construction, not by inspection: reaching this endpoint
    means the SPA's JavaScript ran. Nothing about the caller is read, so
    the aggregate-only promise above still holds.
    """
    from analytics.bots import CLASS_HUMAN

    assert _c().post(PAGEVIEW, {"path": "/top"}, format="json").status_code == 204
    fila = _files("pageview").get()
    assert fila.dimensio_2 == CLASS_HUMAN
