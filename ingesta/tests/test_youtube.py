"""Tests for the YouTube client + discovery/poll commands.

External HTTP is mocked; no real quota is spent.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

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
