"""Unit tests for `web.api.staff._spotify_url.parse_track_id`.

Store-and-trust format validation only — no Spotify API call. Covers the
three accepted forms (URL, URI, bare id), the locale-prefixed URL, the
`?si=` query string, and every rejection path (album/artist/playlist,
malformed id, empty).
"""

from __future__ import annotations

import pytest

from web.api.staff._spotify_url import SpotifyUrlError, parse_track_id

VALID = "4cOdK2wGLETKBW3PvgPWqT"  # 22-char base62, shape only


@pytest.mark.parametrize(
    "raw",
    [
        VALID,
        f"spotify:track:{VALID}",
        f"https://open.spotify.com/track/{VALID}",
        f"https://open.spotify.com/track/{VALID}?si=abc123DEF456",
        f"http://open.spotify.com/track/{VALID}",
        f"https://open.spotify.com/intl-ca/track/{VALID}",
        f"  https://open.spotify.com/track/{VALID}  ",
    ],
)
def test_accepts_track_forms(raw):
    assert parse_track_id(raw) == VALID


@pytest.mark.parametrize(
    "raw",
    [
        f"https://open.spotify.com/album/{VALID}",
        f"https://open.spotify.com/artist/{VALID}",
        f"https://open.spotify.com/playlist/{VALID}",
        f"spotify:album:{VALID}",
        f"spotify:artist:{VALID}",
    ],
)
def test_rejects_non_track_references(raw):
    with pytest.raises(SpotifyUrlError):
        parse_track_id(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "not a url",
        "https://open.spotify.com/track/short",
        "https://example.com/track/" + VALID,
        VALID + "EXTRA",  # 27 chars, not 22
        "spotify:track:" + VALID + "x",  # wrong length in URI
    ],
)
def test_rejects_malformed_input(raw):
    with pytest.raises(SpotifyUrlError):
        parse_track_id(raw)
