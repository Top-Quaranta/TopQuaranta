"""Tests for the artist dispersion calculator.

Covers:
  * Clean mapping (all enriched tracks point to one Spotify artist)
    -> dispersion 1.
  * Mixed mapping (multiple distinct principal artists) -> dispersion
    matches the unique count.
  * Collaborations (artists list >1) don't inflate dispersion because
    we only count the principal artist_id.
  * Cançons with status != found are excluded from the calculation.
  * Filtering by artista_ids subset only updates those artistes.
"""

from __future__ import annotations

import pytest

from music.models import Album, Artista, Canco, SpotifyMetadata
from music.spotify_dispersio import recalcular_dispersio


def _canco(artista, album, idx: int) -> Canco:
    c = Canco.objects.create(
        artista=artista,
        album=album,
        nom=f"EXEMPLE-d-{idx:04d}",
        isrc=f"ZZ00D{idx:07d}",
    )
    # SpotifyMetadata is not auto-created via signal; ensure the row
    # exists for the test (in prod the 0080 migration covers existing
    # rows but new ones need an explicit insert).
    SpotifyMetadata.objects.get_or_create(canco=c)
    return c


def _enrich(canco, principal_id: str, all_ids: list[str], status="found"):
    sm = canco.spotify
    sm.spotify_artist_id = principal_id
    sm.spotify_artist_ids = all_ids
    sm.enrichment_status = status
    sm.save()
    return sm


@pytest.mark.django_db
def test_clean_mapping_dispersion_1():
    a = Artista.objects.create(nom="EXEMPLE Clean", lastfm_nom="EXEMPLE Clean")
    al = Album.objects.create(artista=a, nom="EXEMPLE A")
    for i in range(3):
        c = _canco(a, al, i)
        _enrich(c, "ARTX", ["ARTX"])

    out = recalcular_dispersio()
    assert out["inspected"] >= 1
    a.refresh_from_db()
    assert a.spotify_artist_dispersio == 1
    assert a.spotify_artist_ids_distints == ["ARTX"]


@pytest.mark.django_db
def test_mixed_mapping_dispersion_n():
    a = Artista.objects.create(nom="EXEMPLE Mixed", lastfm_nom="EXEMPLE Mixed")
    al = Album.objects.create(artista=a, nom="EXEMPLE M")
    for i, pid in enumerate(["ARTA", "ARTB", "ARTC", "ARTA"]):
        c = _canco(a, al, 100 + i)
        _enrich(c, pid, [pid])

    recalcular_dispersio(artista_ids=[a.pk])
    a.refresh_from_db()
    assert a.spotify_artist_dispersio == 3
    assert a.spotify_artist_ids_distints == ["ARTA", "ARTB", "ARTC"]


@pytest.mark.django_db
def test_collaborators_do_not_inflate_dispersion():
    """The full artists[] list might include guests; only the principal
    artist counts toward dispersion."""
    a = Artista.objects.create(nom="EXEMPLE Coll", lastfm_nom="EXEMPLE Coll")
    al = Album.objects.create(artista=a, nom="EXEMPLE C")
    c1 = _canco(a, al, 200)
    c2 = _canco(a, al, 201)
    _enrich(c1, "ARTP", ["ARTP", "GUEST1"])
    _enrich(c2, "ARTP", ["ARTP", "GUEST2", "GUEST3"])

    recalcular_dispersio(artista_ids=[a.pk])
    a.refresh_from_db()
    # Despite 4 distinct ids across both tracks, dispersion is 1
    # because every PRINCIPAL is ARTP.
    assert a.spotify_artist_dispersio == 1
    assert a.spotify_artist_ids_distints == ["ARTP"]


@pytest.mark.django_db
def test_not_found_cancons_excluded():
    """Status != found contributes nothing to dispersion."""
    a = Artista.objects.create(nom="EXEMPLE NF", lastfm_nom="EXEMPLE NF")
    al = Album.objects.create(artista=a, nom="EXEMPLE N")
    c1 = _canco(a, al, 300)
    c2 = _canco(a, al, 301)
    _enrich(c1, "ARTP", ["ARTP"], status="found")
    _enrich(c2, "ARTQ", ["ARTQ"], status="not_found")
    # Even though c2 has a spotify_artist_id set, status=not_found
    # excludes it from the dispersion calc.

    recalcular_dispersio(artista_ids=[a.pk])
    a.refresh_from_db()
    assert a.spotify_artist_dispersio == 1


@pytest.mark.django_db
def test_subset_filter_only_updates_those_artistas():
    a1 = Artista.objects.create(nom="EXEMPLE S1", lastfm_nom="EXEMPLE S1")
    a2 = Artista.objects.create(nom="EXEMPLE S2", lastfm_nom="EXEMPLE S2")
    al1 = Album.objects.create(artista=a1, nom="EXEMPLE Al1")
    al2 = Album.objects.create(artista=a2, nom="EXEMPLE Al2")
    _enrich(_canco(a1, al1, 400), "ART1", ["ART1"])
    _enrich(_canco(a2, al2, 401), "ART2", ["ART2"])

    # Only recompute a1.
    recalcular_dispersio(artista_ids=[a1.pk])
    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.spotify_artist_dispersio == 1
    # a2 was not in the target set, so it stays at the default (None).
    assert a2.spotify_artist_dispersio is None


@pytest.mark.django_db
def test_artist_with_no_enriched_cancons_keeps_null():
    a = Artista.objects.create(nom="EXEMPLE Z", lastfm_nom="EXEMPLE Z")
    al = Album.objects.create(artista=a, nom="EXEMPLE Z")
    _canco(a, al, 500)
    # Stays not_attempted -> no signal.
    recalcular_dispersio(artista_ids=[a.pk])
    a.refresh_from_db()
    assert a.spotify_artist_dispersio is None
    assert a.spotify_artist_ids_distints == []
