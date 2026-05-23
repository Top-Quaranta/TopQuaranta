"""Tests for the Process B enrichment command.

Mocks search_isrc / get_track / get_artist so no real Spotify calls
fire. Covers:
  * happy path -> status=found with the full SpotifyMetadata populated.
  * search no match -> status=not_found, no track/artist call made.
  * --limit respected.
  * Compound ordering: public by latest SenyalDiari playcount desc,
    pending by ml_confianca desc (verified by which Cançons get
    processed first when limit is below total).
  * RateLimitedError mid-run aborts cleanly, work-done-so-far is
    persisted.
  * --target-playlists narrows the pool to the active playlists.
  * Collaboration (artists list >1): principal = artists[0], full
    list goes to spotify_artist_ids.
  * Dispersion is recomputed for only the affected artistas.

EXEMPLE labels per project convention.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import CommandError, call_command

from ingesta.clients.spotify import RateLimitedError
from ingesta.management.commands.enriquir_spotify import COOLDOWN_FILE
from music.models import Album, Artista, Canco, SpotifyMetadata, SpotifyPlaylist
from ranking.models import SenyalDiari, TopProvisional


@pytest.fixture(autouse=True)
def clean_cooldown_file():
    """Ensure no cooldown file leaks between tests."""
    COOLDOWN_FILE.unlink(missing_ok=True)
    yield
    COOLDOWN_FILE.unlink(missing_ok=True)


@pytest.fixture
def auth_present():
    """Skip the SpotifyAuth.load() gate."""
    with patch("ingesta.management.commands.enriquir_spotify.SpotifyAuth.load") as m:
        m.return_value = MagicMock(refresh_token="EXEMPLE_rt")
        yield m


@pytest.fixture
def client_mock():
    """A MagicMock standing in for UserSpotifyClient. Tests override
    its search_isrc / get_track / get_artist behaviour per scenario."""
    with patch("ingesta.management.commands.enriquir_spotify.UserSpotifyClient") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


def _make_canco(artista, album, idx: int, *, verificada=False, ml=None) -> Canco:
    c = Canco.objects.create(
        artista=artista,
        album=album,
        nom=f"EXEMPLE-c-{idx:04d}",
        isrc=f"ZZ00X{idx:07d}",
        verificada=verificada,
        ml_confianca=ml,
    )
    # SpotifyMetadata is not auto-created via signal; in prod the 0080
    # backfill migration covers existing rows, but Cançons created AFTER
    # the migration (the test set, here) need an explicit row.
    SpotifyMetadata.objects.get_or_create(canco=c)
    return c


def _track_payload(
    spotify_id: str, isrc: str, artist_ids: list[str], names: list[str] | None = None
) -> dict:
    """Minimal but realistic /v1/tracks/{id} response."""
    names = names or [f"EXEMPLE Artist {a}" for a in artist_ids]
    return {
        "id": spotify_id,
        "name": f"EXEMPLE Track {spotify_id}",
        "duration_ms": 200000,
        "explicit": False,
        "is_playable": True,
        "track_number": 1,
        "disc_number": 1,
        "external_ids": {"isrc": isrc},
        "album": {
            "album_type": "single",
            "release_date": "2026-01-19",
            "images": [
                {"url": f"https://e/{spotify_id}/640.jpg", "width": 640, "height": 640},
            ],
        },
        "artists": [
            {"id": aid, "name": name, "uri": f"spotify:artist:{aid}"}
            for aid, name in zip(artist_ids, names)
        ],
    }


@pytest.mark.django_db
def test_happy_path_enriches_canco(auth_present, client_mock):
    """search -> uri; get_track -> payload; SpotifyMetadata filled."""
    a = Artista.objects.create(nom="EXEMPLE A", lastfm_nom="EXEMPLE A")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al")
    c = _make_canco(a, al, 1, ml=0.9)

    client_mock.search_isrc.return_value = "spotify:track:TRACK1"
    client_mock.get_track.return_value = _track_payload(
        "TRACK1", "ZZ00X0000001", ["ART1"]
    )
    client_mock.get_artist.return_value = {
        "id": "ART1",
        "name": "EXEMPLE Spotify Artist Name",
        "images": [{"url": "https://e/art.jpg", "width": 640, "height": 640}],
        "genres": [],
    }

    call_command("enriquir_spotify", limit=10)

    c.refresh_from_db()
    sm = c.spotify
    assert sm.enrichment_status == SpotifyMetadata.STATUS_FOUND
    assert sm.spotify_id == "TRACK1"
    assert sm.spotify_artist_id == "ART1"
    assert sm.spotify_artist_ids == ["ART1"]
    assert sm.spotify_artist_name == "EXEMPLE Spotify Artist Name"
    assert sm.album_type == "single"
    assert sm.release_date == "2026-01-19"
    assert sm.duration_ms == 200000
    assert sm.is_playable is True
    assert sm.enriched_at is not None
    # Legacy Canco.spotify_id stays in sync for any legacy consumer.
    assert c.spotify_id == "TRACK1"


@pytest.mark.django_db
def test_search_no_match_sets_not_found(auth_present, client_mock):
    """search returns None -> status=not_found; get_track NOT called."""
    a = Artista.objects.create(nom="EXEMPLE A2", lastfm_nom="EXEMPLE A2")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al2")
    c = _make_canco(a, al, 2, ml=0.5)

    client_mock.search_isrc.return_value = None
    client_mock.get_track.side_effect = AssertionError("should not be called")

    call_command("enriquir_spotify", limit=10)

    c.refresh_from_db()
    assert c.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_FOUND
    assert c.spotify.spotify_id == ""
    assert c.spotify.enriched_at is not None


@pytest.mark.django_db
def test_collaboration_principal_artist_is_artists0(auth_present, client_mock):
    """Track with two artists: principal = artists[0]; ids list keeps both."""
    a = Artista.objects.create(nom="EXEMPLE A3", lastfm_nom="EXEMPLE A3")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al3")
    _make_canco(a, al, 3, ml=0.8)

    client_mock.search_isrc.return_value = "spotify:track:TRACK3"
    client_mock.get_track.return_value = _track_payload(
        "TRACK3", "ZZ00X0000003", ["MAIN", "COLLAB"]
    )
    client_mock.get_artist.return_value = {
        "id": "MAIN",
        "name": "EXEMPLE Main",
        "images": [],
        "genres": [],
    }

    call_command("enriquir_spotify", limit=10)

    sm = SpotifyMetadata.objects.get(canco__isrc="ZZ00X0000003")
    assert sm.spotify_artist_id == "MAIN"
    assert sm.spotify_artist_ids == ["MAIN", "COLLAB"]
    # get_artist was called ONCE (only the principal), not per collaborator.
    assert client_mock.get_artist.call_count == 1
    client_mock.get_artist.assert_called_with("MAIN")


@pytest.mark.django_db
def test_limit_respected(auth_present, client_mock):
    """`--limit 3` processes exactly 3 cançons even if 5 are eligible."""
    a = Artista.objects.create(nom="EXEMPLE A4", lastfm_nom="EXEMPLE A4")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al4")
    for i in range(5):
        _make_canco(a, al, 100 + i, ml=0.5 + i * 0.05)

    client_mock.search_isrc.return_value = None  # all not_found, fast

    call_command("enriquir_spotify", limit=3)

    not_found = SpotifyMetadata.objects.filter(
        enrichment_status=SpotifyMetadata.STATUS_NOT_FOUND
    ).count()
    assert not_found == 3
    not_attempted = SpotifyMetadata.objects.filter(
        enrichment_status=SpotifyMetadata.STATUS_NOT_ATTEMPTED,
        canco__artista=a,
    ).count()
    assert not_attempted == 2  # the 2 unprocessed of the 5


@pytest.mark.django_db
def test_pending_ordering_by_ml_confianca_desc(auth_present, client_mock):
    """When source is the pending pool, highest ml_confianca first."""
    a = Artista.objects.create(nom="EXEMPLE A5", lastfm_nom="EXEMPLE A5")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al5")
    low = _make_canco(a, al, 200, ml=0.1)
    high = _make_canco(a, al, 201, ml=0.95)
    mid = _make_canco(a, al, 202, ml=0.5)

    client_mock.search_isrc.return_value = None

    call_command("enriquir_spotify", limit=2)

    # high + mid processed; low untouched.
    high.refresh_from_db()
    mid.refresh_from_db()
    low.refresh_from_db()
    assert high.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_FOUND
    assert mid.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_FOUND
    assert low.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_ATTEMPTED


@pytest.mark.django_db
def test_public_ordering_by_latest_senyaldiari_playcount(auth_present, client_mock):
    """Public Cançons come before pending; within public, ordered by
    latest SenyalDiari.lastfm_playcount desc."""
    a = Artista.objects.create(nom="EXEMPLE A6", lastfm_nom="EXEMPLE A6")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al6")

    pub_low = _make_canco(a, al, 300, verificada=True)
    pub_high = _make_canco(a, al, 301, verificada=True)
    pend_high_ml = _make_canco(a, al, 302, verificada=False, ml=0.99)

    today = date.today()
    SenyalDiari.objects.create(canco=pub_low, data=today, lastfm_playcount=50)
    SenyalDiari.objects.create(canco=pub_high, data=today, lastfm_playcount=900)

    client_mock.search_isrc.return_value = None

    # Limit=1 -> only the top public (highest playcount) gets processed.
    call_command("enriquir_spotify", limit=1)
    pub_high.refresh_from_db()
    pub_low.refresh_from_db()
    pend_high_ml.refresh_from_db()
    assert pub_high.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_FOUND
    assert pub_low.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_ATTEMPTED
    assert (
        pend_high_ml.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_ATTEMPTED
    )


@pytest.mark.django_db
def test_rate_limit_writes_cooldown_and_exits_cleanly(auth_present, client_mock):
    """RateLimitedError mid-run -> cooldown file written, exit 0 (no
    CommandError), but the cançons processed before the error are
    persisted (per-Canço transaction)."""
    a = Artista.objects.create(nom="EXEMPLE A7", lastfm_nom="EXEMPLE A7")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al7")
    c1 = _make_canco(a, al, 400, ml=0.9)
    c2 = _make_canco(a, al, 401, ml=0.8)
    c3 = _make_canco(a, al, 402, ml=0.7)

    def search_side_effect(isrc):
        if isrc == "ZZ00X0000402":
            raise RateLimitedError(86076, "/search")
        return None  # first two come back as not_found cheaply

    client_mock.search_isrc.side_effect = search_side_effect

    # No CommandError raised — exits cleanly so tq-health doesn't alert.
    call_command("enriquir_spotify", limit=10)

    c1.refresh_from_db()
    c2.refresh_from_db()
    c3.refresh_from_db()
    # c1 and c2 processed (not_found); c3 was the one that raised, untouched.
    assert c1.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_FOUND
    assert c2.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_FOUND
    assert c3.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_ATTEMPTED
    # Cooldown file written with a future timestamp.
    assert COOLDOWN_FILE.exists()
    from datetime import datetime

    resume_at = datetime.fromisoformat(COOLDOWN_FILE.read_text().strip())
    assert resume_at > datetime.now()


@pytest.mark.django_db
def test_target_playlists_filter(auth_present, client_mock):
    """--target-playlists restricts the source pool to Cançons in any
    active SpotifyPlaylist's window."""
    a = Artista.objects.create(nom="EXEMPLE A8", lastfm_nom="EXEMPLE A8")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al8")
    in_playlist = _make_canco(a, al, 500, ml=0.9)
    out_of_playlist = _make_canco(a, al, 501, ml=0.99)  # even higher ml

    # Wipe the seeded no-verif-N rows from migration 0078 so the
    # target-playlists branch only sees our one fixture playlist.
    # Otherwise the no_verificades branch picks the pending pool wholesale
    # and `out_of_playlist` (verificada=False) ends up inside.
    SpotifyPlaylist.objects.all().delete()
    SpotifyPlaylist.objects.create(
        codi="top-EXEMPLE",
        kind=SpotifyPlaylist.KIND_TOP,
        territori="EXTR",
        spotify_playlist_id="EXEMPLEPLAYLISTID",
    )
    TopProvisional.objects.create(
        canco=in_playlist, territori="EXTR", posicio=1, score_setmanal=1.0
    )

    client_mock.search_isrc.return_value = None

    call_command("enriquir_spotify", limit=10, target_playlists=True)

    in_playlist.refresh_from_db()
    out_of_playlist.refresh_from_db()
    assert in_playlist.spotify.enrichment_status == SpotifyMetadata.STATUS_NOT_FOUND
    # Out-of-playlist stays untouched even though its ml_confianca is higher.
    assert (
        out_of_playlist.spotify.enrichment_status
        == SpotifyMetadata.STATUS_NOT_ATTEMPTED
    )


@pytest.mark.django_db
def test_dispersion_recomputed_for_affected_artists(auth_present, client_mock):
    """After enrichment, the affected artistes have dispersion set."""
    a = Artista.objects.create(nom="EXEMPLE A9", lastfm_nom="EXEMPLE A9")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al9")
    _make_canco(a, al, 600, ml=0.9)
    _make_canco(a, al, 601, ml=0.8)

    call_count = [0]

    def search_side(isrc):
        call_count[0] += 1
        return f"spotify:track:T{call_count[0]}"

    def track_side(sid):
        # First track -> artist X, second -> artist Y (dispersion 2).
        artist_id = "ARTX" if sid == "T1" else "ARTY"
        return _track_payload(sid, f"ZZ00X{call_count[0]:07d}", [artist_id])

    client_mock.search_isrc.side_effect = search_side
    client_mock.get_track.side_effect = track_side
    client_mock.get_artist.return_value = {
        "id": "X",
        "name": "EX",
        "images": [],
        "genres": [],
    }

    call_command("enriquir_spotify", limit=10)

    a.refresh_from_db()
    assert a.spotify_artist_dispersio == 2
    assert sorted(a.spotify_artist_ids_distints) == ["ARTX", "ARTY"]
