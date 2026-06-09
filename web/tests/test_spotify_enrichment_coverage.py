"""Guards for the catalog-wide Spotify enrichment-coverage KPI exposed
by `spotify_estat` (`web/api/staff/social/spotify.py`).

Denominator = active Cançons with an ISRC (the enrichment command's
target); numerator = those with a usable id (SpotifyMetadata in
LOCKED_STATUSES = found + manual). No Spotify HTTP (no SpotifyAuth row →
the endpoint skips the live `/me` call).
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from music.models import Album, Artista, Canco, SpotifyMetadata
from web.api.staff.social.spotify import _enrichment_coverage


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="enrich_cov_tester",
        email="ec@example.com",
        password="x",
        is_staff=True,
    )
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _canco(nom, isrc, activa=True, status=None):
    a, _ = Artista.objects.get_or_create(nom="A", slug="a", defaults={"aprovat": True})
    al, _ = Album.objects.get_or_create(nom="Al", slug="al", artista=a)
    c = Canco.objects.create(
        nom=nom,
        slug=nom.lower(),
        artista=a,
        album=al,
        isrc=isrc,
        activa=activa,
        verificada=True,
    )
    if status is not None:
        SpotifyMetadata.objects.create(canco=c, enrichment_status=status)
    return c


@pytest.fixture
def catalog(db):
    _canco("c1", "ISRC1", status=SpotifyMetadata.STATUS_FOUND)  # in target, enriched
    _canco("c2", "ISRC2", status=SpotifyMetadata.STATUS_MANUAL)  # in target, enriched
    _canco("c3", "ISRC3", status=SpotifyMetadata.STATUS_NOT_FOUND)  # target, not
    _canco("c4", "ISRC4")  # in target, no SpotifyMetadata → not enriched
    _canco("c5", "")  # no ISRC → NOT in target
    _canco(
        "c6", "ISRC6", activa=False, status=SpotifyMetadata.STATUS_FOUND
    )  # inactive → NOT in target


def test_enrichment_coverage_counts(catalog):
    cov = _enrichment_coverage()
    assert cov["total"] == 4  # c1-c4 (active + ISRC)
    assert cov["enriched"] == 2  # c1 (found) + c2 (manual)
    assert cov["ratio"] == 0.5


@pytest.mark.django_db
def test_enrichment_coverage_ratio_none_when_no_target():
    cov = _enrichment_coverage()
    assert cov["total"] == 0 and cov["enriched"] == 0 and cov["ratio"] is None


@pytest.mark.django_db
def test_estat_endpoint_exposes_coverage(staff_client, catalog):
    r = staff_client.get("/api/v1/staff/social/spotify/estat/")
    assert r.status_code == 200
    cov = r.data["enrichment_coverage"]
    assert cov["total"] == 4 and cov["enriched"] == 2 and cov["ratio"] == 0.5
