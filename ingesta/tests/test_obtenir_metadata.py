from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from music.models import Album, Artista, ArtistaDeezer, Canco, Territori


@pytest.fixture(autouse=True)
def territoris():
    Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Catalunya"})
    Territori.objects.get_or_create(codi="VAL", defaults={"nom": "País Valencià"})


def _make_artista(
    nom="Zoo", spotify_id="sp_zoo", deezer_id=None, aprovat=True, territori="CAT"
):
    a = Artista.objects.create(
        nom=nom,
        lastfm_nom=nom,
        spotify_id=spotify_id,
        aprovat=aprovat,
    )
    if deezer_id is not None:
        # R10: link via ArtistaDeezer — the legacy direct field is gone.
        ArtistaDeezer.objects.create(artista=a, deezer_id=deezer_id, principal=True)
    a.territoris.set([Territori.objects.get(codi=territori)])
    return a


RECENT = date.today() - timedelta(days=30)

MOCK_ALBUM = {
    "id": 100,
    "title": "Disc Nou",
    "release_date": RECENT,
    "cover_xl": "https://img.com/cover.jpg",
    "record_type": "album",
}

MOCK_TRACK = {
    "id": 500,
    "title": "Cançó 1",
    "duration": 200,
    "isrc": "ES0001234567",
    "artist_id": 98469,
    "artist_name": "Zoo",
}


@pytest.mark.django_db
class TestIngestarMetadataDeezer:
    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_creates_album_and_track_with_known_deezer_id(self, mock_deezer):
        artista = _make_artista(deezer_id=98469)

        mock_deezer.get_artist_albums.return_value = [MOCK_ALBUM]
        mock_deezer.get_album_tracks.return_value = [MOCK_TRACK]

        call_command("obtenir_metadata", artista_id=artista.pk)

        assert Album.objects.count() == 1
        album = Album.objects.first()
        assert album.nom == "Disc Nou"
        assert album.deezer_id == 100

        assert Canco.objects.count() == 1
        canco = Canco.objects.first()
        assert canco.nom == "Cançó 1"
        assert canco.isrc == "ES0001234567"
        assert canco.deezer_id == 500

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_resolves_deezer_id_via_search_and_isrc(self, mock_deezer):
        artista = _make_artista(deezer_id=None)
        # Create a known track with ISRC for validation
        album = Album.objects.create(
            spotify_id="alb_old", nom="Old Album", artista=artista
        )
        Canco.objects.create(
            spotify_id="trk_old",
            nom="Old Track",
            album=album,
            artista=artista,
            isrc="ES0001234567",
        )

        mock_deezer.search_artist.return_value = {"id": 98469, "name": "ZOO"}
        mock_deezer.get_artist_info.return_value = {"nb_fan": 1000, "nb_album": 5}
        # First get_artist_albums call: for ISRC validation (up to 3 albums)
        # Second call: for actual album fetching
        mock_deezer.get_artist_albums.side_effect = [
            [
                {
                    "id": 900,
                    "title": "Val Album",
                    "release_date": RECENT,
                    "cover_xl": "",
                    "record_type": "album",
                }
            ],
            [MOCK_ALBUM],
        ]
        mock_deezer.get_album_tracks.side_effect = [
            [
                {
                    "id": 901,
                    "title": "Match",
                    "duration": 180,
                    "isrc": "ES0001234567",
                    "artist_id": 98469,
                    "artist_name": "Zoo",
                }
            ],
            [MOCK_TRACK],
        ]

        call_command("obtenir_metadata", artista_id=artista.pk)

        artista.refresh_from_db()
        assert artista.deezer_id_principal == 98469

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_marks_not_found_when_search_fails(self, mock_deezer):
        artista = _make_artista(deezer_id=None)

        mock_deezer.search_artist.return_value = None

        call_command("obtenir_metadata", artista_id=artista.pk)

        artista.refresh_from_db()
        # No Deezer link created; last_checked_deezer is set.
        assert artista.deezer_id_principal is None
        assert artista.last_checked_deezer is not None

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_marks_not_found_when_isrc_validation_fails(self, mock_deezer):
        artista = _make_artista(deezer_id=None)
        album = Album.objects.create(spotify_id="alb1", nom="Album", artista=artista)
        Canco.objects.create(
            spotify_id="trk1",
            nom="Track",
            album=album,
            artista=artista,
            isrc="REAL_ISRC_123",
        )

        mock_deezer.search_artist.return_value = {"id": 999, "name": "Wrong Artist"}
        mock_deezer.get_artist_albums.return_value = [
            {
                "id": 800,
                "title": "X",
                "release_date": RECENT,
                "cover_xl": "",
                "record_type": "album",
            }
        ]
        mock_deezer.get_album_tracks.return_value = [
            {
                "id": 801,
                "title": "Y",
                "duration": 100,
                "isrc": "DIFFERENT_ISRC",
                "artist_id": 999,
                "artist_name": "Wrong",
            }
        ]

        call_command("obtenir_metadata", artista_id=artista.pk)

        artista.refresh_from_db()
        assert artista.deezer_id_principal is None
        assert artista.last_checked_deezer is not None

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_skips_unapproved_artist(self, mock_deezer):
        artista = _make_artista(aprovat=False)

        with pytest.raises(CommandError, match="No approved Artista"):
            call_command("obtenir_metadata", artista_id=artista.pk)

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_dry_run_no_writes(self, mock_deezer):
        _make_artista(deezer_id=98469)

        call_command("obtenir_metadata", dry_run=True)

        assert Album.objects.count() == 0
        assert Canco.objects.count() == 0
        mock_deezer.search_artist.assert_not_called()
        mock_deezer.get_artist_albums.assert_not_called()

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_idempotent_without_force(self, mock_deezer):
        artista = _make_artista(deezer_id=98469)

        mock_deezer.get_artist_albums.return_value = [MOCK_ALBUM]
        mock_deezer.get_album_tracks.return_value = [MOCK_TRACK]

        call_command("obtenir_metadata", artista_id=artista.pk)
        call_command("obtenir_metadata", artista_id=artista.pk)

        assert Album.objects.count() == 1
        assert Canco.objects.count() == 1

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_force_updates_existing(self, mock_deezer):
        artista = _make_artista(deezer_id=98469)

        # Pre-create
        album = Album.objects.create(
            deezer_id=100, nom="Old Name", artista=artista, tipus="album"
        )
        Canco.objects.create(
            deezer_id=500,
            nom="Old Track",
            album=album,
            artista=artista,
            isrc="OLD",
        )

        mock_deezer.get_artist_albums.return_value = [
            {
                **MOCK_ALBUM,
                "title": "New Name",
            }
        ]
        mock_deezer.get_album_tracks.return_value = [
            {
                **MOCK_TRACK,
                "title": "New Track",
                "isrc": "NEW123",
            }
        ]

        call_command("obtenir_metadata", artista_id=artista.pk, force=True)

        album.refresh_from_db()
        assert album.nom == "New Name"

        canco = Canco.objects.get(deezer_id=500)
        assert canco.nom == "New Track"
        assert canco.isrc == "NEW123"

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_skips_artists_with_existing_deezer_link(self, mock_deezer):
        """Artists that already have an ArtistaDeezer row are skipped —
        they're the source of truth that the artist is resolved. The
        legacy `deezer_no_trobat` cache flag is no longer consulted by
        the default filter (audit finding #7, Sessió 17)."""
        _make_artista(deezer_id=98469)  # ArtistaDeezer row gets created

        call_command("obtenir_metadata")

        mock_deezer.search_artist.assert_not_called()

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_processes_artists_without_deezer_link(self, mock_deezer):
        """Artists with no ArtistaDeezer row get queried — the M2M
        relation is the source of truth for "has Deezer"."""
        _make_artista(deezer_id=None)
        mock_deezer.search_artist.return_value = None  # still not found

        call_command("obtenir_metadata")

        mock_deezer.search_artist.assert_called()

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_accepts_name_match_without_isrc(self, mock_deezer):
        """Artist with no known ISRC tracks — accept name match."""
        artista = _make_artista(deezer_id=None)
        # No tracks with ISRC exist

        mock_deezer.search_artist.return_value = {"id": 98469, "name": "ZOO"}
        mock_deezer.get_artist_info.return_value = {"nb_fan": 500, "nb_album": 3}
        mock_deezer.get_artist_albums.return_value = [MOCK_ALBUM]
        mock_deezer.get_album_tracks.return_value = [MOCK_TRACK]

        call_command("obtenir_metadata", artista_id=artista.pk)

        artista.refresh_from_db()
        assert artista.deezer_id_principal == 98469
        assert Canco.objects.count() == 1

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_album_label_captured_from_deezer(self, mock_deezer):
        """Deezer's `album.label` is now stored on `Album.label`.
        Auditat 2026-05-07 — abans no es llegia ni guardava."""
        artista = _make_artista(deezer_id=98469)
        album_with_label = {
            **MOCK_ALBUM,
            "label": "Halley Records",
        }
        mock_deezer.get_artist_albums.return_value = [album_with_label]
        mock_deezer.get_album_tracks.return_value = [MOCK_TRACK]

        call_command("obtenir_metadata", artista_id=artista.pk)

        album = Album.objects.first()
        assert album.label == "Halley Records"

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_secondary_contributor_deferred_to_contributors_raw(self, mock_deezer):
        """A new secondary contributor (Deezer ID we've never seen)
        is no longer auto-created as `Artista(pendent_review=True)`.
        Instead it lands on `Canco.contributors_raw` for materialisation
        at verification time. See `Canco.contributors_raw` docstring."""
        artista = _make_artista(deezer_id=98469)
        track_with_contributor = {
            **MOCK_TRACK,
            "contributors": [
                {"id": 98469, "name": "Zoo", "role": "Main"},
                {"id": 88888, "name": "Producer Foo", "role": "Featured"},
            ],
        }
        mock_deezer.get_artist_albums.return_value = [MOCK_ALBUM]
        mock_deezer.get_album_tracks.return_value = [track_with_contributor]

        call_command("obtenir_metadata", artista_id=artista.pk)

        # No Artista created for "Producer Foo" — the deferral is the fix.
        assert not Artista.objects.filter(nom="Producer Foo").exists()
        # Instead the contributor is parked on the canco for later.
        canco = Canco.objects.get(deezer_id=500)
        assert canco.contributors_raw == [
            {"deezer_id": 88888, "name": "Producer Foo", "role": "secondary"}
        ]

    @patch("ingesta.management.commands.obtenir_metadata.deezer")
    def test_secondary_contributor_with_known_deezer_id_attaches_immediately(
        self, mock_deezer
    ):
        """When the contributor's Deezer ID already maps to an Artista
        in our DB, attach via artistes_col now — only net-new
        contributors get deferred."""
        artista = _make_artista(deezer_id=98469)
        # Pre-existing collaborator we already track.
        existing = Artista.objects.create(
            nom="Existing Featuring",
            lastfm_nom="Existing Featuring",
            aprovat=True,
        )
        ArtistaDeezer.objects.create(artista=existing, deezer_id=4242, principal=True)
        track = {
            **MOCK_TRACK,
            "contributors": [
                {"id": 98469, "name": "Zoo", "role": "Main"},
                {"id": 4242, "name": "Existing Featuring", "role": "Featured"},
            ],
        }
        mock_deezer.get_artist_albums.return_value = [MOCK_ALBUM]
        mock_deezer.get_album_tracks.return_value = [track]

        call_command("obtenir_metadata", artista_id=artista.pk)

        canco = Canco.objects.get(deezer_id=500)
        assert canco.contributors_raw == []
        assert existing in canco.artistes_col.all()
