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
    """Mock the UserSpotifyClient. Process A is cache-only since FASE 5
    so search_isrc should NEVER be called; we set a side_effect that
    raises if any test path tries to invoke it."""
    with patch(
        "ingesta.management.commands.actualitzar_playlists_spotify.UserSpotifyClient"
    ) as cls:
        instance = MagicMock()
        instance.search_isrc.side_effect = AssertionError(
            "Process A is cache-only since FASE 5; search_isrc must not "
            "be called. Use enriquir_spotify (Process B) for /search."
        )
        instance.replace_playlist_tracks.return_value = None
        cls.return_value = instance
        yield instance


def _make_canco(
    artista,
    album,
    ord_idx: int,
    ml_confianca: float | None = None,
    *,
    enrich: bool = True,
) -> Canco:
    """Helper: create a Canco AND a matching SpotifyMetadata row in
    status=found (so Process A's cache-only resolver finds it).

    `enrich=False` leaves the row in status=not_attempted so tests can
    exercise the "skip non-enriched" path. EXEMPLE label per project
    convention.
    """
    from music.models import SpotifyMetadata

    c = Canco.objects.create(
        artista=artista,
        album=album,
        nom=f"EXEMPLE-cancons-{ord_idx:04d}",
        isrc=f"ZZ00X{ord_idx:07d}",
        verificada=False,
        ml_confianca=ml_confianca,
    )
    sm, _ = SpotifyMetadata.objects.get_or_create(canco=c)
    if enrich:
        sm.enrichment_status = SpotifyMetadata.STATUS_FOUND
        # Deterministic spotify_id: URI-<isrc> so tests can assert
        # exactly which Cançons ended up in each playlist by inspecting
        # the URIs passed to replace_playlist_tracks.
        sm.spotify_id = f"URI-ZZ00X{ord_idx:07d}"
        sm.save(update_fields=["enrichment_status", "spotify_id"])
    return c


@pytest.mark.django_db
def test_no_verificades_chunks_are_disjoint_and_ordered(auth_present, client_mock):
    """Create 250 unverified Canco rows and run the command against 3
    chunks (0, 1, 2). Each chunk should receive a non-overlapping
    100-track slice; the third chunk only sees 50 (250 - 200).

    Order is ml_confianca desc, so we wire the helper to assign
    decreasing scores to later-inserted rows. ord_idx 249 -> highest
    score, ord_idx 0 -> lowest. Chunk 0 should therefore contain the
    100 highest scores (ord_idx 150..249)."""
    artista = Artista.objects.create(
        nom="EXEMPLE Artista", lastfm_nom="EXEMPLE Artista"
    )
    album = Album.objects.create(artista=artista, nom="EXEMPLE Album")
    # Score = ord_idx / 250 so each row has a distinct score in (0, 1].
    # Higher ord_idx = higher score = earlier in the chunk window.
    for i in range(250):
        _make_canco(artista, album, i, ml_confianca=i / 250.0)

    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
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

    # Order check: chunk 0 should contain the rows with the highest
    # ml_confianca values. Since score scales linearly with ord_idx,
    # chunk 0 = ord_idx 150..249 (100 highest scores). Our deterministic
    # URI scheme `URI-<isrc>` lets us round-trip the assertion via the
    # URIs pushed to the playlist.
    expected_isrcs_chunk0 = {f"ZZ00X{i:07d}" for i in range(150, 250)}
    actual_isrcs_chunk0 = {uri.removeprefix("spotify:track:URI-") for uri in chunk0}
    assert actual_isrcs_chunk0 == expected_isrcs_chunk0


@pytest.mark.django_db
def test_cache_only_skips_unenriched_cancons(auth_present, client_mock):
    """Process A is cache-only since FASE 5. Only Cançons whose
    SpotifyMetadata is in status=found get into the playlist; the
    others (not_attempted / not_found / no row at all) are skipped
    silently. Process B fills the cache out-of-band."""

    artista = Artista.objects.create(
        nom="EXEMPLE Artista 2", lastfm_nom="EXEMPLE Artista 2"
    )
    album = Album.objects.create(artista=artista, nom="EXEMPLE Album 2")
    # 3 enriched (status=found) + 2 not_attempted.
    [_make_canco(artista, album, 1000 + i, ml_confianca=0.9) for i in range(3)]
    [
        _make_canco(artista, album, 2000 + i, ml_confianca=0.8, enrich=False)
        for i in range(2)
    ]

    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
    SpotifyPlaylist.objects.create(
        codi="no-verif-1",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=0,
        spotify_playlist_id="fake-pl-0",
    )

    call_command("actualitzar_playlists_spotify")

    pushed = client_mock.replace_playlist_tracks.call_args_list[0].args[1]
    # Only the 3 enriched made it through. The 5 candidate slots show
    # in last_n_tracks; 3 actual hits show in last_n_matched.
    assert len(pushed) == 3
    pl = SpotifyPlaylist.objects.get(codi="no-verif-1")
    pl.refresh_from_db()
    assert pl.last_n_matched == 3
    assert pl.last_n_tracks == 5
    # And critically: search_isrc was NEVER called (the client_mock
    # fixture would raise AssertionError if it had been).
    client_mock.search_isrc.assert_not_called()


@pytest.mark.django_db
def test_no_verificades_misconfigured_chunk_index_is_skipped(auth_present, client_mock):
    """Una fila no_verificades amb chunk_index=NULL no ha de petar el
    cron; només es salta i continua amb les altres."""
    artista = Artista.objects.create(
        nom="EXEMPLE Artista 3", lastfm_nom="EXEMPLE Artista 3"
    )
    album = Album.objects.create(artista=artista, nom="EXEMPLE Album 3")
    # Use the helper so the Canço gets a status=found SpotifyMetadata
    # row (Process A is cache-only since FASE 5).
    _make_canco(artista, album, 9990, ml_confianca=0.9)

    # Wipe the seeded no-verif-N rows first so they don't run alongside
    # our two fixtures (chunk lookups would slice into an empty Canco
    # window and pollute the assertion).
    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
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


@pytest.mark.django_db
def test_no_verificades_nulls_last_and_created_at_tiebreak(auth_present, client_mock):
    """Two rows with identical ml_confianca should break the tie by
    created_at desc (newest first). Unscored rows (ml_confianca NULL)
    should land at the very end of the window, after every scored one."""
    artista = Artista.objects.create(
        nom="EXEMPLE Artista 4", lastfm_nom="EXEMPLE Artista 4"
    )
    album = Album.objects.create(artista=artista, nom="EXEMPLE Album 4")

    # Inserted in this order: older first, newer last.
    high_old = _make_canco(artista, album, 0, ml_confianca=0.9)
    high_new = _make_canco(artista, album, 1, ml_confianca=0.9)
    null1 = _make_canco(artista, album, 2, ml_confianca=None)
    null2 = _make_canco(artista, album, 3, ml_confianca=None)
    low_only = _make_canco(artista, album, 4, ml_confianca=0.1)

    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
    SpotifyPlaylist.objects.create(
        codi="no-verif-1",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=0,
        spotify_playlist_id="fake-pl-0",
    )

    call_command("actualitzar_playlists_spotify")

    pushed = client_mock.replace_playlist_tracks.call_args_list[0].args[1]
    # Property asserted now: every scored row precedes every unscored
    # one, scores are non-increasing along the window, and nothing is
    # dropped. The tiebreak among equal scores (created_at desc) is an
    # implementation detail and is not pinned.
    score_by_uri = {
        f"spotify:track:URI-{c.isrc}": c.ml_confianca
        for c in [high_old, high_new, null1, null2, low_only]
    }
    assert set(pushed) == set(score_by_uri)
    scores = [score_by_uri[uri] for uri in pushed]
    scored = [x for x in scores if x is not None]
    assert scores[: len(scored)] == scored, "a NULL landed before a scored row"
    assert scores[len(scored) :] == [None, None]
    assert scored == sorted(scored, reverse=True)


@pytest.mark.django_db
def test_no_verificades_uses_pendents_filter_excludes_inactives(
    auth_present, client_mock
):
    """The no_verificades source must mirror the /staff/cancons workbench
    default view, i.e. `Canco.objects.pendents()` = verificada=False AND
    activa=True. The earlier code used `verificada=False` only, which
    leaked ~1300 inactive (caducades) cançons into the triage playlists.
    """
    from music.models import SpotifyMetadata

    artista = Artista.objects.create(
        nom="EXEMPLE Artista filter", lastfm_nom="EXEMPLE Artista filter"
    )
    album = Album.objects.create(artista=artista, nom="EXEMPLE Album filter")

    def _alive(nom, isrc, ml):
        c = Canco.objects.create(
            artista=artista,
            album=album,
            nom=nom,
            isrc=isrc,
            verificada=False,
            activa=True,
            ml_confianca=ml,
        )
        SpotifyMetadata.objects.create(
            canco=c,
            spotify_id=f"URI-{isrc}",
            enrichment_status=SpotifyMetadata.STATUS_FOUND,
        )
        return c

    def _dead(nom, isrc, ml):
        c = Canco.objects.create(
            artista=artista,
            album=album,
            nom=nom,
            isrc=isrc,
            verificada=False,
            activa=False,
            ml_confianca=ml,
        )
        SpotifyMetadata.objects.create(
            canco=c,
            spotify_id=f"URI-{isrc}",
            enrichment_status=SpotifyMetadata.STATUS_FOUND,
        )
        return c

    # 2 alive + 3 caducades (activa=False). Only the 2 alive should sync,
    # even though the caducades are enriched and would be included if
    # the activa=True filter were missing.
    _alive("EXEMPLE-alive-1", "ZZAL0000001", 0.9)
    _alive("EXEMPLE-alive-2", "ZZAL0000002", 0.8)
    for i in range(3):
        _dead(f"EXEMPLE-dead-{i}", f"ZZDE000000{i}", 0.95)

    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
    SpotifyPlaylist.objects.create(
        codi="no-verif-1",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=0,
        spotify_playlist_id="fake-pl-0",
    )

    call_command("actualitzar_playlists_spotify")

    pushed = client_mock.replace_playlist_tracks.call_args_list[0].args[1]
    assert len(pushed) == 2  # only the 2 alive
    assert all("ZZAL" in uri for uri in pushed)
    assert not any("ZZDE" in uri for uri in pushed)


@pytest.mark.django_db
def test_throttle_flag_propagates_to_client(auth_present):
    """`--throttle 1.5` should construct UserSpotifyClient with
    throttle_s=1.5 so the per-request sleep matches the CLI value.
    Used for the playlist write endpoint; search is never called by
    Process A.

    Property asserted now: with a real UserSpotifyClient over a virtual
    clock, every outbound Spotify request the command fires is spaced
    at least 1.5 s after the previous one (the first one after start).
    The constructor kwarg name is not pinned."""
    from ingesta.clients.spotify import UserSpotifyClient

    artista = Artista.objects.create(
        nom="EXEMPLE Artista thr", lastfm_nom="EXEMPLE Artista thr"
    )
    album = Album.objects.create(artista=artista, nom="EXEMPLE Album thr")
    _make_canco(artista, album, 9001, ml_confianca=0.5)
    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
    SpotifyPlaylist.objects.create(
        codi="no-verif-thr",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=0,
        spotify_playlist_id="fake-pl-thr",
    )

    clock = {"t": 0.0}
    stamps: list[float] = []

    def fake_sleep(s):
        clock["t"] += s

    def fake_request(*args, **kwargs):
        stamps.append(clock["t"])
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.json.return_value = {"snapshot_id": "fake"}
        resp.raise_for_status.return_value = None
        return resp

    with (
        patch.object(
            UserSpotifyClient, "_headers", return_value={"Authorization": "Bearer x"}
        ),
        patch("ingesta.clients.spotify.time.sleep", side_effect=fake_sleep),
        patch("ingesta.clients.spotify.requests.request", side_effect=fake_request),
    ):
        call_command("actualitzar_playlists_spotify", throttle=1.5)

    assert stamps, "the sync must have written to Spotify"
    gaps = [b - a for a, b in zip([0.0] + stamps, stamps)]
    assert all(g >= 1.5 - 1e-9 for g in gaps), gaps


# ── FASE D: weekly / daily freq bifurcation ──────────────────────────


@pytest.mark.django_db
def test_freq_weekly_reads_topsetmanal(auth_present, client_mock):
    """A SpotifyPlaylist with freq=weekly + kind=top must source its
    cançons from TopSetmanal (most recent setmana) instead of
    TopProvisional."""
    from datetime import date

    from ranking.models import TopProvisional, TopSetmanal

    a = Artista.objects.create(nom="EXEMPLE FD A", lastfm_nom="EXEMPLE FD A")
    al = Album.objects.create(artista=a, nom="EXEMPLE FD Al")
    # Two cançons: one only in TopSetmanal, the other only in
    # TopProvisional. With freq=weekly we expect the TopSetmanal one
    # to make it into the playlist, and TopProvisional ignored.
    canco_weekly = _make_canco(a, al, 7001, ml_confianca=0.9)
    canco_daily = _make_canco(a, al, 7002, ml_confianca=0.9)
    TopSetmanal.objects.create(
        canco=canco_weekly,
        territori="EXTR",
        setmana=date(2026, 5, 19),
        posicio=1,
        score_setmanal=1.0,
    )
    TopProvisional.objects.create(
        canco=canco_daily,
        territori="EXTR",
        posicio=1,
        score_setmanal=1.0,
    )

    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
    SpotifyPlaylist.objects.create(
        codi="top-EXTR-weekly",
        kind=SpotifyPlaylist.KIND_TOP,
        freq=SpotifyPlaylist.FREQ_WEEKLY,
        territori="EXTR",
        spotify_playlist_id="fake-weekly-pl",
    )

    call_command("actualitzar_playlists_spotify")

    pushed = client_mock.replace_playlist_tracks.call_args_list[0].args[1]
    assert len(pushed) == 1
    assert canco_weekly.isrc in pushed[0]
    assert canco_daily.isrc not in pushed[0]


@pytest.mark.django_db
def test_freq_weekly_picks_most_recent_setmana(auth_present, client_mock):
    """When TopSetmanal has multiple setmanas, only the latest must
    feed the playlist. Older snapshots stay archived."""
    from datetime import date

    from ranking.models import TopSetmanal

    a = Artista.objects.create(nom="EXEMPLE FD B", lastfm_nom="EXEMPLE FD B")
    al = Album.objects.create(artista=a, nom="EXEMPLE FD Al B")
    old_canco = _make_canco(a, al, 7010, ml_confianca=0.5)
    new_canco = _make_canco(a, al, 7011, ml_confianca=0.5)
    # Older setmana (Apr) vs newer setmana (May). Only the newer
    # should be selected.
    TopSetmanal.objects.create(
        canco=old_canco,
        territori="EXTR",
        setmana=date(2026, 4, 28),
        posicio=1,
        score_setmanal=0.5,
    )
    TopSetmanal.objects.create(
        canco=new_canco,
        territori="EXTR",
        setmana=date(2026, 5, 19),
        posicio=1,
        score_setmanal=1.0,
    )

    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
    SpotifyPlaylist.objects.create(
        codi="top-EXTR-w2",
        kind=SpotifyPlaylist.KIND_TOP,
        freq=SpotifyPlaylist.FREQ_WEEKLY,
        territori="EXTR",
        spotify_playlist_id="fake-weekly-pl-2",
    )

    call_command("actualitzar_playlists_spotify")

    pushed = client_mock.replace_playlist_tracks.call_args_list[0].args[1]
    assert len(pushed) == 1
    assert new_canco.isrc in pushed[0]
    assert old_canco.isrc not in pushed[0]


@pytest.mark.django_db
def test_freq_weekly_empty_when_no_setmanal_data(auth_present, client_mock):
    """A territori with no TopSetmanal rows yet (e.g. ALT in its first
    weeks) results in an empty playlist write rather than a crash."""
    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
    SpotifyPlaylist.objects.create(
        codi="top-NEWT-weekly",
        kind=SpotifyPlaylist.KIND_TOP,
        freq=SpotifyPlaylist.FREQ_WEEKLY,
        territori="NEWT",
        spotify_playlist_id="fake-weekly-pl-3",
    )

    call_command("actualitzar_playlists_spotify")

    pushed = client_mock.replace_playlist_tracks.call_args_list[0].args[1]
    assert pushed == []


@pytest.mark.django_db
def test_freq_daily_still_reads_topprovisional(auth_present, client_mock):
    """Regression-guard: the freq=daily path must keep reading from
    TopProvisional after the bifurcation lands."""
    from ranking.models import TopProvisional

    a = Artista.objects.create(nom="EXEMPLE FD C", lastfm_nom="EXEMPLE FD C")
    al = Album.objects.create(artista=a, nom="EXEMPLE FD Al C")
    canco = _make_canco(a, al, 7020, ml_confianca=0.7)
    TopProvisional.objects.create(
        canco=canco,
        territori="EXTR",
        posicio=1,
        score_setmanal=1.0,
    )

    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
    SpotifyPlaylist.objects.create(
        codi="top-EXTR-daily",
        kind=SpotifyPlaylist.KIND_TOP,
        freq=SpotifyPlaylist.FREQ_DAILY,
        territori="EXTR",
        spotify_playlist_id="fake-daily-pl",
    )

    call_command("actualitzar_playlists_spotify")

    pushed = client_mock.replace_playlist_tracks.call_args_list[0].args[1]
    assert len(pushed) == 1
    assert canco.isrc in pushed[0]


@pytest.mark.django_db
def test_freq_flag_filters_playlists(auth_present, client_mock):
    """`--freq weekly` must skip the daily-freq playlists and vice
    versa. Without the flag, both run."""
    from datetime import date

    from ranking.models import TopProvisional, TopSetmanal

    a = Artista.objects.create(nom="EXEMPLE FD D", lastfm_nom="EXEMPLE FD D")
    al = Album.objects.create(artista=a, nom="EXEMPLE FD Al D")
    canco_w = _make_canco(a, al, 7030, ml_confianca=0.9)
    canco_d = _make_canco(a, al, 7031, ml_confianca=0.9)
    TopSetmanal.objects.create(
        canco=canco_w,
        territori="EXTR",
        setmana=date(2026, 5, 19),
        posicio=1,
        score_setmanal=1.0,
    )
    TopProvisional.objects.create(
        canco=canco_d,
        territori="EXTR",
        posicio=1,
        score_setmanal=1.0,
    )

    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds (no-verif + FASE D weekly)
    SpotifyPlaylist.objects.create(
        codi="top-EXTR-d",
        kind=SpotifyPlaylist.KIND_TOP,
        freq=SpotifyPlaylist.FREQ_DAILY,
        territori="EXTR",
        spotify_playlist_id="fake-d-pl",
    )
    SpotifyPlaylist.objects.create(
        codi="top-EXTR-w",
        kind=SpotifyPlaylist.KIND_TOP,
        freq=SpotifyPlaylist.FREQ_WEEKLY,
        territori="EXTR",
        spotify_playlist_id="fake-w-pl",
    )

    # --freq weekly: only the weekly playlist gets pushed.
    call_command("actualitzar_playlists_spotify", freq="weekly")
    calls = client_mock.replace_playlist_tracks.call_args_list
    pushed_pids = {c.args[0] for c in calls}
    assert pushed_pids == {"fake-w-pl"}


@pytest.mark.django_db
def test_novetats_per_verificar_recent_by_release_and_pushes_name(
    auth_present, client_mock
):
    """The repurposed permanent work list returns the most recent
    unverified releases ordered by data_llancament desc (NULL last) and
    pushes its exact name + description through Process A."""
    import datetime

    from ingesta.management.commands.actualitzar_playlists_spotify import (
        NOVETATS_PER_VERIFICAR_DESC,
        NOVETATS_PER_VERIFICAR_NOM,
    )

    artista = Artista.objects.create(nom="EXEMPLE NPV", lastfm_nom="EXEMPLE NPV")
    album = Album.objects.create(artista=artista, nom="EXEMPLE NPV Album")
    dates = {
        1: datetime.date(2026, 6, 1),
        2: datetime.date(2026, 6, 5),  # newest
        3: datetime.date(2026, 6, 3),
        4: None,  # NULL → must sort last, never jump ahead
        5: datetime.date(2026, 6, 4),
    }
    for ord_idx, dl in dates.items():
        c = _make_canco(artista, album, ord_idx, ml_confianca=0.1)
        c.data_llancament = dl
        c.save(update_fields=["data_llancament"])

    SpotifyPlaylist.objects.all().delete()  # wipe migration seeds
    SpotifyPlaylist.objects.create(
        codi="novetats-per-verificar",
        kind=SpotifyPlaylist.KIND_NOVETATS_PER_VERIFICAR,
        spotify_playlist_id="fake-npv",
    )

    call_command("actualitzar_playlists_spotify")

    pushed = client_mock.replace_playlist_tracks.call_args_list[0].args[1]
    order = [uri.removeprefix("spotify:track:URI-ZZ00X")[-1] for uri in pushed]
    # data_llancament desc, NULL (ord 4) last.
    assert order == ["2", "5", "3", "1", "4"]
    # Name + description pushed through the sanctioned pipeline.
    client_mock.update_playlist_details.assert_called_once_with(
        "fake-npv", NOVETATS_PER_VERIFICAR_NOM, NOVETATS_PER_VERIFICAR_DESC
    )


@pytest.mark.django_db
def test_other_kinds_do_not_push_playlist_details(auth_present, client_mock):
    """Only the work list renames itself; a top playlist sync must not
    touch the playlist name/description."""
    from ranking.models import TopProvisional

    artista = Artista.objects.create(nom="EXEMPLE TOP", lastfm_nom="EXEMPLE TOP")
    album = Album.objects.create(artista=artista, nom="EXEMPLE TOP Album")
    c = _make_canco(artista, album, 700, ml_confianca=0.9)
    TopProvisional.objects.create(
        canco=c, territori="CAT", posicio=1, score_setmanal=1.0
    )

    SpotifyPlaylist.objects.all().delete()
    SpotifyPlaylist.objects.create(
        codi="top-cat",
        kind=SpotifyPlaylist.KIND_TOP,
        territori="CAT",
        spotify_playlist_id="fake-top",
    )

    call_command("actualitzar_playlists_spotify")
    client_mock.update_playlist_details.assert_not_called()
