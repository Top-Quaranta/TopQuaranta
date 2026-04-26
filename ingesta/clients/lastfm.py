import logging
import re
import time
import unicodedata

import requests
from django.conf import settings

from music.constants import LASTFM_RATE_LIMIT, MAX_API_RETRIES

logger = logging.getLogger(__name__)

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
RATE_LIMIT_SLEEP = LASTFM_RATE_LIMIT
MAX_RETRIES = MAX_API_RETRIES

# Regex strips applied when a track is "not found" with the original name.
# Each pattern removes the matched suffix (anchored to end of string).
_TRACK_SUFFIX_STRIP = [
    # Parenthetical features / collaborations
    re.compile(
        r"\s*[\(\[]\s*(feat\.?|ft\.?|with|amb|featuring)\s+[^)\]]*[\)\]]\s*$", re.I
    ),
    # Parenthetical version/live/remix/etc tags (single trailing parenthetical)
    re.compile(
        r"\s*[\(\[]\s*("
        r"acoustic|acústica|live|en directe|en viu|directe|directo|"
        r"remix|version|versió|version|remaster(ed)?|"
        r"radio edit|edit|extended|instrumental|"
        r"bonus track|demo|single version|album version"
        r")[^)\]]*[\)\]]\s*$",
        re.I,
    ),
    # Catch-all trailing parenthetical with year reference (e.g. "(en Directe ... 2022)")
    re.compile(r"\s*[\(\[][^)\]]*\b(19|20)\d{2}\b[^)\]]*[\)\]]\s*$"),
    # Dash-separated version/live/etc suffixes
    re.compile(
        r"\s+-\s+("
        r"acoustic|acústica|live|en directe|en viu|directe|directo|"
        r"remix|version|versió|remaster(ed)?|"
        r"radio edit|edit|extended|instrumental|demo|"
        r"single version|album version|bonus track"
        r")\b.*$",
        re.I,
    ),
    # Pipe-separated alternate titles (ex. "Balh Plan de Canejan | Ball Pla
    # de Sort ..."). Last.fm indexes under the first title; drop everything
    # from the pipe onward. Applied only on retry (after the original name
    # failed) so tracks legitimately containing " | " don't lose it on the
    # first attempt.
    re.compile(r"\s*\|\s*.*$"),
]

_UNICODE_PUNCT = {
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote / apostrophe
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
}


def _normalize_unicode(text: str) -> str:
    """Replace curly quotes and dashes with ASCII equivalents."""
    for src, dst in _UNICODE_PUNCT.items():
        text = text.replace(src, dst)
    return text


def _normalize_track(name: str) -> str:
    """Aggressive normalization for retry: strip parentheticals and suffixes."""
    name = _normalize_unicode(name)
    prev = None
    while prev != name:
        prev = name
        for pattern in _TRACK_SUFFIX_STRIP:
            name = pattern.sub("", name).strip()
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _api_call(artist_name: str, track_name: str) -> tuple[dict | None, int | None]:
    """
    Single Last.fm call with retries.
    Returns (data_dict, error_code) — data_dict is the parsed track on success,
    None otherwise; error_code is the Last.fm error number (e.g. 6 = not found)
    or None for transport errors.
    """
    # Last.fm's index is in NFC; we occasionally get NFD strings from
    # Postgres (legacy imports with combining accents). Normalise here
    # so `Só` stored as O+U+0301 matches `Ó` (U+00D3) on their side.
    params = {
        "method": "track.getInfo",
        "api_key": settings.LASTFM_API_KEY,
        "artist": unicodedata.normalize("NFC", artist_name),
        "track": unicodedata.normalize("NFC", track_name),
        "format": "json",
        "autocorrect": 1,
    }

    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(RATE_LIMIT_SLEEP)
            response = requests.get(LASTFM_API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                return None, int(data.get("error", 0))

            return data.get("track", {}), None

        except requests.RequestException as exc:
            wait = 2**attempt
            logger.warning(
                "Last.fm attempt %d/%d failed for '%s'/'%s': %s — retry in %ds",
                attempt + 1,
                MAX_RETRIES,
                artist_name,
                track_name,
                exc,
                wait,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)

    return None, None


def _find_in_artist_top_tracks(
    artist_name: str, track_name: str, min_ratio: float = 0.95
) -> dict | None:
    """Search the artist's top 50 tracks for a fuzzy match to track_name.

    Returns the matched track dict (from artist.getTopTracks) or None. Used
    as a last-resort recovery when track.getInfo fails with err=6 even
    after normalization — typically for case-only variants ("+ Arcade" vs
    "+ ARCADE") or punctuation variants that Last.fm's autocorrect doesn't
    catch.

    The `min_ratio` default of 0.95 is intentionally strict: this is a
    "blind" fallback without staff review, so we only accept near-exact
    matches. Looser cases (ratio 0.80–0.95) become "real errors" that
    surface in the staff panel for manual resolution.
    """
    try:
        time.sleep(RATE_LIMIT_SLEEP)
        response = requests.get(
            LASTFM_API_URL,
            params={
                "method": "artist.getTopTracks",
                "api_key": settings.LASTFM_API_KEY,
                "artist": artist_name,
                "format": "json",
                "limit": 50,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return None

    tracks = data.get("toptracks", {}).get("track", [])
    if isinstance(tracks, dict):
        tracks = [tracks]
    if not tracks:
        return None

    # Fuzzy match against the normalized track name (strips feat., parens…).
    from difflib import SequenceMatcher

    target = _normalize_track(track_name).lower()
    best = None
    best_ratio = 0.0
    for t in tracks:
        candidate = t.get("name", "")
        ratio = SequenceMatcher(
            None, target, _normalize_track(candidate).lower()
        ).ratio()
        if ratio > best_ratio:
            best = t
            best_ratio = ratio
    if best is not None and best_ratio >= min_ratio:
        return best
    return None


def _extract_returned_names(track: dict) -> tuple[str, str]:
    """Pull the name/artist Last.fm ACTUALLY returned (after autocorrect=1).

    Returns (returned_track, returned_artist). Empty strings if absent.
    The artist block can be either a dict ({"name": "X"}) or a string,
    depending on the API response shape — cover both.
    """
    returned_track = (track.get("name") or "").strip()
    artist_field = track.get("artist", "")
    if isinstance(artist_field, dict):
        returned_artist = (artist_field.get("name") or "").strip()
    elif isinstance(artist_field, str):
        returned_artist = artist_field.strip()
    else:
        returned_artist = ""
    return returned_track, returned_artist


def get_track_info(artist_name: str, track_name: str) -> dict | None:
    """
    Fetch cumulative playcount and listeners for a track from Last.fm.
    Returns a dict with playcount/listeners AND the names Last.fm actually
    returned (may differ from the input because autocorrect=1), or None
    on any failure.

    R5: `returned_track` and `returned_artist` are the names the API
    responded with. The caller compares them against what we asked for
    and flags silent drift. Without this, a track with a common name
    can accumulate playcount from a completely different artist without
    any signal that we're conflating them.

    On Last.fm "Track not found" (error 6), retries once with a normalized
    track name (parentheticals like "(feat. X)" / "(Acoustic Version)" and
    suffixes like " - Live" stripped, plus unicode quotes converted to ASCII).
    Never raises.
    """
    track, err = _api_call(artist_name, track_name)
    if track is not None:
        rt, ra = _extract_returned_names(track)
        return {
            "playcount": int(track.get("playcount", 0)),
            "listeners": int(track.get("listeners", 0)),
            "returned_track": rt,
            "returned_artist": ra,
        }

    # Retry with normalized name only on "Track not found"
    if err == 6:
        normalized = _normalize_track(track_name)
        if normalized and normalized != track_name:
            track2, err2 = _api_call(artist_name, normalized)
            if track2 is not None:
                logger.info(
                    "Last.fm recovered '%s'/'%s' via normalization to '%s'",
                    artist_name,
                    track_name,
                    normalized,
                )
                rt, ra = _extract_returned_names(track2)
                return {
                    "playcount": int(track2.get("playcount", 0)),
                    "listeners": int(track2.get("listeners", 0)),
                    "returned_track": rt,
                    "returned_artist": ra,
                }
            err = err2 if err2 is not None else err

        # Final fallback: search the artist's top tracks for a near-exact
        # match to the track name. Catches case-only variants like
        # "+ Arcade" vs "+ ARCADE" that Last.fm's autocorrect misses.
        match = _find_in_artist_top_tracks(artist_name, track_name)
        if match is not None:
            logger.info(
                "Last.fm recovered '%s'/'%s' via top-tracks match to '%s'",
                artist_name,
                track_name,
                match.get("name", ""),
            )
            artist_field = match.get("artist") or {}
            if isinstance(artist_field, dict):
                ra = (artist_field.get("name") or "").strip()
            else:
                ra = str(artist_field).strip()
            return {
                "playcount": int(match.get("playcount", 0)),
                "listeners": int(match.get("listeners", 0)),
                "returned_track": (match.get("name") or "").strip(),
                "returned_artist": ra,
            }

    if err is not None:
        logger.warning(
            "Last.fm error %s for '%s' / '%s'",
            err,
            artist_name,
            track_name,
        )
    else:
        logger.error(
            "Last.fm: all retries exhausted for '%s' / '%s'",
            artist_name,
            track_name,
        )
    return None


# ── Artist-level endpoints ──────────────────────────────────────────────


def _artist_api_call(method: str, **extra) -> dict | None:
    """Generic helper for artist.* endpoints. Returns parsed JSON or None.

    Uses the same rate-limit + exponential-backoff retry pattern as
    `_api_call` for tracks. Errors are logged once at WARNING and the
    call returns None — never raises.
    """
    params = {
        "method": method,
        "api_key": settings.LASTFM_API_KEY,
        "format": "json",
        "autocorrect": 1,
        **extra,
    }
    if "artist" in params:
        params["artist"] = unicodedata.normalize("NFC", params["artist"])

    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(RATE_LIMIT_SLEEP)
            response = requests.get(LASTFM_API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                logger.warning(
                    "Last.fm %s error %s for %r: %s",
                    method,
                    data.get("error"),
                    params.get("artist"),
                    data.get("message"),
                )
                return None
            return data
        except requests.RequestException as exc:
            wait = 2**attempt
            logger.warning(
                "Last.fm %s attempt %d/%d failed for %r: %s — retry in %ds",
                method,
                attempt + 1,
                MAX_RETRIES,
                params.get("artist"),
                exc,
                wait,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)
    return None


def get_artist_info(artist_name: str) -> dict | None:
    """Fetch the artist.getInfo block for `artist_name`.

    Returns the raw `artist` dict from Last.fm (with `bio`, `stats`,
    `image`, `tags`, `ontour`, `url`…) or None on any failure.
    Autocorrect is on, so the returned name may differ slightly from
    the input — callers should preserve our `lastfm_nom`/`nom` rather
    than overwriting from the response.
    """
    data = _artist_api_call("artist.getInfo", artist=artist_name)
    if not data:
        return None
    return data.get("artist") or None


def get_artist_similar(artist_name: str, limit: int = 100) -> list[dict]:
    """Fetch the artist.getSimilar list for `artist_name`.

    Returns a list of similar-artist dicts as Last.fm hands them
    (`name`, `match`, `url`, `image`, `mbid`). Empty list on any
    failure. Caller is responsible for filtering by `match` threshold.
    """
    data = _artist_api_call("artist.getSimilar", artist=artist_name, limit=limit)
    if not data:
        return []
    similar = (data.get("similarartists") or {}).get("artist") or []
    if isinstance(similar, dict):
        similar = [similar]
    return similar
