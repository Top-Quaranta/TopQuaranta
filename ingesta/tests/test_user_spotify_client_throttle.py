"""Tests for the rate-limit handling in UserSpotifyClient.

Focus areas (post-2026-05-22 incident):
  * Throttle between API calls is applied.
  * 429 with a short Retry-After (<=60s) sleeps and retries.
  * 429 with a long Retry-After (>60s) raises RateLimitedError
    INSTEAD of sleeping. This is the core fix; the old code blocked
    the cron for 24h on a 86076s value.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from ingesta.clients.spotify import RateLimitedError, UserSpotifyClient


def _fake_auth():
    """Lightweight stand-in for a SpotifyAuth row."""
    auth = MagicMock()
    auth.refresh_token = "EXEMPLE_refresh_token"
    return auth


def _mock_response(status: int, body: dict | None = None, headers=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = body or {}
    if status >= 400:
        # `raise_for_status` raises for 4xx/5xx; our client checks the
        # known cases (401, 429) BEFORE calling it, so set it here so
        # any unexpected status surfaces in tests. The HTTPError must
        # carry the response back to the caller because get_track /
        # get_artist read `exc.response.status_code` to special-case 404.
        err = requests.HTTPError(f"HTTP {status}")
        err.response = r
        r.raise_for_status.side_effect = err
    else:
        r.raise_for_status.return_value = None
    return r


@pytest.fixture
def patched_token():
    """Skip the OAuth round trip — we don't need to test refresh here."""
    with patch.object(UserSpotifyClient, "_refresh_access_token") as m:
        # The method itself just sets _access_token; emulate that.
        def set_token(self):
            self._access_token = "fake_access_token"

        m.side_effect = lambda: setattr(
            m._mock_self if hasattr(m, "_mock_self") else None,
            "_access_token",
            "fake_access_token",
        )
        # Simpler: instead, patch _headers to bypass refresh entirely.
        with patch.object(
            UserSpotifyClient,
            "_headers",
            return_value={"Authorization": "Bearer fake"},
        ):
            yield


def test_throttle_sleeps_between_calls(patched_token):
    """Default throttle = 0.2s; we override to 0.05 to keep tests fast
    and assert that `time.sleep(throttle)` is the first call inside
    `_request`."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0.05)
    with (
        patch("ingesta.clients.spotify.time.sleep") as mock_sleep,
        patch(
            "ingesta.clients.spotify.requests.request",
            return_value=_mock_response(200, {"tracks": {"items": []}}),
        ),
    ):
        client.search_isrc("EXISRC123")
    # Sleep called at least once with the throttle value.
    sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
    assert 0.05 in sleep_args


def test_429_short_retry_after_sleeps_and_retries(patched_token):
    """Retry-After=5s -> sleep 5s, retry, succeed on second attempt."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0)
    first = _mock_response(429, headers={"Retry-After": "5"})
    second = _mock_response(200, {"tracks": {"items": []}})
    with (
        patch("ingesta.clients.spotify.time.sleep") as mock_sleep,
        patch("ingesta.clients.spotify.requests.request", side_effect=[first, second]),
    ):
        result = client.search_isrc("EXISRC456")
    assert result is None  # empty items
    # Sleep called with 5 (the Retry-After value) on the retry path.
    assert 5 in [call.args[0] for call in mock_sleep.call_args_list]


def test_429_long_retry_after_raises_instead_of_sleeping(patched_token):
    """Retry-After=86076s (24h) -> raise RateLimitedError; the client
    must NEVER call time.sleep with the long value. This is the core
    regression-guard for the 2026-05-22 outage."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0, max_retry_after_s=60)
    long_429 = _mock_response(429, headers={"Retry-After": "86076"})
    with (
        patch("ingesta.clients.spotify.time.sleep") as mock_sleep,
        patch("ingesta.clients.spotify.requests.request", return_value=long_429),
    ):
        with pytest.raises(RateLimitedError) as exc_info:
            client.search_isrc("EXISRC789")
    assert exc_info.value.retry_after_s == 86076
    # The long value MUST NOT appear in any sleep call.
    sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
    assert 86076 not in sleep_args


def test_429_at_tolerance_boundary_sleeps(patched_token):
    """Retry-After exactly equal to max_retry_after_s should sleep (not
    raise) so we don't reject genuinely small windows."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0, max_retry_after_s=60)
    boundary = _mock_response(429, headers={"Retry-After": "60"})
    ok = _mock_response(200, {"tracks": {"items": []}})
    with (
        patch("ingesta.clients.spotify.time.sleep"),
        patch("ingesta.clients.spotify.requests.request", side_effect=[boundary, ok]),
    ):
        result = client.search_isrc("EXISRCBND")
    assert result is None  # success path; no raise


def test_replace_playlist_tracks_uses_items_endpoint(patched_token):
    """Spotify deprecated /playlists/{id}/tracks on 2026-03 and the old
    path now returns 403 to Development Mode apps. The client MUST hit
    /playlists/{id}/items. Regression guard so a future refactor can't
    silently revert the path."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0)
    ok = _mock_response(200, {"snapshot_id": "fake_snap"})
    with patch(
        "ingesta.clients.spotify.requests.request", return_value=ok
    ) as mock_request:
        client.replace_playlist_tracks("EXEMPLE_PID", ["spotify:track:abc"])
    # First (and only) call: PUT to /items, NOT /tracks.
    call = mock_request.call_args_list[0]
    method = call.args[0]
    url = call.args[1]
    assert method == "PUT"
    assert "/playlists/EXEMPLE_PID/items" in url
    assert "/tracks" not in url


def test_replace_playlist_tracks_chunks_via_items_endpoint(patched_token):
    """Chunking branch (>100 URIs) must also use /items, not /tracks."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0)
    ok = _mock_response(200, {"snapshot_id": "fake_snap"})
    with patch(
        "ingesta.clients.spotify.requests.request", return_value=ok
    ) as mock_request:
        uris = [f"spotify:track:exempl{i:04d}" for i in range(150)]
        client.replace_playlist_tracks("EXEMPLE_PID2", uris)
    # First call PUT, second call POST, both to /items.
    assert len(mock_request.call_args_list) == 2
    first, second = mock_request.call_args_list
    assert first.args[0] == "PUT"
    assert "/items" in first.args[1] and "/tracks" not in first.args[1]
    assert second.args[0] == "POST"
    assert "/items" in second.args[1] and "/tracks" not in second.args[1]


def test_custom_throttle_overrides_default():
    """A `throttle_s=1.5` passed in __init__ becomes the per-request
    sleep value."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=1.5)
    assert client._throttle_s == 1.5
    # And the default for the max retry tolerance is preserved.
    assert client._max_retry_after_s == UserSpotifyClient.DEFAULT_MAX_RETRY_AFTER_S


# ── get_track / get_artist (FASE 2 of Process A/B split) ─────────────


def test_get_track_returns_full_json(patched_token):
    """Happy path: a fresh GET /v1/tracks/{id} returns the populated
    track dict with the fields ADR-0012 confirms are live."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0)
    body = {
        "id": "ABCD1",
        "name": "EXEMPLE Track",
        "duration_ms": 302000,
        "explicit": False,
        "is_playable": True,
        "track_number": 1,
        "disc_number": 1,
        "external_ids": {"isrc": "QT3TB2546815"},
        "album": {
            "album_type": "single",
            "release_date": "2026-01-19",
            "images": [
                {"url": "https://e/640.jpg", "width": 640, "height": 640},
                {"url": "https://e/300.jpg", "width": 300, "height": 300},
            ],
        },
        "artists": [
            {"id": "ARTID1", "name": "EXEMPLE Artist", "uri": "spotify:artist:ARTID1"}
        ],
        # Wave One nulls — included in the mock so the client must
        # tolerate their presence (it just passes the dict through).
        "popularity": None,
        "preview_url": None,
        "available_markets": None,
    }
    with patch(
        "ingesta.clients.spotify.requests.request",
        return_value=_mock_response(200, body),
    ) as mock_req:
        result = client.get_track("ABCD1")
    # URL contains /tracks/{id}; method is GET.
    assert mock_req.call_args.args[0] == "GET"
    assert "/tracks/ABCD1" in mock_req.call_args.args[1]
    # And the body comes through unchanged.
    assert result["id"] == "ABCD1"
    assert result["external_ids"]["isrc"] == "QT3TB2546815"
    assert len(result["album"]["images"]) == 2


def test_get_track_returns_none_on_404(patched_token):
    """A removed-from-catalogue ID returns None, not a raise."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0)
    with patch(
        "ingesta.clients.spotify.requests.request",
        return_value=_mock_response(404, {"error": {"status": 404}}),
    ):
        result = client.get_track("REMOVED")
    assert result is None


def test_get_track_empty_id_returns_none(patched_token):
    """Defensive: empty input doesn't even hit the network."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0)
    with patch("ingesta.clients.spotify.requests.request") as mock_req:
        result = client.get_track("")
    assert result is None
    mock_req.assert_not_called()


def test_get_artist_returns_json(patched_token):
    """Happy path: GET /v1/artists/{id} returns the artist dict."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0)
    body = {
        "id": "ARTID1",
        "name": "EXEMPLE Artist",
        "uri": "spotify:artist:ARTID1",
        "images": [
            {"url": "https://a/640.jpg", "width": 640, "height": 640},
        ],
        "external_urls": {"spotify": "https://open.spotify.com/artist/ARTID1"},
        "genres": [],
        "followers": None,
        "popularity": None,
    }
    with patch(
        "ingesta.clients.spotify.requests.request",
        return_value=_mock_response(200, body),
    ) as mock_req:
        result = client.get_artist("ARTID1")
    assert mock_req.call_args.args[0] == "GET"
    assert "/artists/ARTID1" in mock_req.call_args.args[1]
    assert result["id"] == "ARTID1"
    assert result["genres"] == []


def test_get_artist_404_returns_none(patched_token):
    client = UserSpotifyClient(_fake_auth(), throttle_s=0)
    with patch(
        "ingesta.clients.spotify.requests.request",
        return_value=_mock_response(404, {"error": {"status": 404}}),
    ):
        assert client.get_artist("REMOVED") is None


def test_get_track_throttle_applied(patched_token):
    """Each fetch sleeps the configured throttle before firing,
    matching the search_isrc behaviour."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0.07)
    with (
        patch("ingesta.clients.spotify.time.sleep") as mock_sleep,
        patch(
            "ingesta.clients.spotify.requests.request",
            return_value=_mock_response(200, {"id": "x", "artists": []}),
        ),
    ):
        client.get_track("x")
    assert 0.07 in [c.args[0] for c in mock_sleep.call_args_list]


def test_get_track_long_retry_after_raises(patched_token):
    """The same RateLimitedError contract as search_isrc / writes:
    Retry-After > tolerance -> raise, don't sleep."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=0, max_retry_after_s=60)
    long_429 = _mock_response(429, headers={"Retry-After": "86076"})
    with (
        patch("ingesta.clients.spotify.time.sleep") as mock_sleep,
        patch("ingesta.clients.spotify.requests.request", return_value=long_429),
    ):
        with pytest.raises(RateLimitedError):
            client.get_track("x")
    # The long value MUST NOT be slept.
    assert 86076 not in [c.args[0] for c in mock_sleep.call_args_list]
