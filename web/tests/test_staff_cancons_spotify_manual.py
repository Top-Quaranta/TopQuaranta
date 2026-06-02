"""Manual Spotify link on the canço editor PATCH (backlog A).

Store-and-trust: PATCH `spotify_url` validates the *format* only (no
Spotify API call), writes `SpotifyMetadata.spotify_id` with
`enrichment_status='manual'` and `enriched_at=NULL` (pending hydration).
The link is visible to Process A (playlist) instantly; Process B's
hydration phase later fills `spotify_artist_id` + the rest from the id
WITHOUT `/search`.

Covers:
  * valid URL / URI / bare id → stored, status=manual, pending, excluded
    from the /search queue, included in the hydration queue;
  * non-track URL / malformed input → 400;
  * fill-when-empty: a second id is refused while one is already set;
  * collision: an id already on another canço → 400;
  * clearing → back to not_attempted → /search-enrichable again;
  * Process A's cache-only resolver picks the manual id up.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from ingesta.management.commands.actualitzar_playlists_spotify import (
    Command as PlaylistCommand,
)
from ingesta.management.commands.enriquir_spotify import Command as EnrichCommand
from music.models import Album, Artista, Canco, SpotifyMetadata

TRACK_A = "4cOdK2wGLETKBW3PvgPWqT"
TRACK_B = "1301WleyT98MSxVHPZCA6M"


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="manual_spotify_tester",
        email="ms@example.com",
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


def _make_canco(isrc="ZZMN0000001", nom="EXEMPLE MAN C"):
    a = Artista.objects.create(nom="EXEMPLE MAN", lastfm_nom="EXEMPLE MAN")
    al = Album.objects.create(artista=a, nom="EXEMPLE MAN Al")
    return Canco.objects.create(
        artista=a,
        album=al,
        nom=nom,
        isrc=isrc,
        verificada=True,
        activa=True,
    )


def _is_search_candidate(canco) -> bool:
    cands = EnrichCommand()._select_candidates(
        limit=50, retry_not_found=False, target_playlists=False
    )
    return canco.pk in {c.pk for c in cands}


def _is_hydration_candidate(canco) -> bool:
    cands = EnrichCommand()._select_hydration_candidates(limit=50)
    return canco.pk in {c.pk for c in cands}


@pytest.mark.django_db
def test_patch_url_stores_pending_manual(staff_client):
    c = _make_canco()
    # Sanity: a verified canço with an ISRC is /search-enrichable.
    assert _is_search_candidate(c) is True

    r = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/",
        {"spotify_url": f"https://open.spotify.com/track/{TRACK_A}?si=xyz"},
        format="json",
    )
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["spotify"]["spotify_id"] == TRACK_A
    assert body["spotify"]["is_manual"] is True
    assert body["spotify"]["hydration"] == "pending"

    sm = SpotifyMetadata.objects.get(canco=c)
    assert sm.spotify_id == TRACK_A
    assert sm.enrichment_status == SpotifyMetadata.STATUS_MANUAL
    assert sm.spotify_artist_id == ""
    assert sm.enriched_at is None  # pending hydration
    c.refresh_from_db()
    assert c.spotify_id == TRACK_A  # legacy mirror

    # Excluded from the /search queue, included in the hydration queue.
    assert _is_search_candidate(c) is False
    assert _is_hydration_candidate(c) is True


@pytest.mark.django_db
@pytest.mark.parametrize("raw", [f"spotify:track:{TRACK_A}", TRACK_A])
def test_patch_uri_and_bare_id(staff_client, raw):
    c = _make_canco()
    r = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/", {"spotify_url": raw}, format="json"
    )
    assert r.status_code == 200, r.content
    assert r.json()["spotify"]["spotify_id"] == TRACK_A


@pytest.mark.django_db
@pytest.mark.parametrize(
    "raw",
    [
        f"https://open.spotify.com/album/{TRACK_A}",
        f"https://open.spotify.com/artist/{TRACK_A}",
        "not a spotify link",
        "https://open.spotify.com/track/tooshort",
    ],
)
def test_patch_invalid_input_rejected(staff_client, raw):
    c = _make_canco()
    r = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/", {"spotify_url": raw}, format="json"
    )
    assert r.status_code == 400, r.content
    assert "error" in r.json()
    assert not SpotifyMetadata.objects.filter(canco=c, spotify_id=TRACK_A).exists()


@pytest.mark.django_db
def test_fill_when_empty_refuses_overwrite(staff_client):
    c = _make_canco()
    ok = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/",
        {"spotify_url": f"spotify:track:{TRACK_A}"},
        format="json",
    )
    assert ok.status_code == 200
    bad = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/",
        {"spotify_url": f"spotify:track:{TRACK_B}"},
        format="json",
    )
    assert bad.status_code == 400, bad.content
    sm = SpotifyMetadata.objects.get(canco=c)
    assert sm.spotify_id == TRACK_A


@pytest.mark.django_db
def test_collision_with_another_canco_rejected(staff_client):
    c1 = _make_canco(isrc="ZZMN0000001", nom="EXEMPLE MAN 1")
    c2 = _make_canco(isrc="ZZMN0000002", nom="EXEMPLE MAN 2")
    first = staff_client.patch(
        f"/api/v1/staff/cancons/{c1.pk}/",
        {"spotify_url": f"spotify:track:{TRACK_A}"},
        format="json",
    )
    assert first.status_code == 200
    # Same id on a different canço → clear 400, nothing written on c2.
    clash = staff_client.patch(
        f"/api/v1/staff/cancons/{c2.pk}/",
        {"spotify_url": f"spotify:track:{TRACK_A}"},
        format="json",
    )
    assert clash.status_code == 400, clash.content
    assert str(c1.pk) in clash.json()["error"]
    assert not SpotifyMetadata.objects.filter(canco=c2, spotify_id=TRACK_A).exists()


@pytest.mark.django_db
def test_clear_resets_and_reenrichable(staff_client):
    c = _make_canco()
    staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/",
        {"spotify_url": f"spotify:track:{TRACK_A}"},
        format="json",
    )
    assert _is_search_candidate(c) is False
    assert _is_hydration_candidate(c) is True

    cleared = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/", {"spotify_url": ""}, format="json"
    )
    assert cleared.status_code == 200, cleared.content
    assert cleared.json()["spotify"] is None

    sm = SpotifyMetadata.objects.get(canco=c)
    assert sm.enrichment_status == SpotifyMetadata.STATUS_NOT_ATTEMPTED
    assert sm.spotify_id == ""
    c.refresh_from_db()
    assert c.spotify_id is None
    # Back in the /search pool, out of the hydration pool.
    assert _is_search_candidate(c) is True
    assert _is_hydration_candidate(c) is False


@pytest.mark.django_db
def test_manual_id_is_picked_up_by_process_a(staff_client):
    c = _make_canco()
    staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/",
        {"spotify_url": f"https://open.spotify.com/track/{TRACK_A}"},
        format="json",
    )
    fresh = Canco.objects.get(pk=c.pk)
    uri = PlaylistCommand()._resolve_uri_cache_only(fresh)
    assert uri == f"spotify:track:{TRACK_A}"
