"""Empty-string → NULL normalisation on unique fields.

Without this guard, two rows that both saw the unique CharField cleared
to "" (instead of None) would crash with `duplicate key value violates
unique constraint`. We hit this with `musicbrainz_id` in production
(2026-04-25) before adding the normaliser. These tests pin the
behaviour for every nullable-unique field on Artista / Album / Canco.
"""

import pytest

from music.models import Album, Artista, Canco


@pytest.mark.django_db
class TestArtistaSaveNormalization:
    def test_empty_mbid_normalises_to_none(self):
        a = Artista.objects.create(nom="Test Empty MBID 1", musicbrainz_id="")
        a.refresh_from_db()
        assert a.musicbrainz_id is None

    def test_empty_spotify_id_normalises_to_none(self):
        a = Artista.objects.create(nom="Test Empty Spotify 1", spotify_id="")
        a.refresh_from_db()
        assert a.spotify_id is None

    def test_two_artists_with_blank_mbid_dont_collide(self):
        Artista.objects.create(nom="Test A", musicbrainz_id="")
        Artista.objects.create(nom="Test B", musicbrainz_id="")
        # Both should land as NULL — Postgres allows multiple NULLs in UNIQUE.
        assert (
            Artista.objects.filter(musicbrainz_id__isnull=True)
            .filter(nom__startswith="Test ")
            .count()
            == 2
        )

    def test_real_mbid_preserved(self):
        mbid = "11111111-2222-3333-4444-555555555555"
        a = Artista.objects.create(nom="Test Real MBID", musicbrainz_id=mbid)
        a.refresh_from_db()
        assert a.musicbrainz_id == mbid


@pytest.mark.django_db
class TestAlbumSaveNormalization:
    def test_empty_spotify_id_normalises(self):
        artista = Artista.objects.create(nom="Test Album Owner")
        alb = Album.objects.create(artista=artista, nom="A1", spotify_id="")
        alb.refresh_from_db()
        assert alb.spotify_id is None


@pytest.mark.django_db
class TestCancoSaveNormalization:
    def test_empty_spotify_id_normalises(self):
        artista = Artista.objects.create(nom="Test Canco Owner")
        album = Album.objects.create(artista=artista, nom="A1")
        c = Canco.objects.create(artista=artista, album=album, nom="T1", spotify_id="")
        c.refresh_from_db()
        assert c.spotify_id is None
