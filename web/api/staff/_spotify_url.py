# Spec: docs/architecture/web.md
"""Parse and validate a manual Spotify *track* reference.

Store-and-trust (see docs/architecture/playlists.md "Manual Spotify id"):
we validate only the *format* of a track id, never calling the Spotify
API. Staff is looking at the real track in Spotify when they paste it, so
a 22-char base62 id is taken at face value. Album / artist / playlist /
episode references are rejected because Process A builds
`spotify:track:<id>` URIs only.
"""

from __future__ import annotations

import re

# Spotify base62 ids are exactly 22 chars from [0-9A-Za-z].
_ID_RE = re.compile(r"^[0-9A-Za-z]{22}$")
# open.spotify.com/<kind>/<id>, tolerating an `intl-xx/` locale prefix
# and a trailing `?si=...` query string.
_URL_RE = re.compile(
    r"open\.spotify\.com/(?:intl-[a-z]{2}/)?"
    r"(?P<kind>track|album|artist|playlist|episode|show)/"
    r"(?P<id>[0-9A-Za-z]{22})"
)
# spotify:<kind>:<id> URI form.
_URI_RE = re.compile(
    r"^spotify:(?P<kind>track|album|artist|playlist|episode|show):"
    r"(?P<id>[0-9A-Za-z]{22})$"
)


class SpotifyUrlError(ValueError):
    """The input is not a usable Spotify *track* reference."""


def _wrong_kind_msg(kind: str) -> str:
    label = {
        "album": "un àlbum",
        "artist": "un artista",
        "playlist": "una llista",
        "episode": "un episodi",
        "show": "un podcast",
    }.get(kind, f"un {kind}")
    return f"Això és {label} de Spotify, no una cançó (track)."


def parse_track_id(raw: str) -> str:
    """Return the 22-char track id from a URL / URI / bare id.

    Accepts:
      * ``https://open.spotify.com/track/<id>[?si=...]``
      * ``https://open.spotify.com/intl-ca/track/<id>``
      * ``spotify:track:<id>``
      * ``<id>`` (a bare 22-char base62 id)

    Raises :class:`SpotifyUrlError` for album/artist/playlist references,
    malformed ids or empty input. Never calls the Spotify API.
    """
    value = (raw or "").strip()
    if not value:
        raise SpotifyUrlError("Cal un enllaç o id de Spotify.")

    if _ID_RE.match(value):
        return value

    m = _URI_RE.match(value)
    if m:
        if m.group("kind") != "track":
            raise SpotifyUrlError(_wrong_kind_msg(m.group("kind")))
        return m.group("id")

    m = _URL_RE.search(value)
    if m:
        if m.group("kind") != "track":
            raise SpotifyUrlError(_wrong_kind_msg(m.group("kind")))
        return m.group("id")

    raise SpotifyUrlError(
        "Format no reconegut. Enganxa l'enllaç «Comparteix → Copia "
        "l'enllaç de la cançó» de Spotify (open.spotify.com/track/…)."
    )
