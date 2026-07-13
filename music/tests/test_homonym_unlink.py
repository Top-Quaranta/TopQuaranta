"""Auto-unlink of Deezer IDs when every track of an artist has been
rejected via `desvincular_artista`.

Behaviour pinned:
  1. Artist with all tracks rejected `desvincular_artista` and 0
     active → all ArtistaDeezer rows deleted.
  2. Artist with mixed motius (some `desvincular_canco`, some
     `desvincular_artista`) → no auto-unlink (human review needed).
  3. Artist with at least one active track left → no auto-unlink.
  4. After unlink, the artista lands on `pendent_review=True,
     aprovat=False` regardless of MBID. The MBID does not factor
     in: new releases come from Deezer and the operator still needs
     to find the correct Deezer profile.
"""

from datetime import date

import pytest

from music.models import Artista, ArtistaDeezer, Canco
from music.services import rebutjar_canco


@pytest.fixture
def artist_with_track(db):
    artista = Artista.objects.create(nom="Homonym Test", aprovat=True)
    ArtistaDeezer.objects.create(artista=artista, deezer_id=999111, principal=True)
    return artista


def _make_canco(artista, nom):
    from music.models import Album

    album = Album.objects.create(artista=artista, nom=f"Album {nom}")
    return Canco.objects.create(
        artista=artista,
        album=album,
        nom=nom,
        verificada=False,
        activa=True,
        data_llancament=date(2026, 1, 1),
    )


@pytest.mark.django_db
def test_unlink_when_all_rejected_as_homonym(artist_with_track):
    a = artist_with_track
    c1 = _make_canco(a, "T1")
    c2 = _make_canco(a, "T2")

    rebutjar_canco(c1, "desvincular_artista")
    rebutjar_canco(c2, "desvincular_artista")

    assert not ArtistaDeezer.objects.filter(artista=a).exists()


@pytest.mark.django_db
def test_no_unlink_when_motius_mixed(artist_with_track):
    a = artist_with_track
    c1 = _make_canco(a, "T1")
    c2 = _make_canco(a, "T2")

    rebutjar_canco(c1, "desvincular_canco")
    rebutjar_canco(c2, "desvincular_artista")

    # The mix means we can't be certain the Deezer ID is wrong.
    assert ArtistaDeezer.objects.filter(artista=a).count() == 1


@pytest.mark.django_db
def test_no_unlink_when_active_tracks_remain(artist_with_track):
    a = artist_with_track
    c1 = _make_canco(a, "T1")
    _alive = _make_canco(a, "T2")

    rebutjar_canco(c1, "desvincular_artista")

    assert ArtistaDeezer.objects.filter(artista=a).count() == 1


@pytest.mark.django_db
def test_unlink_queues_for_pendent_review_when_no_mbid(artist_with_track):
    a = artist_with_track
    assert a.aprovat is True
    assert a.musicbrainz_id is None

    c = _make_canco(a, "Only")
    rebutjar_canco(c, "desvincular_artista")

    a.refresh_from_db()
    # ArtistaDeezer was the sole anchor; the signal desaproves and
    # then the service overrides to pendent_review=True.
    assert a.aprovat is False
    assert a.pendent_review is True
    assert not ArtistaDeezer.objects.filter(artista=a).exists()


@pytest.mark.django_db
def test_unlink_queues_for_pendent_review_even_with_mbid(artist_with_track):
    """MBID does not exempt: new releases come from Deezer, so the
    operator still needs to find the correct Deezer profile and the
    artista belongs in pendents."""
    a = artist_with_track
    a.musicbrainz_id = "abcdef00-1111-2222-3333-444444444444"
    a.save()

    c = _make_canco(a, "Only")
    rebutjar_canco(c, "desvincular_artista")

    a.refresh_from_db()
    assert a.aprovat is False
    assert a.pendent_review is True
    assert not ArtistaDeezer.objects.filter(artista=a).exists()
