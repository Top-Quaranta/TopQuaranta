"""Tests for the SpotifyMetadata + dispersion fields on the
/api/v1/staff/cancons/ workbench response (FASE 6).

Covers:
  * Cançó with SpotifyMetadata in status=found -> spotify payload
    surfaces (spotify_id, artist_name, artist_id).
  * Cançó without enrichment -> spotify is null in the response.
  * Artista.spotify_artist_dispersio populated -> surfaced under
    artista.spotify_dispersio.

Reuses the existing staff client pattern from test_staff_spotify.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from music.models import Album, Artista, Canco, SpotifyMetadata


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="cancons_spotify_tester",
        email="cs@example.com",
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


@pytest.mark.django_db
def test_cancons_list_includes_spotify_payload_when_found(staff_client):
    a = Artista.objects.create(
        nom="EXEMPLE A",
        lastfm_nom="EXEMPLE A",
        spotify_artist_dispersio=2,
        spotify_artist_ids_distints=["ART1", "ART2"],
    )
    al = Album.objects.create(artista=a, nom="EXEMPLE Al")
    c = Canco.objects.create(
        artista=a,
        album=al,
        nom="EXEMPLE C",
        isrc="ZZSP0000001",
        verificada=False,
        activa=True,
    )
    SpotifyMetadata.objects.create(
        canco=c,
        spotify_id="SPID123",
        spotify_artist_id="ART1",
        spotify_artist_name="EXEMPLE Spotify Name",
        enrichment_status=SpotifyMetadata.STATUS_FOUND,
    )

    r = staff_client.get("/api/v1/staff/cancons/?verificada=0")
    assert r.status_code == 200, r.content
    rows = r.json()["results"]
    row = next(rw for rw in rows if rw["pk"] == c.pk)
    assert row["spotify"] is not None
    assert row["spotify"]["spotify_id"] == "SPID123"
    assert row["spotify"]["artist_name"] == "EXEMPLE Spotify Name"
    assert row["spotify"]["artist_id"] == "ART1"
    # And the artist's dispersion comes through.
    assert row["artista"]["spotify_dispersio"] == 2


@pytest.mark.django_db
def test_cancons_list_spotify_null_when_not_enriched(staff_client):
    a = Artista.objects.create(nom="EXEMPLE Z", lastfm_nom="EXEMPLE Z")
    al = Album.objects.create(artista=a, nom="EXEMPLE Z")
    c = Canco.objects.create(
        artista=a,
        album=al,
        nom="EXEMPLE Z",
        isrc="ZZSP0000002",
        verificada=False,
        activa=True,
    )
    # Either no SM row or status=not_attempted -> spotify is null.
    SpotifyMetadata.objects.create(canco=c)  # default: not_attempted

    r = staff_client.get("/api/v1/staff/cancons/?verificada=0")
    assert r.status_code == 200
    row = next(rw for rw in r.json()["results"] if rw["pk"] == c.pk)
    assert row["spotify"] is None
    assert row["artista"]["spotify_dispersio"] is None
