# Spec: docs/architecture/web.md
"""Parse and validate a manual YouTube *video* reference.

Store-and-trust, same contract as `_spotify_url`: we validate the
**format** of a video id and never spend a quota unit checking it. Staff
is looking at the video when they paste it, and a `videos.list` call to
confirm would cost the one resource this whole integration is rationed
by (see `docs/architecture/ingesta.md` §YouTube).

Channel / playlist / user URLs are rejected explicitly: a channel goes
in the artist's field, not the song's, and the error should say so
instead of storing an id that polls forever and returns nothing.
"""

from __future__ import annotations

import re

# YouTube video ids are 11 chars of [A-Za-z0-9_-]. The length is fixed
# and has been since 2007; anything else is a channel id (UC + 22), a
# playlist (PL…) or a typo.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
# watch?v=…, youtu.be/…, /embed/…, /shorts/…, /live/…
_URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^ ]*&)?v=|embed/|shorts/|live/|v/)"
    r"|youtu\.be/)(?P<id>[A-Za-z0-9_-]{11})"
)
# The shapes that are NOT a video, so the message can name the mistake.
_CANAL_RE = re.compile(r"youtube\.com/(channel/|@|c/|user/)", re.I)
_LLISTA_RE = re.compile(r"youtube\.com/playlist\?", re.I)


class YoutubeUrlError(ValueError):
    """The input is not a usable YouTube *video* reference."""


def parse_video_id(raw: str) -> str:
    """Return the 11-char video id from a URL / bare id.

    Accepts `watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/live/` and
    a bare id, with or without extra query parameters (`&t=`, `?si=`).
    Raises :class:`YoutubeUrlError` on a channel, a playlist or garbage.
    Never calls the YouTube API.
    """
    value = (raw or "").strip()
    if not value:
        raise YoutubeUrlError("Cal un enllaç o id de YouTube.")

    m = _URL_RE.search(value)
    if m:
        return m.group("id")

    if _ID_RE.match(value):
        return value

    if _CANAL_RE.search(value):
        raise YoutubeUrlError(
            "Això és un canal de YouTube, no un vídeo. El canal va a la "
            "fitxa de l'artista; ací fa falta l'enllaç d'una cançó."
        )
    if _LLISTA_RE.search(value):
        raise YoutubeUrlError(
            "Això és una llista de reproducció, no un vídeo. Obri la "
            "cançó concreta i copia'n l'enllaç."
        )
    raise YoutubeUrlError(
        "Format no reconegut. Enganxa l'enllaç del vídeo "
        "(youtube.com/watch?v=… o youtu.be/…)."
    )
