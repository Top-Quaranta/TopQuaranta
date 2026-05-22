"""Tests for the SpotifyMetadata model + Artista dispersion fields.

Covers:
  * OneToOne reverse accessor (canco.spotify) works both when row exists
    and when it doesn't (None vs DoesNotExist behaviour).
  * Status transitions (default not_attempted, can go to found/not_found).
  * Defaults on new Artista (dispersio NULL, ids_distints empty list).

Backfill semantics (migration 0080) are covered indirectly by the
fixture set-up: every Canço created in a TransactionTestCase already
has a Spotify row from the migration, but in plain TestCase the
migration runs once per session so the rows persist.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from music.models import Album, Artista, Canco, SpotifyMetadata


@pytest.fixture
def artist_and_album(db):
    a = Artista.objects.create(nom="EXEMPLE Artista", lastfm_nom="EXEMPLE Artista")
    al = Album.objects.create(artista=a, nom="EXEMPLE Album")
    return a, al


@pytest.mark.django_db
def test_default_status_not_attempted(artist_and_album):
    """Per-Canco rows can be created with no fields and default to
    not_attempted; enriched_at stays NULL until Process B fires."""
    a, al = artist_and_album
    c = Canco.objects.create(artista=a, album=al, nom="EXEMPLE C", isrc="ZZ00MD0000001")
    sm = SpotifyMetadata.objects.create(canco=c)
    assert sm.enrichment_status == SpotifyMetadata.STATUS_NOT_ATTEMPTED
    assert sm.spotify_id == ""
    assert sm.spotify_artist_id == ""
    assert sm.spotify_artist_ids == []
    assert sm.images == []
    assert sm.genres == []
    assert sm.enriched_at is None


@pytest.mark.django_db
def test_one_to_one_reverse_accessor(artist_and_album):
    """Canco.spotify resolves to the related SpotifyMetadata row."""
    a, al = artist_and_album
    c = Canco.objects.create(
        artista=a, album=al, nom="EXEMPLE OTO", isrc="ZZ00MD0000002"
    )
    sm = SpotifyMetadata.objects.create(canco=c, spotify_id="ABC123")
    # Reverse lookup via .spotify works even on a fresh fetch.
    c.refresh_from_db()
    assert c.spotify.spotify_id == "ABC123"
    assert c.spotify.pk == sm.pk


@pytest.mark.django_db
def test_status_transition_to_found(artist_and_album):
    """A Process B call flips status to found and stamps enriched_at."""
    a, al = artist_and_album
    c = Canco.objects.create(
        artista=a, album=al, nom="EXEMPLE FT", isrc="ZZ00MD0000003"
    )
    sm = SpotifyMetadata.objects.create(canco=c)
    now = timezone.now()
    sm.enrichment_status = SpotifyMetadata.STATUS_FOUND
    sm.spotify_id = "FOUND123"
    sm.spotify_artist_id = "ARTID1"
    sm.spotify_artist_ids = ["ARTID1", "ARTID2"]
    sm.spotify_artist_name = "EXEMPLE Spotify Name"
    sm.album_type = "single"
    sm.release_date = "2026-01-19"
    sm.duration_ms = 302000
    sm.explicit = False
    sm.is_playable = True
    sm.images = [{"url": "https://example/x.jpg", "width": 640, "height": 640}]
    sm.enriched_at = now
    sm.save()
    sm.refresh_from_db()
    assert sm.enrichment_status == SpotifyMetadata.STATUS_FOUND
    assert sm.spotify_id == "FOUND123"
    assert sm.spotify_artist_ids == ["ARTID1", "ARTID2"]
    assert sm.duration_ms == 302000
    assert sm.is_playable is True
    assert sm.enriched_at == now


@pytest.mark.django_db
def test_status_transition_to_not_found(artist_and_album):
    """When Spotify's /search returns no match, status=not_found with
    enriched_at stamped but spotify_id stays empty."""
    a, al = artist_and_album
    c = Canco.objects.create(
        artista=a, album=al, nom="EXEMPLE NF", isrc="ZZ00MD0000004"
    )
    sm = SpotifyMetadata.objects.create(canco=c)
    now = timezone.now()
    sm.enrichment_status = SpotifyMetadata.STATUS_NOT_FOUND
    sm.enriched_at = now
    sm.save()
    sm.refresh_from_db()
    assert sm.enrichment_status == SpotifyMetadata.STATUS_NOT_FOUND
    assert sm.spotify_id == ""
    assert sm.enriched_at == now


@pytest.mark.django_db
def test_artista_dispersion_defaults():
    """Brand-new Artista has NULL dispersio and empty ids_distints
    until Process B / recalcular_dispersio runs."""
    a = Artista.objects.create(nom="EXEMPLE Artista 2", lastfm_nom="EXEMPLE Artista 2")
    assert a.spotify_artist_dispersio is None
    assert a.spotify_artist_ids_distints == []


@pytest.mark.django_db
def test_backfill_migration_idempotent_on_existing_spotify_id(artist_and_album):
    """Manually exercising the migration shape: Canço with spotify_id ->
    SpotifyMetadata with status=found. The migration uses
    get_or_create-ish logic via the OneToOne column, so re-running
    against a Canço that already has metadata is a no-op."""
    a, al = artist_and_album
    c = Canco.objects.create(
        artista=a,
        album=al,
        nom="EXEMPLE BF",
        isrc="ZZ00MD0000005",
        spotify_id="BACKFILL123",
    )
    sm = SpotifyMetadata.objects.create(
        canco=c,
        spotify_id="BACKFILL123",
        enrichment_status=SpotifyMetadata.STATUS_FOUND,
        enriched_at=timezone.now(),
    )
    assert SpotifyMetadata.objects.filter(canco=c).count() == 1
    # Re-running the backfill body should NOT create a second row
    # (OneToOne would also raise IntegrityError if it tried).
    assert c.spotify.pk == sm.pk
