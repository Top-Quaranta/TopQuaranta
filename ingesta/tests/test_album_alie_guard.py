"""Album-alien guard in `obtenir_novetats._create_track`.

Rule (authorised after `ingest-album-alie-recon.md`): a track is created
under `album.artista` only when the album is genuinely theirs (`own_album`)
OR our artista appears among the track's LIVE Deezer contributors. The
canonical no-regression cases:

- Pangea: foreign album where we only guest on 1 track → only that track
  enters, the rest are skipped.
- Own album with guests: titular is ours → every track enters.
- Remix: our own remix (we're on the track) enters; a foreign remix on the
  same album is skipped.
- `/album/{id}` failure: conservative — `own_album=True`, nothing dropped.
"""

from unittest.mock import patch

import pytest

from ingesta.management.commands import obtenir_novetats
from ingesta.management.commands.obtenir_novetats import Command
from music.models import Album, Artista, ArtistaDeezer, Canco

OUR_DZ = 96483602  # our artista's Deezer profile
FOREIGN_DZ = 173775537  # the foreign album titular (e.g. TIPO TRANQILO)


@pytest.fixture
def our_artista(db):
    a = Artista.objects.create(nom="Baya Baye", slug="baya-baye", aprovat=True)
    ArtistaDeezer.objects.create(artista=a, deezer_id=OUR_DZ, principal=True)
    return a


@pytest.fixture
def foreign_album(our_artista):
    """An album row attributed to our artista (as the ingest does today),
    but whose real Deezer titular is someone else."""
    import datetime

    return Album.objects.create(
        deezer_id=986902841,
        nom="Pangea",
        artista=our_artista,
        data_llancament=datetime.date.today(),
        tipus="album",
    )


def _track(dz_id, title, contributor_ids, isrc=""):
    return {
        "id": dz_id,
        "title": title,
        "isrc": isrc,
        "duration": 180,
        "preview": "",
        "album_release_date": "",
        "contributors": [
            {"id": cid, "name": f"artist-{cid}"} for cid in contributor_ids
        ],
    }


# Skip the ML classifier in the create path — irrelevant to the guard.
@pytest.fixture(autouse=True)
def _no_ml():
    with patch.object(obtenir_novetats, "classificar_i_guardar", lambda c: None):
        yield


@pytest.mark.django_db
def test_foreign_album_skips_track_without_our_artist(foreign_album):
    """Pangea pin (the skipped majority): foreign titular + our artista not a
    contributor → the track is NOT created."""
    cmd = Command()
    td = _track(4032703301, "3GSC", [FOREIGN_DZ, 13869917], isrc="ESA092607294")
    created = cmd._create_track(foreign_album, td, own_album=False)
    assert created is False
    assert not Canco.objects.filter(deezer_id=4032703301).exists()


@pytest.mark.django_db
def test_foreign_album_keeps_track_where_our_artist_contributes(foreign_album):
    """Pangea pin (the kept collab): foreign titular but our artista IS a
    contributor → the track enters under our artista."""
    cmd = Command()
    td = _track(111, "Els Veritables", [FOREIGN_DZ, OUR_DZ], isrc="ESLEGIT0001")
    created = cmd._create_track(foreign_album, td, own_album=False)
    assert created is True
    c = Canco.objects.get(deezer_id=111)
    assert c.artista_id == foreign_album.artista_id


@pytest.mark.django_db
def test_own_album_keeps_all_tracks_including_guest_led(our_artista):
    """Own-album pin: titular is ours → even a track where our artista isn't a
    per-track contributor (guest-led interlude) still enters."""
    import datetime

    own = Album.objects.create(
        deezer_id=555,
        nom="Disc Propi",
        artista=our_artista,
        data_llancament=datetime.date.today(),
        tipus="album",
    )
    cmd = Command()
    td = _track(222, "Interludi del Convidat", [987654], isrc="ESOWN00001")
    created = cmd._create_track(own, td, own_album=True)
    assert created is True
    assert Canco.objects.get(deezer_id=222).artista_id == our_artista.id


@pytest.mark.django_db
def test_remix_own_kept_foreign_skipped_same_album(foreign_album):
    """Remix pin: on one foreign album, our remix (we're on the track) enters,
    the original/foreign remix is skipped."""
    cmd = Command()
    ours = _track(301, "Glowing Tide (Roger Remix)", [FOREIGN_DZ, OUR_DZ], "ESRMX0001")
    alien = _track(302, "Glowing Tide", [FOREIGN_DZ], "ESRMX0002")
    assert cmd._create_track(foreign_album, ours, own_album=False) is True
    assert cmd._create_track(foreign_album, alien, own_album=False) is False
    assert Canco.objects.filter(deezer_id=301).exists()
    assert not Canco.objects.filter(deezer_id=302).exists()


@pytest.mark.django_db
def test_resolve_own_album_true_when_titular_is_ours(foreign_album):
    cmd = Command()
    with patch.object(
        obtenir_novetats.deezer, "get_album_titular_id", return_value=OUR_DZ
    ):
        assert cmd._resolve_own_album(foreign_album) is True


@pytest.mark.django_db
def test_resolve_own_album_false_when_titular_is_foreign(foreign_album):
    cmd = Command()
    with patch.object(
        obtenir_novetats.deezer, "get_album_titular_id", return_value=FOREIGN_DZ
    ):
        assert cmd._resolve_own_album(foreign_album) is False


@pytest.mark.django_db
def test_resolve_own_album_conservative_on_failure(foreign_album):
    """`/album/{id}` failure → None → treat as own album (never drop tracks
    because of a transient API hiccup)."""
    cmd = Command()
    with patch.object(
        obtenir_novetats.deezer, "get_album_titular_id", return_value=None
    ):
        assert cmd._resolve_own_album(foreign_album) is True
