from unittest.mock import call, patch

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

        The client makes two calls: (1) track.getInfo returns err=6, and
        (2) a last-resort artist.getTopTracks fallback. Both mocked to
        return the same err=6 shape; the fallback returns empty tracks
        and the whole chain yields None. No rate-limit retries on
        API-level errors.
        """
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "error": 6,
            "message": "Track not found",
        }

        result = get_track_info("Unknown Artist", "Unknown Track")

        assert result is None
        # One getInfo + one getTopTracks fallback. The normalized-name
        # retry is skipped because _normalize_track("Unknown Track") ==
        # "Unknown Track".
        assert mock_get.call_count == 2


class TestGetTrackInfoTopTracksFallback:
    @patch("ingesta.clients.lastfm.time.sleep")
    @patch("ingesta.clients.lastfm.requests.get")
    def test_fuzzy_recovery_via_top_tracks(self, mock_get, mock_sleep):
        """A case-only variant ('+ Arcade' vs '+ ARCADE') is recovered
        via the artist.getTopTracks fallback when track.getInfo fails.
        """
        responses = [
            # track.getInfo(+ Arcade) → err=6
            {"error": 6, "message": "Track not found"},
            # artist.getTopTracks → contains + ARCADE with playcount
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
        """time.sleep called with RATE_LIMIT_SLEEP before each request."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "track": {"playcount": "1", "listeners": "1"}
        }

        get_track_info("Zoo", "Bona Nit")

        # First call to sleep should be the rate limit
        assert mock_sleep.call_args_list[0] == call(RATE_LIMIT_SLEEP)
