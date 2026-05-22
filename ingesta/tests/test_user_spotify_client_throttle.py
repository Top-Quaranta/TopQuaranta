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
        # any unexpected status surfaces in tests.
        r.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
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


def test_custom_throttle_overrides_default():
    """A `throttle_s=1.5` passed in __init__ becomes the per-request
    sleep value."""
    client = UserSpotifyClient(_fake_auth(), throttle_s=1.5)
    assert client._throttle_s == 1.5
    # And the default for the max retry tolerance is preserved.
    assert client._max_retry_after_s == UserSpotifyClient.DEFAULT_MAX_RETRY_AFTER_S
