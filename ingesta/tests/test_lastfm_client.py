from unittest.mock import patch

import pytest
import requests

from ingesta.clients.lastfm import (
    MAX_RETRIES,
    RATE_LIMIT_SLEEP,
    get_track_info,
    to_noredirect_url,
)


class TestToNoredirectUrl:
    def test_rewrites_canonical_form(self):
        assert (
            to_noredirect_url("https://www.last.fm/music/Fades")
            == "https://www.last.fm/music/+noredirect/Fades"
        )

    def test_idempotent_on_already_noredirect(self):
        url = "https://www.last.fm/music/+noredirect/Fades"
        assert to_noredirect_url(url) == url

    def test_preserves_path_after_artist(self):
        assert (
            to_noredirect_url("https://www.last.fm/music/Manel/_/En+la+Pell")
            == "https://www.last.fm/music/+noredirect/Manel/_/En+la+Pell"
        )

    def test_handles_http_and_no_www(self):
        assert (
            to_noredirect_url("http://last.fm/music/Boira")
            == "http://last.fm/music/+noredirect/Boira"
        )

    def test_noop_on_empty(self):
        assert to_noredirect_url("") == ""
        assert to_noredirect_url(None) == ""

    def test_noop_on_non_lastfm_url(self):
        assert (
            to_noredirect_url("https://www.deezer.com/artist/123")
            == "https://www.deezer.com/artist/123"
        )


FAKE_API_KEY = "test_api_key_123"


@pytest.fixture(autouse=True)
def lastfm_settings(settings):
    settings.LASTFM_API_KEY = FAKE_API_KEY


class TestGetTrackInfoSuccess:
    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_success(self, mock_get, mock_sleep):
        """Mocked 200 → correct playcount and listeners."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "track": {
                "name": "Benvolguts",
                "artist": {"name": "Txarango"},
                "playcount": "12345",
                "listeners": "678",
            }
        }

        result = get_track_info("Txarango", "Benvolguts")

        # R5: response includes the names Last.fm actually returned so the
        # caller can detect silent autocorrect drift.
        assert result == {
            "playcount": 12345,
            "listeners": 678,
            "returned_track": "Benvolguts",
            "returned_artist": "Txarango",
        }
        mock_get.assert_called_once()
        params = mock_get.call_args[1]["params"]
        assert params["artist"] == "Txarango"
        assert params["track"] == "Benvolguts"
        assert params["api_key"] == FAKE_API_KEY
        # May-2026 audit: default flipped to autocorrect=0 (= the API
        # equivalent of the website's `+noredirect` URL) to defend
        # against silent homonym redirects (Fades → The Fades style).
        assert params["autocorrect"] == 0


class TestGetTrackInfoTrackNotFound:
    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_track_not_found(self, mock_get, mock_sleep):
        """Last.fm error 6 → returns None, no exception.

        The client makes three calls: (1) track.getInfo with
        autocorrect=0 returns err=6, (2) track.getInfo retry with
        autocorrect=1 also returns err=6, (3) a last-resort
        artist.getTopTracks fallback. All mocked to err=6; no
        rate-limit retries fire on API-level errors.

        2026-05-07 follow-up: the autocorrect=1 retry runs
        unconditionally on err=6 (was previously gated on
        `normalized != track_name`, which skipped it for case-only
        mismatches and left the cron with ~12 % spurious errors).

        Property asserted now: the result is None (no raise) and at
        least one retry with `autocorrect=1` was attempted for the same
        artist/track. The ladder length is not pinned, so an extra
        fallback rung can be added without touching this test.
        """
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "error": 6,
            "message": "Track not found",
        }

        result = get_track_info("Unknown Artist", "Unknown Track")

        assert result is None
        sent = [c.kwargs["params"] for c in mock_get.call_args_list]
        assert any(
            p.get("autocorrect") == 1
            and p.get("method") == "track.getInfo"
            and p.get("artist") == "Unknown Artist"
            for p in sent
        ), sent


class TestGetTrackInfoTopTracksFallback:
    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_fuzzy_recovery_via_top_tracks(self, mock_get, mock_sleep):
        """A case-only variant ('+ Arcade' vs '+ ARCADE') is recovered
        via the artist.getTopTracks fallback when track.getInfo fails.
        """
        responses = [
            # 1) track.getInfo(+ Arcade, autocorrect=0) → err=6
            {"error": 6, "message": "Track not found"},
            # 2) track.getInfo(+ Arcade, autocorrect=1) retry → still err=6
            #    (the case-folded variant '+ ARCADE' is not what Last.fm
            #     autocorrects to either; it requires fuzzy match against
            #     the artist's top tracks). 2026-05-07 added.
            {"error": 6, "message": "Track not found"},
            # 3) artist.getTopTracks → contains + ARCADE with playcount
            {
                "toptracks": {
                    "track": [
                        {
                            "name": "+ ARCADE",
                            "playcount": "33",
                            "listeners": "7",
                            "artist": {"name": "Adrien Broadway"},
                        },
                        {
                            "name": "Other Song",
                            "playcount": "10",
                            "listeners": "3",
                            "artist": {"name": "Adrien Broadway"},
                        },
                    ]
                }
            },
        ]
        call_iter = iter(responses)

        def fake_get(*args, **kwargs):
            resp = mock_get.return_value
            resp.status_code = 200
            resp.raise_for_status.return_value = None
            resp.json.return_value = next(call_iter)
            return resp

        mock_get.side_effect = fake_get

        result = get_track_info("Adrien Broadway", "+ Arcade")

        assert result is not None
        assert result["playcount"] == 33
        assert result["listeners"] == 7
        assert result["returned_track"] == "+ ARCADE"
        assert result["returned_artist"] == "Adrien Broadway"


class TestGetTrackInfoNetworkError:
    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_network_error(self, mock_get, mock_sleep):
        """RequestException → None after MAX_RETRIES."""
        mock_get.side_effect = requests.RequestException("Connection refused")

        result = get_track_info("Txarango", "Benvolguts")

        assert result is None
        assert mock_get.call_count == MAX_RETRIES


class TestGetTrackInfoRateLimit:
    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_rate_limit_sleep(self, mock_get, mock_sleep):
        """time.sleep called with RATE_LIMIT_SLEEP before each request.

        Property asserted now: on a virtual clock, every request to
        Last.fm fires at least RATE_LIMIT_SLEEP after the previous one
        (the first one after start). The exact sleep argument / call
        order is not pinned."""
        clock = {"t": 0.0}
        stamps: list[float] = []
        mock_sleep.side_effect = lambda s: clock.__setitem__("t", clock["t"] + s)

        def fake_get(*args, **kwargs):
            stamps.append(clock["t"])
            resp = mock_get.return_value
            resp.status_code = 200
            resp.raise_for_status.return_value = None
            resp.json.return_value = {"track": {"playcount": "1", "listeners": "1"}}
            return resp

        mock_get.side_effect = fake_get

        get_track_info("Zoo", "Bona Nit")
        get_track_info("Zoo", "Estiu")

        assert len(stamps) >= 2
        gaps = [b - a for a, b in zip([0.0] + stamps, stamps)]
        assert all(g >= RATE_LIMIT_SLEEP - 1e-9 for g in gaps), gaps


class TestMbidFallback:
    """Last.fm resolves `mbid` INSTEAD of artist+track: an MBID it hasn't
    indexed answers error 6 and the names sent alongside are never
    consulted. A successful MusicBrainz match therefore used to delete the
    track's Last.fm signal permanently (caught 2026-08-10: Auxili's
    "Tarrinetes al Sol", 316 plays by name, error 6 by MBID, every day
    since MB matched it on 10 July)."""

    @staticmethod
    def _responses(mock_get, sequence):
        it = iter(sequence)

        def fake_get(*args, **kwargs):
            resp = mock_get.return_value
            resp.raise_for_status.return_value = None
            resp.json.return_value = next(it)
            return resp

        mock_get.side_effect = fake_get

    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_retries_without_mbid_and_recovers(self, mock_get, mock_sleep):
        self._responses(
            mock_get,
            [
                {"error": 6, "message": "Track not found"},  # with mbid
                {  # same call without the mbid
                    "track": {
                        "name": "Tarrinetes al sol",
                        "artist": {"name": "Auxili"},
                        "playcount": "316",
                        "listeners": "98",
                    }
                },
            ],
        )

        result = get_track_info(
            "Auxili", "Tarrinetes al Sol", track_mbid="1e36075e-ff6c-4159-9cd2-a"
        )

        assert result["playcount"] == 316
        assert mock_get.call_count == 2
        assert "mbid" in mock_get.call_args_list[0][1]["params"]
        assert "mbid" not in mock_get.call_args_list[1][1]["params"]

    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_no_extra_call_when_there_was_no_mbid(self, mock_get, mock_sleep):
        """Without an MBID there is nothing to drop: the ladder must not
        gain a redundant call for every genuinely-missing track.

        Property asserted now: no request carries an `mbid`, and no two
        requests send the identical params (a redundant "retry without
        the mbid" would be a byte-for-byte repeat of the literal call).
        The ladder length itself is not pinned."""
        self._responses(mock_get, [{"error": 6}] * 6)

        assert get_track_info("Auxili", "Tu Contra el Món") is None
        sent = [c.kwargs["params"] for c in mock_get.call_args_list]
        assert sent, "at least the literal call must fire"
        assert all("mbid" not in p for p in sent)
        as_keys = [tuple(sorted(p.items())) for p in sent]
        assert len(set(as_keys)) == len(as_keys), "redundant duplicate call"

    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_mbid_is_dropped_from_the_normalisation_retry_too(
        self, mock_get, mock_sleep
    ):
        """Once we know Last.fm doesn't have the MBID, no later call in the
        ladder should carry it either — otherwise the retry inherits the
        same dead end."""
        self._responses(mock_get, [{"error": 6}] * 5)

        get_track_info("X", "Y (Remaster 2015)", track_mbid="dead-beef")

        carried = [
            "mbid" in c[1]["params"]
            for c in mock_get.call_args_list
            if c[1]["params"].get("method") == "track.getInfo"
        ]
        assert carried[0] is True
        assert not any(carried[1:])


class TestVersionsNoHeretenLOriginal:
    """Un remix, un directe o una acústica no són la cançó original.

    Last.fm sovint no en té pàgina. La cadena de recuperació llevava el
    sufix i es quedava amb el títol pelat, que és una gravació distinta
    amb el públic de l'original: el 22/08/2026 «DIUMENGE SENSE DRAMA
    (Remix)» de Mon DJ va entrar al número 2 de PPCC amb les 705
    escoltes d'Els Catarres i dos dies de vida.

    El que ha de continuar funcionant és el cas contrari: «(Remaster)»,
    «(feat. X)» o un canvi de majúscules són la mateixa cinta i s'han de
    poder recuperar pel títol pelat.
    """

    @staticmethod
    def _respostes(mock_get, per_titol):
        """Contesta segons el `track` que demana cada crida."""

        def fake_get(*args, **kwargs):
            params = kwargs.get("params", {})
            demanat = params.get("track") or params.get("artist")
            resp = mock_get.return_value
            resp.status_code = 200
            resp.raise_for_status.return_value = None
            resp.json.return_value = per_titol.get(
                demanat, {"error": 6, "message": "Track not found"}
            )
            return resp

        mock_get.side_effect = fake_get

    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_un_remix_desconegut_no_hereta_les_escoltes_de_loriginal(
        self, mock_get, mock_sleep
    ):
        self._respostes(
            mock_get,
            {
                # El títol pelat SÍ que existeix i té molt de públic.
                "DIUMENGE SENSE DRAMA": {
                    "track": {
                        "name": "DIUMENGE SENSE DRAMA",
                        "playcount": "705",
                        "listeners": "273",
                        "artist": {"name": "Els Catarres"},
                    }
                },
            },
        )

        assert (
            get_track_info("Els Catarres", "DIUMENGE SENSE DRAMA (Remix)") is None
        ), "el remix s'ha quedat amb les escoltes de l'original"

    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_un_directe_no_casa_amb_lestudi_a_les_top_tracks(
        self, mock_get, mock_sleep
    ):
        self._respostes(
            mock_get,
            {
                "Lluna": {
                    "toptracks": {
                        "track": [
                            {
                                "name": "Plora",
                                "playcount": "9000",
                                "listeners": "800",
                                "artist": {"name": "Lluna"},
                            }
                        ]
                    }
                },
            },
        )

        assert (
            get_track_info("Lluna", "Plora (En Directe a La Cova del Drac)") is None
        ), "el directe ha casat amb la gravació d'estudi"

    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_un_remaster_sí_que_es_recupera_pel_títol_pelat(self, mock_get, mock_sleep):
        self._respostes(
            mock_get,
            {
                "L'Empordà": {
                    "track": {
                        "name": "L'Empordà",
                        "playcount": "4200",
                        "listeners": "900",
                        "artist": {"name": "Sopa de Cabra"},
                    }
                },
            },
        )

        result = get_track_info("Sopa de Cabra", "L'Empordà (Remaster 2015)")

        assert result is not None, "un remaster és la mateixa cinta i s'ha de recuperar"
        assert result["playcount"] == 4200
