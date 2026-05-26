"""Tests for the backfill enrichment command.

Pins the URI-to-ID strip that mirrors the maintenance command's
`_enrich_one`. Without it, `search_isrc` returns a Spotify URI
(`spotify:track:<id>`) and the next call hits
`https://api.spotify.com/v1/tracks/spotify:track:<id>` which
returns 400 Bad Request. Caught on the first wet run on
2026-05-26.
"""

# Spec: docs/architecture/pipeline.md

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from ingesta.clients.spotify_metadata_cooldown import SHARED_PATH
from music.models import (
    Album,
    Artista,
    Canco,
    HistorialRevisio,
    SpotifyMetadata,
)


@pytest.fixture(autouse=True)
def clean_metadata_cooldown():
    """Make sure no leaked cooldown file blocks the run."""
    SHARED_PATH.unlink(missing_ok=True)
    yield
    SHARED_PATH.unlink(missing_ok=True)


@pytest.fixture
def auth_present():
    with patch(
        "ingesta.management.commands.enriquir_spotify_rebuigs.SpotifyAuth.load"
    ) as m:
        m.return_value = MagicMock(refresh_token="EXEMPLE_rt")
        yield m


@pytest.fixture
def client_mock():
    with patch(
        "ingesta.management.commands.enriquir_spotify_rebuigs.UserSpotifyClient"
    ) as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


def _make_canco_with_rejection(idx: int, isrc: str) -> Canco:
    """Build an active pendent cançó plus an HR rebuig that marks
    its artista_deezer_id as a shortlist target. The shortlist
    filter joins on `Canco.deezer_id`, so the cançó also needs a
    deezer_id."""
    a = Artista.objects.create(
        nom=f"EXEMPLE Artist {idx}",
        aprovat=False,
        pendent_review=True,
    )
    al = Album.objects.create(artista=a, nom=f"EXEMPLE Album {idx}")
    canco_deezer_id = 20000 + idx
    c = Canco.objects.create(
        artista=a,
        album=al,
        nom=f"EXEMPLE Cançó {idx}",
        isrc=isrc,
        deezer_id=canco_deezer_id,
        verificada=False,
        activa=True,
        data_llancament=date(2026, 1, 1),
    )
    HistorialRevisio.objects.create(
        canco_nom=c.nom,
        artista_nom=a.nom,
        artista_deezer_id=10000 + idx,
        canco_deezer_id=canco_deezer_id,
        canco_isrc=isrc,
        decisio="rebutjada",
        motiu="desvincular_album",
    )
    return c


@pytest.mark.django_db
def test_search_isrc_uri_is_stripped_before_get_track(auth_present, client_mock):
    """`search_isrc` returns a Spotify URI. The next call to
    `get_track` MUST receive the bare ID, NOT the URI. Spotify's
    `/v1/tracks/<id>` endpoint returns 400 on the URI form."""
    c = _make_canco_with_rejection(idx=1, isrc="ZZ00X0000001")

    track_id = "7wxYUjErY7HL6x7aFKRcso"
    spotify_uri = f"spotify:track:{track_id}"

    client_mock.search_isrc.return_value = spotify_uri
    client_mock.get_track.return_value = {
        "id": track_id,
        "name": "Track name",
        "duration_ms": 200000,
        "artists": [{"id": "ARTIST_ID_1", "name": "EXEMPLE Artist 1"}],
    }
    client_mock.get_artist.return_value = {
        "id": "ARTIST_ID_1",
        "name": "EXEMPLE Artist 1",
        "genres": [],
        "images": [],
    }

    call_command("enriquir_spotify_rebuigs", limit=1, shortlist_only=True)

    # The bare ID, not the URI, must reach get_track.
    client_mock.get_track.assert_called_once_with(track_id)
    # And SpotifyMetadata persists the bare ID too (downstream the
    # playlist sync builds `spotify:track:<id>` URIs from this
    # value and would double-up the prefix otherwise).
    sm = SpotifyMetadata.objects.get(canco=c)
    assert sm.spotify_id == track_id
    assert sm.enrichment_status == SpotifyMetadata.STATUS_FOUND


@pytest.mark.django_db
def test_search_returns_none_means_not_found_no_track_call(auth_present, client_mock):
    """When `search_isrc` returns None the command must NOT call
    `get_track` (avoids a spurious 4xx) and must mark the cançó
    `not_found`."""
    c = _make_canco_with_rejection(idx=2, isrc="ZZ00X0000002")
    client_mock.search_isrc.return_value = None

    call_command("enriquir_spotify_rebuigs", limit=1, shortlist_only=True)

    client_mock.get_track.assert_not_called()
    sm = SpotifyMetadata.objects.get(canco=c)
    assert sm.enrichment_status == SpotifyMetadata.STATUS_NOT_FOUND
