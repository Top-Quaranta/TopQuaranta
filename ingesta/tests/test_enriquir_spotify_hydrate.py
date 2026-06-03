"""Process B phase 2: hydration of manual Spotify links (no /search).

A staff-pasted manual link lands as `status=manual, enriched_at=NULL`
(pending). The enrichment cron's phase 2 hydrates it from the KNOWN id
via get_track + get_artist — never `/v1/search` — preserving the
`manual` status and recomputing dispersion. A get_track 404 keeps the
row `manual` with `enriched_at` stamped (the "failed hydration" state),
so it is not retried.

Mocks the Spotify client so no real calls fire.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from ingesta.clients.spotify_metadata_cooldown import SHARED_PATH as COOLDOWN_FILE
from ingesta.management.commands.enriquir_spotify import Command as EnrichCommand
from music.models import Album, Artista, Canco, SpotifyMetadata

MANUAL_ID = "4cOdK2wGLETKBW3PvgPWqT"


@pytest.fixture(autouse=True)
def clean_cooldown_file():
    COOLDOWN_FILE.unlink(missing_ok=True)
    yield
    COOLDOWN_FILE.unlink(missing_ok=True)


@pytest.fixture
def auth_present():
    with patch("ingesta.management.commands.enriquir_spotify.SpotifyAuth.load") as m:
        m.return_value = MagicMock(refresh_token="EXEMPLE_rt")
        yield m


@pytest.fixture
def client_mock():
    with patch("ingesta.management.commands.enriquir_spotify.UserSpotifyClient") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


def _track_payload(spotify_id, artist_id):
    return {
        "id": spotify_id,
        "name": f"EXEMPLE Track {spotify_id}",
        "duration_ms": 200000,
        "explicit": False,
        "is_playable": True,
        "album": {
            "album_type": "single",
            "release_date": "2026-01-19",
            "images": [{"url": "https://e/640.jpg", "width": 640, "height": 640}],
        },
        "artists": [{"id": artist_id, "name": "EXEMPLE Spotify Name"}],
    }


def _make_manual_canco(spotify_id=MANUAL_ID):
    a = Artista.objects.create(nom="EXEMPLE H", lastfm_nom="EXEMPLE H")
    al = Album.objects.create(artista=a, nom="EXEMPLE H Al")
    c = Canco.objects.create(
        artista=a, album=al, nom="EXEMPLE H C", isrc="ZZHY0000001", verificada=True
    )
    SpotifyMetadata.objects.create(
        canco=c,
        spotify_id=spotify_id,
        enrichment_status=SpotifyMetadata.STATUS_MANUAL,
        enriched_at=None,  # pending hydration
    )
    return c


@pytest.mark.django_db
def test_hydration_fills_artist_without_search(auth_present, client_mock):
    c = _make_manual_canco()
    client_mock.get_track.return_value = _track_payload(MANUAL_ID, "ART9")
    client_mock.get_artist.return_value = {
        "id": "ART9",
        "name": "EXEMPLE",
        "genres": [],
    }

    # limit=0 so phase 1 (/search) has no candidates; only phase 2 runs.
    call_command("enriquir_spotify", limit=0, hydrate_limit=10)

    # NEVER calls /search for a manual link.
    client_mock.search_isrc.assert_not_called()
    client_mock.get_track.assert_called_once_with(MANUAL_ID)

    sm = c.spotify
    sm.refresh_from_db()
    assert sm.enrichment_status == SpotifyMetadata.STATUS_MANUAL  # provenance kept
    assert sm.spotify_id == MANUAL_ID  # never re-resolved
    assert sm.spotify_artist_id == "ART9"  # hydrated
    assert sm.enriched_at is not None  # no longer pending
    assert sm.album_type == "single"

    # Dispersion recomputed for the manual link's artista.
    c.artista.refresh_from_db()
    assert c.artista.spotify_artist_dispersio == 1

    # No longer a hydration candidate.
    cands = EnrichCommand()._select_hydration_candidates(limit=50)
    assert c.pk not in {x.pk for x in cands}


@pytest.mark.django_db
def test_hydration_404_marks_failed_keeps_manual(auth_present, client_mock):
    c = _make_manual_canco()
    client_mock.get_track.return_value = None  # bad / taken-down id

    call_command("enriquir_spotify", limit=0, hydrate_limit=10)

    client_mock.search_isrc.assert_not_called()
    sm = c.spotify
    sm.refresh_from_db()
    # Kept as manual (NOT flipped to not_found), id preserved, stamped.
    assert sm.enrichment_status == SpotifyMetadata.STATUS_MANUAL
    assert sm.spotify_id == MANUAL_ID
    assert sm.spotify_artist_id == ""
    assert sm.enriched_at is not None  # attempted → not retried

    # Dropped from the hydration queue (enriched_at now set).
    cands = EnrichCommand()._select_hydration_candidates(limit=50)
    assert c.pk not in {x.pk for x in cands}
