"""Tests for the YouTube client + discovery/poll commands.

External HTTP is mocked; no real quota is spent.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from ingesta.clients import youtube as yt
from music.models import Album, Artista, Canco
from ranking.models import SenyalYouTube


class TestFindTopicChannel:
    """Searching "<nom> - Topic" returns the band's OWN channel first when
    the band has one. Accepting it poisons every downstream match: its
    videos are videoclips with decorated titles ("AUXILI - TARRINETES AL
    SOL ft DJ Trapella"), which match nothing. Caught in the 2026-08-11
    recon — 8 of 30 artists silently matched 0 songs because of it."""

    def _search(self, titles):
        return {
            "items": [
                {"snippet": {"title": t, "channelId": f"UC{i}"}}
                for i, t in enumerate(titles)
            ]
        }

    def test_prefers_the_topic_channel_over_the_human_one(self):
        with patch.object(
            yt, "_get", return_value=self._search(["AUXILI", "Auxili - Topic"])
        ):
            assert yt.find_topic_channel("Auxili") == "UC1"

    def test_refuses_when_no_candidate_carries_the_suffix(self):
        with patch.object(yt, "_get", return_value=self._search(["AUXILI", "Auxili"])):
            assert yt.find_topic_channel("Auxili") is None

    def test_refuses_a_topic_channel_of_a_different_act(self):
        with patch.object(
            yt, "_get", return_value=self._search(["Guerra Sound - Topic"])
        ):
            assert yt.find_topic_channel("Guerra") is None


class TestQuota:
    def test_quota_exceeded_raises_instead_of_looking_like_no_results(self):
        payload = {
            "error": {
                "message": "quota",
                "errors": [{"reason": "quotaExceeded"}],
            }
        }
        with (
            patch("ingesta.clients.youtube.requests.get") as g,
            patch("ingesta.clients.youtube.time.sleep"),
        ):
            g.return_value.json.return_value = payload
            with pytest.raises(yt.QuotaExhausted):
                yt.find_topic_channel("X")

    def test_other_errors_degrade_to_empty(self):
        payload = {"error": {"message": "boom", "errors": [{"reason": "backendError"}]}}
        with (
            patch("ingesta.clients.youtube.requests.get") as g,
            patch("ingesta.clients.youtube.time.sleep"),
        ):
            g.return_value.json.return_value = payload
            assert yt.find_topic_channel("X") is None


@pytest.mark.django_db
class TestDescobrirYoutube:
    @pytest.fixture
    def artista(self):
        a = Artista.objects.create(nom="Auxili", lastfm_nom="Auxili", aprovat=True)
        alb = Album.objects.create(
            artista=a, nom="X", data_llancament=date.today() - timedelta(days=10)
        )
        for nom in ("Tarrinetes al Sol", "Lluna per Nosaltres"):
            Canco.objects.create(
                artista=a,
                album=alb,
                nom=nom,
                lastfm_nom=nom,
                data_llancament=date.today() - timedelta(days=10),
                verificada=True,
                activa=True,
            )
        return a

    def test_matches_art_tracks_by_normalised_title(self, artista):
        with (
            patch.object(yt, "find_topic_channel", return_value="UCabc"),
            patch.object(yt, "uploads_playlist", return_value="UUabc"),
            patch.object(
                yt,
                "playlist_videos",
                return_value=[
                    # Last.fm-style casing differences must not block the match.
                    {"video_id": "v1", "title": "Tarrinetes al sol"},
                    {"video_id": "v2", "title": "Un altre tema"},
                ],
            ),
        ):
            call_command("descobrir_youtube", stdout=StringIO())

        artista.refresh_from_db()
        assert artista.youtube_channel_id == "UCabc"
        c = Canco.objects.get(nom="Tarrinetes al Sol")
        assert c.youtube_video_id == "v1"
        assert c.youtube_match == Canco.MATCH_EXACTE
        # No blind guessing: the unmatched track stays unmatched.
        assert Canco.objects.get(nom="Lluna per Nosaltres").youtube_video_id == ""

    def test_a_miss_is_remembered_so_we_dont_respend_100_units(self, artista):
        with patch.object(yt, "find_topic_channel", return_value=None):
            call_command("descobrir_youtube", stdout=StringIO())
        artista.refresh_from_db()
        assert artista.youtube_checked_at is not None
        assert artista.youtube_channel_id == ""

        from ingesta.management.commands.descobrir_youtube import _cua

        assert artista not in _cua(None)

    def test_budget_stops_the_run(self, artista):
        with patch.object(yt, "find_topic_channel") as f:
            call_command("descobrir_youtube", "--budget", "10", stdout=StringIO())
        f.assert_not_called()


@pytest.mark.django_db
class TestObtenirSenyalYoutube:
    @pytest.fixture
    def canco(self):
        a = Artista.objects.create(nom="A", lastfm_nom="A", aprovat=True)
        alb = Album.objects.create(
            artista=a, nom="X", data_llancament=date.today() - timedelta(days=5)
        )
        return Canco.objects.create(
            artista=a,
            album=alb,
            nom="T",
            data_llancament=date.today() - timedelta(days=5),
            verificada=True,
            activa=True,
            youtube_video_id="v1",
        )

    def test_writes_a_snapshot(self, canco):
        with patch.object(
            yt, "video_stats", return_value={"v1": {"views": 1234, "likes": 56}}
        ):
            call_command("obtenir_senyal_youtube", stdout=StringIO())
        row = SenyalYouTube.objects.get(canco=canco)
        assert row.views == 1234 and row.error is False

    def test_missing_stats_are_recorded_not_dropped(self, canco):
        """A takedown must be visible in the daily report, not silence."""
        with patch.object(yt, "video_stats", return_value={}):
            call_command("obtenir_senyal_youtube", stdout=StringIO())
        row = SenyalYouTube.objects.get(canco=canco)
        assert row.error is True and row.views is None

    def test_is_idempotent_for_the_same_day(self, canco):
        with patch.object(
            yt, "video_stats", return_value={"v1": {"views": 1, "likes": 0}}
        ) as m:
            call_command("obtenir_senyal_youtube", stdout=StringIO())
            call_command("obtenir_senyal_youtube", stdout=StringIO())
        assert m.call_count == 1
        assert SenyalYouTube.objects.filter(canco=canco).count() == 1


class TestConteTitol:
    """The guard that decides whether a video on the artist's own channel
    is *this* song. Titles there are free text ("AUXILI - TARRINETES AL
    SOL ft DJ Trapella"), so this is where the "Guerra"/"Ukraine" exploit
    would land. The project's rule is explicit: when in doubt, refuse."""

    @staticmethod
    def _f(video, canco, artista=""):
        from ingesta.management.commands.descobrir_youtube import _conte_titol

        return _conte_titol(video, canco, artista)

    @pytest.mark.parametrize(
        "video,canco,artista",
        [
            ("auxili tarrinetes al sol ft dj trapella", "tarrinetes al sol", "auxili"),
            (
                "joan miquel oliver oxitocina video oficial",
                "oxitocina",
                "joan miquel oliver",
            ),
            # The artist's name after the title is a credit line.
            ("exorcisme katta lana", "exorcisme", "katta lana"),
            ("baby toca m katta lana brauer", "baby toca m", "katta lana"),
            # Stripping the artist must not eat the song's own words.
            ("malalts d hivern", "malalts d hivern", "malalts"),
            ("malalts som malalts directe", "som malalts", "malalts"),
        ],
    )
    def test_accepts_the_real_thing(self, video, canco, artista):
        assert self._f(video, canco, artista) is True

    @pytest.mark.parametrize(
        "video,canco,artista",
        [
            # Word boundaries are NOT enough: "llibertat" is a whole word
            # inside "buscant la llibertat". Caught probing David Torné.
            ("buscant la llibertat", "llibertat", "david torne"),
            # A different song that merely starts with ours.
            ("oxitocina i dopamina", "oxitocina", ""),
            ("res de res", "res", ""),
            # Trailing free text that isn't decoration nor the artist.
            ("guapa i bonica", "guapa", "katta lana"),
            ("nadala de xabia 2019", "nadala de xabia", ""),
        ],
    )
    def test_refuses_the_lookalikes(self, video, canco, artista):
        assert self._f(video, canco, artista) is False


@pytest.mark.django_db
class TestDuesLlanes:
    """A song's YouTube signal is the SUM of the Art Track and whatever
    the artist's official channel holds for it. An artist reviewed as
    having no own channel is complete with one lane — not a gap."""

    @pytest.fixture
    def canco(self):
        from music.models import CancoYouTubeVideo

        a = Artista.objects.create(nom="A", lastfm_nom="A", aprovat=True)
        alb = Album.objects.create(
            artista=a, nom="X", data_llancament=date.today() - timedelta(days=5)
        )
        c = Canco.objects.create(
            artista=a,
            album=alb,
            nom="T",
            data_llancament=date.today() - timedelta(days=5),
            verificada=True,
            activa=True,
            youtube_video_id="art1",
        )
        CancoYouTubeVideo.objects.create(canco=c, video_id="clip1", titol="A - T")
        CancoYouTubeVideo.objects.create(canco=c, video_id="clip2", titol="A - T live")
        return c

    def test_sums_every_lane_into_one_row(self, canco):
        with patch.object(
            yt,
            "video_stats",
            return_value={
                "art1": {"views": 100, "likes": 1},
                "clip1": {"views": 9000, "likes": 20},
                "clip2": {"views": 400, "likes": 5},
            },
        ):
            call_command("obtenir_senyal_youtube", stdout=StringIO())

        row = SenyalYouTube.objects.get(canco=canco)
        assert row.views == 9500
        assert row.n_videos == 3
        assert row.error is False

    def test_one_dead_video_among_several_is_not_an_error(self, canco):
        with patch.object(
            yt,
            "video_stats",
            return_value={"art1": {"views": 100, "likes": 1}},
        ):
            call_command("obtenir_senyal_youtube", stdout=StringIO())

        row = SenyalYouTube.objects.get(canco=canco)
        assert row.error is False
        assert row.views == 100 and row.n_videos == 1

    def test_all_lanes_dead_is_an_error(self, canco):
        with patch.object(yt, "video_stats", return_value={}):
            call_command("obtenir_senyal_youtube", stdout=StringIO())

        row = SenyalYouTube.objects.get(canco=canco)
        assert row.error is True and row.n_videos == 0


@pytest.mark.django_db
class TestSembrarCanals:
    def test_reads_the_channel_id_straight_off_a_musicbrainz_url(self):
        a = Artista.objects.create(
            nom="A",
            lastfm_nom="A",
            aprovat=True,
            youtube_url="https://www.youtube.com/channel/UCego8MWd7DkJXnGl9WQAbTQ",
        )
        call_command("sembrar_canals_youtube", stdout=StringIO())
        a.refresh_from_db()
        assert a.youtube_canal_oficial == "UCego8MWd7DkJXnGl9WQAbTQ"
        assert a.youtube_canal_revisat is True

    def test_a_handle_is_resolved_for_one_unit(self):
        """`forHandle` costs 1 unit; the old `search.list` path cost 100
        and turned the 655-handle backlog into seven days of quota."""
        for i in range(3):
            Artista.objects.create(
                nom=f"A{i}",
                lastfm_nom=f"A{i}",
                aprovat=True,
                youtube_url=f"https://www.youtube.com/@handle{i}",
            )
        with patch.object(yt, "resolve_handle", return_value="UC" + "x" * 20) as m:
            call_command("sembrar_canals_youtube", "--resolve", stdout=StringIO())

        assert m.call_count == 3
        assert Artista.objects.exclude(youtube_canal_oficial="").count() == 3

    def test_the_budget_still_stops_the_run(self):
        for i in range(4):
            Artista.objects.create(
                nom=f"B{i}",
                lastfm_nom=f"B{i}",
                aprovat=True,
                youtube_url=f"https://www.youtube.com/@h{i}",
            )
        with patch.object(yt, "resolve_handle", return_value="UC" + "y" * 20) as m:
            call_command(
                "sembrar_canals_youtube",
                "--resolve",
                "--budget",
                "2",
                stdout=StringIO(),
            )
        assert m.call_count == 2

    def test_absence_of_a_link_never_marks_the_artist_reviewed(self):
        """ "Nobody looked yet" is not "looked, has none" — only a human
        writes the second."""
        a = Artista.objects.create(nom="B", lastfm_nom="B", aprovat=True)
        call_command("sembrar_canals_youtube", stdout=StringIO())
        a.refresh_from_db()
        assert a.youtube_canal_revisat is False


class TestNomsAmbAccents:
    """Two real misses from the first full discovery run, both mine."""

    def _search(self, titles):
        return {
            "items": [
                {"snippet": {"title": t, "channelId": f"UC{i}"}}
                for i, t in enumerate(titles)
            ]
        }

    def test_matches_an_unaccented_channel_title(self):
        """Our "Bèrnia" against a channel literally called "bernia"."""
        with patch.object(yt, "_get", return_value=self._search(["bernia - Topic"])):
            assert yt.find_topic_channel("Bèrnia") == "UC0"

    def test_matches_across_unicode_normalisation(self):
        """NFD on one side, NFC on the other — "Clàudia Xiva" was refused
        against a channel with the identical visible name."""
        import unicodedata

        nfd = unicodedata.normalize("NFD", "Clàudia Xiva")
        with patch.object(
            yt, "_get", return_value=self._search(["Clàudia Xiva - Topic"])
        ):
            assert yt.find_topic_channel(nfd) == "UC0"

    def test_still_refuses_a_different_act(self):
        """Folding accents must not start accepting other bands."""
        with patch.object(
            yt, "_get", return_value=self._search(["Essência do Céu - Topic"])
        ):
            assert yt.find_topic_channel("Essència") is None


class TestSufixLocalitzat:
    """YouTube localises the auto-generated suffix: a Catalan browser shows
    "Malifeta - Tema". Our server currently gets English, but that is the
    API's default locale, not a contract — and requiring the English word
    would make discovery return nothing at all, silently."""

    @pytest.mark.parametrize(
        "titol,esperat",
        [
            ("Malifeta - Topic", "Malifeta"),
            ("Malifeta - Tema", "Malifeta"),
            ("Auxili - Thema", "Auxili"),
            ("MALIFETA", None),
            ("Malifeta de Tema", None),
        ],
    )
    def test_recognises_the_auto_generated_channel(self, titol, esperat):
        assert yt.topic_suffix_name(titol) == esperat

    def test_discovery_accepts_a_localised_suffix(self):
        data = {"items": [{"snippet": {"title": "Auxili - Tema", "channelId": "UC9"}}]}
        with patch.object(yt, "_get", return_value=data):
            assert yt.find_topic_channel("Auxili") == "UC9"


@pytest.mark.django_db
class TestCarrilOficialDesacoblat:
    """An official channel confirmed AFTER the artist's Topic discovery
    must still get enumerated. The day the first 58 staff confirmations
    were applied, exactly 1 official-lane video had ever been matched:
    the enumeration only ran inside the discovery loop, and an artist
    already discovered never re-entered it."""

    def test_enumerates_official_channels_of_discovered_artists(self):
        from music.models import CancoYouTubeVideo

        a = Artista.objects.create(
            nom="Bèrnia",
            lastfm_nom="Bèrnia",
            aprovat=True,
            youtube_channel_id="UCtopic" + "x" * 15,  # Topic ja descobert
            youtube_checked_at=timezone.now(),
            youtube_canal_oficial="UCoficial" + "y" * 13,
            youtube_canal_revisat=True,
        )
        alb = Album.objects.create(
            artista=a, nom="X", data_llancament=date.today() - timedelta(days=10)
        )
        c = Canco.objects.create(
            artista=a,
            album=alb,
            nom="La Nit Més Llarga",
            data_llancament=date.today() - timedelta(days=10),
            verificada=True,
            activa=True,
        )

        with (
            patch.object(yt, "uploads_playlist", return_value="UUof"),
            patch.object(
                yt,
                "playlist_videos",
                return_value=[
                    {
                        "video_id": "v9",
                        "title": "Bèrnia - La Nit Més Llarga (Videoclip)",
                    }
                ],
            ),
        ):
            call_command("descobrir_youtube", stdout=StringIO())

        v = CancoYouTubeVideo.objects.get(canco=c)
        assert v.video_id == "v9"

    def test_second_run_adds_nothing_new(self):
        from music.models import CancoYouTubeVideo

        a = Artista.objects.create(
            nom="A",
            lastfm_nom="A",
            aprovat=True,
            youtube_channel_id="UCt" + "x" * 19,
            youtube_checked_at=timezone.now(),
            youtube_canal_oficial="UCo" + "y" * 19,
            youtube_canal_revisat=True,
        )
        alb = Album.objects.create(
            artista=a, nom="X", data_llancament=date.today() - timedelta(days=5)
        )
        Canco.objects.create(
            artista=a,
            album=alb,
            nom="Cançó Llarga",
            data_llancament=date.today() - timedelta(days=5),
            verificada=True,
            activa=True,
        )
        videos = [{"video_id": "v1", "title": "Cançó Llarga"}]
        with (
            patch.object(yt, "uploads_playlist", return_value="UUo"),
            patch.object(yt, "playlist_videos", return_value=videos),
        ):
            call_command("descobrir_youtube", stdout=StringIO())
            out = StringIO()
            call_command("descobrir_youtube", stdout=out)

        assert CancoYouTubeVideo.objects.count() == 1
        assert "vídeos del carril oficial: 0" in out.getvalue()
