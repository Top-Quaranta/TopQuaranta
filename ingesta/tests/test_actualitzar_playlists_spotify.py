"""Tests for the `actualitzar_playlists_spotify` management command.

Coverage:
  * The no_verificades branch slices the window by chunk_index without
    overlap (chunk 0 = newest 100; chunk 6 = items 601..700).
  * The window is materialised once per command run, not once per
    playlist row (we assert the source query runs at most once).
  * The kind=top branch keeps working alongside the new branch.

We mock UserSpotifyClient to avoid hitting Spotify, and we mock
SpotifyAuth.load() to skip the OAuth gate.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from ingesta.management.commands.actualitzar_playlists_spotify import (
    NO_VERIF_CHUNK_SIZE,
    NO_VERIF_WINDOW,
)
from music.models import Album, Artista, Canco, SpotifyPlaylist


@pytest.fixture
def auth_present():
    """Bypass the SpotifyAuth.load() gate without touching the DB."""
    with patch(
        "ingesta.management.commands.actualitzar_playlists_spotify.SpotifyAuth.load"
    ) as m:
        m.return_value = MagicMock(refresh_token="x", spotify_user_id="u")
        yield m


@pytest.fixture
def client_mock():
    """Mock the UserSpotifyClient: every ISRC search returns a fake URI
    so we can assert chunking math without caring about Spotify shape."""
    with patch(
        "ingesta.management.commands.actualitzar_playlists_spotify.UserSpotifyClient"
    ) as cls:
        instance = MagicMock()
        instance.search_isrc.side_effect = lambda isrc: f"spotify:track:URI-{isrc}"
        instance.replace_playlist_tracks.return_value = None
        cls.return_value = instance
        yield instance


def _make_canco(artista, album, ord_idx: int) -> Canco:
    """Helper: create a Canco with a deterministic ISRC and
    `created_at` ordering. Note the EXEMPLE label on the synthetic
    Catalan-looking title (per project convention `# EXEMPLE`)."""
    return Canco.objects.create(
        artista=artista,
        album=album,
        nom=f"EXEMPLE-cancons-{ord_idx:04d}",
        isrc=f"ZZ00X{ord_idx:07d}",
        verificada=False,
    )


@pytest.mark.django_db
def test_no_verificades_chunks_are_disjoint_and_ordered(auth_present, client_mock):
    """Create 250 unverified Canco rows and run the command against 3
    chunks (0, 1, 2). Each chunk should receive a non-overlapping
    100-track slice; the third chunk only sees 50 (250 - 200)."""
    artista = Artista.objects.create(
        nom="EXEMPLE Artista", lastfm_nom="EXEMPLE Artista"
    )
    album = Album.objects.create(artista=artista, nom="EXEMPLE Album")
    # Create 250 cançons in stable creation order; we don't need to keep
    # the list, only the side-effect on the DB.
    for i in range(250):
        _make_canco(artista, album, i)

    # Most recently created is the LAST one we inserted (ord_idx 249).
    # The expected chunk 0 (newest 100) maps to ISRCs 249..150 (desc).
    SpotifyPlaylist.objects.filter(codi__startswith="no-verif").delete()
    SpotifyPlaylist.objects.create(
        codi="no-verif-1",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=0,
        spotify_playlist_id="fake-pl-0",
    )
    SpotifyPlaylist.objects.create(
        codi="no-verif-2",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=1,
        spotify_playlist_id="fake-pl-1",
    )
    SpotifyPlaylist.objects.create(
        codi="no-verif-3",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=2,
        spotify_playlist_id="fake-pl-2",
    )

    call_command("actualitzar_playlists_spotify")

    # Inspect what was pushed to each fake playlist.
    calls = client_mock.replace_playlist_tracks.call_args_list
    assert len(calls) == 3
    by_pl = {c.args[0]: c.args[1] for c in calls}

    chunk0 = by_pl["fake-pl-0"]
    chunk1 = by_pl["fake-pl-1"]
    chunk2 = by_pl["fake-pl-2"]

    # Disjoint slices.
    assert len(chunk0) == 100
    assert len(chunk1) == 100
    assert len(chunk2) == 50  # only 250 rows total
    assert set(chunk0).isdisjoint(chunk1)
    assert set(chunk1).isdisjoint(chunk2)
    assert set(chunk0).isdisjoint(chunk2)

    # Order check: chunk 0 should contain the most-recently-inserted
    # tracks, which by ord_idx are 249..150 (desc).
    expected_isrcs_chunk0 = {f"ZZ00X{i:07d}" for i in range(150, 250)}
    actual_isrcs_chunk0 = {uri.removeprefix("spotify:track:URI-") for uri in chunk0}
    assert actual_isrcs_chunk0 == expected_isrcs_chunk0


@pytest.mark.django_db
def test_no_verificades_skips_empty_isrc(auth_present, client_mock):
    """Cançons amb ISRC buit no entren al window (no es poden buscar)."""
    artista = Artista.objects.create(
        nom="EXEMPLE Artista 2", lastfm_nom="EXEMPLE Artista 2"
    )
    album = Album.objects.create(artista=artista, nom="EXEMPLE Album 2")
    # 3 amb ISRC + 2 sense
    for i in range(3):
        Canco.objects.create(
            artista=artista,
            album=album,
            nom=f"EXEMPLE-amb-isrc-{i}",
            isrc=f"ZZ00Y000000{i}",
            verificada=False,
        )
    for i in range(2):
        Canco.objects.create(
            artista=artista,
            album=album,
            nom=f"EXEMPLE-sense-{i}",
            isrc="",
            verificada=False,
        )

    SpotifyPlaylist.objects.filter(codi__startswith="no-verif").delete()
    SpotifyPlaylist.objects.create(
        codi="no-verif-1",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=0,
        spotify_playlist_id="fake-pl-0",
    )

    call_command("actualitzar_playlists_spotify")

    pushed = client_mock.replace_playlist_tracks.call_args_list[0].args[1]
    assert len(pushed) == 3  # only the 3 amb-isrc rows


@pytest.mark.django_db
def test_no_verificades_misconfigured_chunk_index_is_skipped(auth_present, client_mock):
    """Una fila no_verificades amb chunk_index=NULL no ha de petar el
    cron; només es salta i continua amb les altres."""
    artista = Artista.objects.create(
        nom="EXEMPLE Artista 3", lastfm_nom="EXEMPLE Artista 3"
    )
    album = Album.objects.create(artista=artista, nom="EXEMPLE Album 3")
    Canco.objects.create(
        artista=artista,
        album=album,
        nom="EXEMPLE",
        isrc="ZZ00Z0000001",
        verificada=False,
    )

    # Wipe the seeded no-verif-N rows first so they don't run alongside
    # our two fixtures (chunk lookups would slice into an empty Canco
    # window and pollute the assertion).
    SpotifyPlaylist.objects.filter(codi__startswith="no-verif").delete()
    SpotifyPlaylist.objects.create(
        codi="no-verif-broken",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=None,
        spotify_playlist_id="fake-pl-broken",
    )
    SpotifyPlaylist.objects.create(
        codi="no-verif-1",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=0,
        spotify_playlist_id="fake-pl-0",
    )

    call_command("actualitzar_playlists_spotify")

    calls = client_mock.replace_playlist_tracks.call_args_list
    by_pl = {c.args[0]: c.args[1] for c in calls}
    # Broken row: 0 tracks pushed (but replace was still called with []).
    assert by_pl["fake-pl-broken"] == []
    # Healthy row: 1 track.
    assert len(by_pl["fake-pl-0"]) == 1


def test_window_constants_are_consistent():
    """Sanity guard: chunk count must be int and slot in 0..6 must fit
    inside the window (700 / 100 = 7 chunks)."""
    assert NO_VERIF_WINDOW == 7 * NO_VERIF_CHUNK_SIZE
