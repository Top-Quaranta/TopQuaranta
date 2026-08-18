"""Tests for the spotify_artist_dispersio feature in ml._build_features.

The feature is the 17th structured value, between the MB block and
the TF-IDF tail. We assert it is present at the expected index and
respects the artista's `spotify_artist_dispersio` field, including
the None fallback.
"""

from __future__ import annotations

import pytest

from music.ml import (
    FEATURE_NAMES,
    _build_features,
    _spotify_dispersion_feature,
    _spotify_dispersion_from_historial,
)
from music.models import Album, Artista, Canco


@pytest.fixture
def base(db):
    a = Artista.objects.create(nom="EXEMPLE D", lastfm_nom="EXEMPLE D")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al")
    c = Canco.objects.create(artista=a, album=al, nom="EXEMPLE C", isrc="ZZ00DL0000001")
    return a, al, c


def test_dispersion_feature_reads_artista_field(base):
    a, _, c = base
    a.spotify_artist_dispersio = 3
    a.save(update_fields=["spotify_artist_dispersio"])
    a.refresh_from_db()
    assert _spotify_dispersion_feature(a) == 3.0


def test_dispersion_feature_none_falls_back_to_zero(base):
    a, _, c = base
    # Brand-new artista: dispersio is NULL by default.
    assert a.spotify_artist_dispersio is None
    assert _spotify_dispersion_feature(a) == 0.0


def test_dispersion_feature_artista_none_is_zero():
    """Defensive: an artista=None call site should never crash."""
    assert _spotify_dispersion_feature(None) == 0.0


@pytest.mark.django_db
def test_build_features_includes_dispersion_at_expected_index():
    """End-to-end: a Cançó whose artista has dispersio=2 produces a
    feature vector where the slot before the TF-IDF tail is 2.0.

    Property asserted: the vector is aligned with FEATURE_NAMES (same
    length) and the value at the column NAMED `spotify_artist_dispersio`
    is the artista's dispersio. The index is looked up by name, so
    appending features at the end of FEATURE_NAMES (the post-2026-05-23
    convention, see docs/ops/runbook.md) does not break this test."""
    a = Artista.objects.create(
        nom="EXEMPLE D2", lastfm_nom="EXEMPLE D2", spotify_artist_dispersio=2
    )
    al = Album.objects.create(artista=a, nom="EXEMPLE Al2")
    c = Canco.objects.create(
        artista=a, album=al, nom="EXEMPLE D2 song", isrc="ZZ00DL0000002"
    )
    feats = _build_features(c)
    assert len(feats) == len(FEATURE_NAMES)
    idx = FEATURE_NAMES.index("spotify_artist_dispersio")
    assert feats[idx] == 2.0
    # The column tracks the field, not a constant: change the artista's
    # dispersio and the same slot moves with it.
    a.spotify_artist_dispersio = 5
    a.save(update_fields=["spotify_artist_dispersio"])
    c.refresh_from_db()
    assert _build_features(c)[idx] == 5.0


@pytest.mark.django_db
def test_dispersion_from_historial_resolves_via_isrc(base):
    """Training-side helper: a HistorialRevisio row whose canco_isrc
    still resolves to a live Canço reads the artist's current
    dispersion. Mirrors the existing mb_features_from_historial
    fallback pattern."""
    from music.models import HistorialRevisio

    a, _, c = base
    a.spotify_artist_dispersio = 4
    a.save(update_fields=["spotify_artist_dispersio"])

    rec = HistorialRevisio.objects.create(
        canco_isrc=c.isrc,
        canco_nom=c.nom,
        artista_nom=a.nom,
        decisio="aprovada",
    )
    assert _spotify_dispersion_from_historial(rec) == 4.0


@pytest.mark.django_db
def test_dispersion_from_historial_missing_canco_returns_zero():
    """If neither deezer_id nor ISRC resolves to a live Canço, the
    feature falls back to 0.0 (same convention as the MB helper)."""
    from music.models import HistorialRevisio

    rec = HistorialRevisio.objects.create(
        canco_isrc="ZZNOTREAL00001",
        canco_nom="EXEMPLE gone",
        artista_nom="EXEMPLE gone",
        decisio="rebutjada",
    )
    assert _spotify_dispersion_from_historial(rec) == 0.0
