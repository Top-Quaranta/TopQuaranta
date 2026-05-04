"""Tests for the public SPA analytics ingest endpoints."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from analytics.models import MetricaEsdeveniment


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_pageview_endpoint_records(client):
    res = client.post(
        reverse("api:analytics_pageview"),
        {"path": "/top"},
        format="json",
    )
    assert res.status_code == 204
    assert MetricaEsdeveniment.objects.filter(
        clau="pageview", dimensio_1="/top"
    ).exists()


@pytest.mark.django_db
def test_pageview_with_utm_records_both(client):
    res = client.post(
        reverse("api:analytics_pageview"),
        {"path": "/", "utm_source": "Mastodon", "utm_campaign": "Top_PPCC"},
        format="json",
    )
    assert res.status_code == 204
    assert MetricaEsdeveniment.objects.filter(clau="pageview", dimensio_1="/").exists()
    row = MetricaEsdeveniment.objects.get(clau="utm_landing")
    # lower-cased + truncated
    assert row.dimensio_1 == "mastodon"
    assert row.dimensio_2 == "top_ppcc"


@pytest.mark.django_db
def test_event_known_clau_records(client):
    res = client.post(
        reverse("api:analytics_event"),
        {"clau": "escolta_click", "dim1": "spotify"},
        format="json",
    )
    assert res.status_code == 204
    assert MetricaEsdeveniment.objects.filter(
        clau="escolta_click", dimensio_1="spotify"
    ).exists()


@pytest.mark.django_db
def test_event_unknown_clau_rejected(client):
    res = client.post(
        reverse("api:analytics_event"),
        {"clau": "rogue_metric"},
        format="json",
    )
    assert res.status_code == 400
    assert not MetricaEsdeveniment.objects.filter(clau="rogue_metric").exists()
