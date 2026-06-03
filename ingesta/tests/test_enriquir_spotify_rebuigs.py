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


# ─────────────────────────── Orphan flow ─────────────────────────────


def _make_orphan_hr(idx: int, isrc: str, *, motiu="desvincular_album"):
    """Build an HR row whose `canco_deezer_id` has NO matching Canco
    (orphan), still carries an ISRC, and is on the shortlist."""
    HistorialRevisio.objects.create(
        canco_nom=f"EXEMPLE orphan {idx}",
        artista_nom=f"EXEMPLE artist orphan {idx}",
        artista_deezer_id=80000 + idx,
        canco_deezer_id=90000 + idx,
        canco_isrc=isrc,
        decisio="rebutjada",
        motiu=motiu,
    )


@pytest.mark.django_db
def test_orphan_flow_resolves_isrc_and_propagates_to_all_hr_rows(
    auth_present, client_mock
):
    """One `/v1/search` per ISRC. The resolved spotify_artist_id
    lands on EVERY HR row that carries that ISRC, regardless of
    Canco existence. `spotify_lookup_at` is stamped so the next
    run will not retry the same ISRC."""
    isrc = "ZZ00X0000100"
    # Three HR rows on the same ISRC -> deduped to one search.
    for i in range(3):
        _make_orphan_hr(idx=100 + i, isrc=isrc)

    client_mock.search_isrc_principal_artist.return_value = "SPOTIFY_ART_42"

    call_command(
        "enriquir_spotify_rebuigs",
        limit=10,
        shortlist_only=True,
        include_orfes=True,
    )

    # Single search per ISRC.
    assert client_mock.search_isrc_principal_artist.call_count == 1
    client_mock.search_isrc_principal_artist.assert_called_once_with(isrc)
    # `get_track` / `get_artist` are NOT called for orphans.
    client_mock.get_track.assert_not_called()
    client_mock.get_artist.assert_not_called()
    # All three HR rows now carry the artista_spotify_id and the
    # lookup timestamp.
    rows = HistorialRevisio.objects.filter(canco_isrc=isrc)
    assert rows.count() == 3
    for row in rows:
        assert row.artista_spotify_id == "SPOTIFY_ART_42"
        assert row.spotify_lookup_at is not None


@pytest.mark.django_db
def test_orphan_flow_not_found_stamps_lookup_without_overwriting(
    auth_present, client_mock
):
    """If Spotify replies with no match, the HR rows keep an empty
    `artista_spotify_id` but get the `spotify_lookup_at` stamp so
    the search is not re-issued for 30 days."""
    isrc = "ZZ00X0000200"
    _make_orphan_hr(idx=200, isrc=isrc)
    client_mock.search_isrc_principal_artist.return_value = None

    call_command(
        "enriquir_spotify_rebuigs",
        limit=10,
        shortlist_only=True,
        include_orfes=True,
    )

    row = HistorialRevisio.objects.get(canco_isrc=isrc)
    assert row.artista_spotify_id == ""
    assert row.spotify_lookup_at is not None


@pytest.mark.django_db
def test_orphan_flow_skips_recent_lookups(auth_present, client_mock):
    """An HR row with `spotify_lookup_at` set to less than 30 days
    ago is excluded from candidate selection. No /search is fired
    for it."""
    from datetime import timedelta

    from django.utils import timezone

    isrc = "ZZ00X0000300"
    _make_orphan_hr(idx=300, isrc=isrc)
    HistorialRevisio.objects.filter(canco_isrc=isrc).update(
        spotify_lookup_at=timezone.now() - timedelta(days=5)
    )

    call_command(
        "enriquir_spotify_rebuigs",
        limit=10,
        shortlist_only=True,
        include_orfes=True,
    )

    client_mock.search_isrc_principal_artist.assert_not_called()


@pytest.mark.django_db
def test_orphan_flow_disabled_by_default(auth_present, client_mock):
    """Without `--include-orfes` the orphan flow is OFF: the
    backfill ignores HR rows whose Canco was deleted, even if
    they sit on the shortlist."""
    _make_orphan_hr(idx=400, isrc="ZZ00X0000400")

    call_command("enriquir_spotify_rebuigs", limit=10, shortlist_only=True)

    client_mock.search_isrc_principal_artist.assert_not_called()


# ─────────────────────── Pendents flow (last tier) ───────────────────


@pytest.mark.django_db
def test_pendents_flow_runs_only_when_alive_pool_empty_and_flag_set(
    auth_present, client_mock
):
    """A `verificada=False, activa=True` Canco with no rebuig and
    no SpotifyMetadata is picked up only when `--include-pendents`
    is set AND the live-shortlist pool is empty."""
    a = Artista.objects.create(nom="EXEMPLE pendent A")
    al = Album.objects.create(artista=a, nom="EXEMPLE pendent Al")
    c = Canco.objects.create(
        artista=a,
        album=al,
        nom="EXEMPLE pendent track",
        isrc="ZZ00X0000500",
        deezer_id=500001,
        verificada=False,
        activa=True,
        data_llancament=date(2026, 1, 1),
    )
    # No HR rebuig row exists for this Canco; only pendent flow can pick it.

    client_mock.search_isrc.return_value = "spotify:track:abc500"
    client_mock.get_track.return_value = {
        "id": "abc500",
        "name": "Pendent",
        "duration_ms": 180000,
        "artists": [{"id": "ART_500"}],
    }
    client_mock.get_artist.return_value = {"id": "ART_500", "name": "X"}

    # Without the flag: not touched.
    call_command("enriquir_spotify_rebuigs", limit=5)
    assert not SpotifyMetadata.objects.filter(canco=c).exists()

    # With the flag: picked up.
    call_command("enriquir_spotify_rebuigs", limit=5, include_pendents=True)
    sm = SpotifyMetadata.objects.get(canco=c)
    assert sm.spotify_id == "abc500"


# ───────────────────────── Cascade ordering ──────────────────────────


@pytest.mark.django_db
def test_cascade_alive_consumes_budget_before_orfes(auth_present, client_mock):
    """When the alive-shortlist tier already fills the budget, the
    orphan tier gets no calls. Pins the priority order."""
    # 1 alive shortlist canco.
    c_alive = _make_canco_with_rejection(idx=600, isrc="ZZ00X0000600")
    # 1 orphan on the same shortlist.
    _make_orphan_hr(idx=601, isrc="ZZ00X0000601")

    client_mock.search_isrc.return_value = "spotify:track:alive600"
    client_mock.get_track.return_value = {
        "id": "alive600",
        "name": "Alive",
        "duration_ms": 100000,
        "artists": [{"id": "ART_600"}],
    }
    client_mock.get_artist.return_value = {"id": "ART_600", "name": "X"}

    call_command(
        "enriquir_spotify_rebuigs",
        limit=1,
        shortlist_only=True,
        include_orfes=True,
    )

    # Alive tier consumed the 1-slot budget.
    sm = SpotifyMetadata.objects.get(canco=c_alive)
    assert sm.enrichment_status == SpotifyMetadata.STATUS_FOUND
    # Orphan tier did not run.
    client_mock.search_isrc_principal_artist.assert_not_called()


# ──────────────── Live-tier starvation (regression) ──────────────────


def _make_dead_shortlist_hr(idx: int, isrc: str, created_at):
    """An HR rebuig on the shortlist whose `canco_deezer_id` has NO
    surviving Canco (the cançó was deleted by
    `rebutjar_album`/`rebutjar_artista`). These dominate the real
    shortlist universe (~95 %)."""
    hr = HistorialRevisio.objects.create(
        canco_nom=f"DEAD {idx}",
        artista_nom=f"DEAD artist {idx}",
        artista_deezer_id=700000 + idx,
        canco_deezer_id=700000 + idx,  # no Canco carries this deezer_id
        canco_isrc=isrc,
        decisio="rebutjada",
        motiu="desvincular_album",
    )
    HistorialRevisio.objects.filter(pk=hr.pk).update(created_at=created_at)
    return hr


def _make_alive_shortlist_hr(idx: int, isrc: str, created_at):
    """An HR rebuig on the shortlist whose `canco_deezer_id` points to
    a surviving, non-FOUND Canco (an enrichable live candidate)."""
    a = Artista.objects.create(nom=f"ALIVE {idx}", aprovat=False, pendent_review=True)
    al = Album.objects.create(artista=a, nom=f"ALIVE Al {idx}")
    dz = 800000 + idx
    Canco.objects.create(
        artista=a,
        album=al,
        nom=f"ALIVE {idx}",
        isrc=isrc,
        deezer_id=dz,
        verificada=False,
        activa=True,
        data_llancament=date(2026, 1, 1),
    )
    hr = HistorialRevisio.objects.create(
        canco_nom=f"ALIVE {idx}",
        artista_nom=a.nom,
        artista_deezer_id=810000 + idx,
        canco_deezer_id=dz,
        canco_isrc=isrc,
        decisio="rebutjada",
        motiu="desvincular_album",
    )
    HistorialRevisio.objects.filter(pk=hr.pk).update(created_at=created_at)
    return dz


@pytest.mark.django_db
def test_live_tier_not_starved_by_deleted_cancons():
    """Regression for the 2026-05-28 `live_alive=0` bug.

    500 oldest shortlist HR rows point to deleted cançons, then 50
    point to surviving non-FOUND cançons. Capping at limit=400 used
    to fill the budget entirely with dead deezer_ids and return 0;
    with the surviving-Canço pre-filter the 50 live candidates are
    selected regardless of the cap."""
    from datetime import timedelta

    from django.utils import timezone

    from ingesta.management.commands.enriquir_spotify_rebuigs import Command

    base = timezone.now() - timedelta(days=10)
    for i in range(500):
        _make_dead_shortlist_hr(
            idx=i, isrc=f"ZZDEAD{i:06d}", created_at=base + timedelta(seconds=i)
        )
    for i in range(50):
        _make_alive_shortlist_hr(
            idx=i,
            isrc=f"ZZLIVE{i:06d}",
            created_at=base + timedelta(seconds=1000 + i),
        )

    result = Command()._select_candidates_alive(limit=400, shortlist_only=True)

    assert len(result) == 50
    # Every returned cançó is a surviving, non-FOUND row.
    for c in result:
        assert 800000 <= c.deezer_id < 800050


@pytest.mark.django_db
def test_live_tier_selection_is_deterministic_under_created_at_ties():
    """With a pk tiebreak, two consecutive selections over a pool of
    identical-`created_at` rows return the same capped set of ids."""
    from datetime import timedelta

    from django.utils import timezone

    from ingesta.management.commands.enriquir_spotify_rebuigs import Command

    ts = timezone.now() - timedelta(days=5)
    for i in range(100):
        _make_alive_shortlist_hr(idx=2000 + i, isrc=f"ZZTIE{i:06d}", created_at=ts)

    r1 = Command()._select_candidates_alive(limit=50, shortlist_only=True)
    r2 = Command()._select_candidates_alive(limit=50, shortlist_only=True)

    ids1 = sorted(c.deezer_id for c in r1)
    ids2 = sorted(c.deezer_id for c in r2)
    assert len(r1) == 50
    assert ids1 == ids2


@pytest.mark.django_db
def test_live_tier_no_regression_when_alive_pool_within_cap():
    """When every live candidate already fits inside the cap, the
    pre-filter changes nothing: all of them are returned."""
    from datetime import timedelta

    from django.utils import timezone

    from ingesta.management.commands.enriquir_spotify_rebuigs import Command

    base = timezone.now() - timedelta(days=3)
    expected = set()
    for i in range(10):
        dz = _make_alive_shortlist_hr(
            idx=3000 + i,
            isrc=f"ZZOK{i:06d}",
            created_at=base + timedelta(seconds=i),
        )
        expected.add(dz)

    result = Command()._select_candidates_alive(limit=400, shortlist_only=True)

    assert {c.deezer_id for c in result} == expected
