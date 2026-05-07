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

# Rewrites `last.fm/music/<artist>[/...]` → `last.fm/music/+noredirect/<artist>[/...]`.
# Idempotent (skips URLs that already contain `+noredirect`) and a no-op on
# anything that isn't a Last.fm music URL. The website silently redirects
# low-listener artists to higher-listener namesakes (Fades → The Fades,
# Miley Cyrus → some other Miley); the +noredirect form opts out. This is
# the API-layer twin of `autocorrect=0` we already use.
_NOREDIRECT_RE = re.compile(
    r"^(https?://(?:www\.)?last\.fm/music/)(?!\+noredirect/)", re.I
)


def to_noredirect_url(url: str | None) -> str:
    """Force the +noredirect form on a Last.fm `/music/<artist>` URL.

    Examples:
      `https://www.last.fm/music/Fades` → `…/music/+noredirect/Fades`
      `https://www.last.fm/music/+noredirect/Fades` → unchanged
      `` / None / non-Last.fm URLs → returned as-is.
    """
    if not url:
        return url or ""
    return _NOREDIRECT_RE.sub(r"\1+noredirect/", url)


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


def _api_call(
    artist_name: str,
    track_name: str,
    *,
    autocorrect: bool = False,
    track_mbid: str | None = None,
    artist_mbid: str | None = None,
) -> tuple[dict | None, int | None]:
    """
    Single Last.fm call with retries.
    Returns (data_dict, error_code) — data_dict is the parsed track on success,
    None otherwise; error_code is the Last.fm error number (e.g. 6 = not found)
    or None for transport errors.

    Disambiguation strategy (May-2026 audit follow-up):
      * `autocorrect` defaults to **False** (= the API equivalent of
        `https://www.last.fm/music/+noredirect/<artist>`). Last.fm's
        autocorrect silently merges "Fades" → "The Fades" at the
        artist layer, which then poisons every track lookup against
        that name. We trust our curated `lastfm_nom`. Callers can
        opt back into autocorrect=1 (e.g. the alias detector) by
        passing autocorrect=True.
      * When we have a MusicBrainz `mbid` (recording- or artist-level),
        pass it. Last.fm uses the MBID over the name and skips name
        resolution entirely. Track-level recording MBIDs come from
        `Canco.mb_recording_id` (populated by `obtenir_metadata_musicbrainz`).
    """
    # Last.fm's index is in NFC; we occasionally get NFD strings from
    # Postgres (legacy imports with combining accents). Normalise here
    # so `Só` stored as O+U+0301 matches `Ó` (U+00D3) on their side.
    params: dict = {
        "method": "track.getInfo",
        "api_key": settings.LASTFM_API_KEY,
        "artist": unicodedata.normalize("NFC", artist_name),
        "track": unicodedata.normalize("NFC", track_name),
        "format": "json",
        "autocorrect": 1 if autocorrect else 0,
    }
    if track_mbid:
        params["mbid"] = track_mbid
    if artist_mbid:
        # Last.fm doesn't have a separate artist_mbid param on
        # track.getInfo, but passing it doesn't hurt — the server
        # ignores unknown params. Kept for forward compat.
        params["artist_mbid"] = artist_mbid

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


def get_track_info_literal(
    artist_name: str, track_name: str, canonical_artist: str | None = None
) -> dict | None:
    """Like `get_track_info` but with `autocorrect=0` — returns the
    LITERAL Last.fm page for the given (artist, track) string.

    Used by `obtenir_senyal` to sum playcounts across spelling
    variants of the same artist (e.g. 'Boira' + 'Böira' → one
    aggregate signal). With autocorrect=1 Last.fm silently
    redirects 'Böira' → 'Boira' and we'd double-count the canonical
    page. Returns None if the literal page doesn't exist.

    `canonical_artist`: when provided, the response's artist URL is
    compared against the canonical's. If they collapse to the same
    page (Last.fm case-folds 'ADRIÀ PUNTÍ' → 'Adrià Puntí' even
    with autocorrect=0), returns None instead of the playcount —
    otherwise we'd double-count the canonical signal. Caught
    2026-05-01 from Adrià Puntí showing pc_canon == pc_var.
    """
    params = {
        "method": "track.getInfo",
        "api_key": settings.LASTFM_API_KEY,
        "artist": unicodedata.normalize("NFC", artist_name),
        "track": unicodedata.normalize("NFC", track_name),
        "format": "json",
        "autocorrect": 0,
    }
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(RATE_LIMIT_SLEEP)
            r = requests.get(LASTFM_API_URL, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                # Track or artist not found at this literal spelling
                # — common for aliases that have a Last.fm page for
                # SOME tracks but not others.
                return None
            track = data.get("track") or {}
            # Case-fold guard: if the response's artist name (after
            # Last.fm's silent normalisation) matches the canonical
            # artist name we were asked to *not* double-count, treat
            # the alias as a duplicate page and return None.
            if canonical_artist:
                returned_artist_field = track.get("artist")
                if isinstance(returned_artist_field, dict):
                    returned_name = (returned_artist_field.get("name") or "").strip()
                else:
                    returned_name = str(returned_artist_field or "").strip()
                if (
                    returned_name
                    and returned_name.lower() == canonical_artist.lower()
                    and returned_name != artist_name
                ):
                    # Same page as canonical → don't sum.
                    return None
            return {
                "playcount": int(track.get("playcount", 0)),
                "listeners": int(track.get("listeners", 0)),
            }
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
    return None


def get_track_info(
    artist_name: str,
    track_name: str,
    *,
    track_mbid: str | None = None,
    artist_mbid: str | None = None,
) -> dict | None:
    """
    Fetch cumulative playcount and listeners for a track from Last.fm.
    Returns a dict with playcount/listeners AND the names Last.fm actually
    returned, or None on any failure.

    Disambiguation strategy (May-2026 audit follow-up):
      * `autocorrect=0` is the default (the API equivalent of the
        website's `+noredirect` URL). Trust the curated `lastfm_nom`;
        a name typo that returns None is recoverable via the err=6
        normalisation + top-tracks fallback below.
      * Pass `track_mbid` (from `Canco.mb_recording_id`) when known —
        Last.fm uses MBID over name, immune to homonym redirects.
      * Pass `artist_mbid` (from `Artista.musicbrainz_id`) for forward
        compat; the server tolerates unknown params.

    R5: `returned_track` and `returned_artist` are the names the API
    responded with. The caller compares them against what we asked for
    and flags silent drift. With autocorrect=0 they should equal the
    input, but Last.fm sometimes case-folds (caught 2026-05-01).

    On Last.fm "Track not found" (error 6), retries once with a normalized
    track name (parentheticals like "(feat. X)" / "(Acoustic Version)" and
    suffixes like " - Live" stripped, plus unicode quotes converted to ASCII).
    The retry uses **`autocorrect=1`** so case/whitespace/punctuation
    variations within the same artist's catalogue are recovered (caught
    2026-05-07: the autocorrect=0-everywhere default produced 506 extra
    errors/day for legit track-name variations like "Cançó" vs "cançó").
    The artist-level homonym risk this re-introduces is bounded by
    `_detect_drift` at the caller, which flags `corregit=True` on
    artist-name mismatch — and the ranking algorithm now filters those.
    Never raises.
    """
    track, err = _api_call(
        artist_name,
        track_name,
        track_mbid=track_mbid,
        artist_mbid=artist_mbid,
    )
    if track is not None:
        rt, ra = _extract_returned_names(track)
        return {
            "playcount": int(track.get("playcount", 0)),
            "listeners": int(track.get("listeners", 0)),
            "returned_track": rt,
            "returned_artist": ra,
        }

    # On "Track not found", retry with autocorrect=1. Two sub-cases
    # both handled by the same call when the track name has been
    # normalised, otherwise just one. autocorrect=1 here recovers
    # case-only / whitespace / punctuation variations that the literal
    # call missed; artist-level homonym risk is caught by `_detect_drift`
    # at the caller and the ranking algorithm's `corregit=False` filter.
    if err == 6:
        normalized = _normalize_track(track_name)
        retry_name = (
            normalized if (normalized and normalized != track_name) else track_name
        )
        track2, err2 = _api_call(
            artist_name,
            retry_name,
            autocorrect=True,
            track_mbid=track_mbid,
            artist_mbid=artist_mbid,
        )
        if track2 is not None:
            if retry_name != track_name:
                logger.info(
                    "Last.fm recovered '%s'/'%s' via normalization to '%s'",
                    artist_name,
                    track_name,
                    retry_name,
                )
            else:
                logger.info(
                    "Last.fm recovered '%s'/'%s' via autocorrect retry",
                    artist_name,
                    track_name,
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


def get_artist_info(
    artist_name: str, mbid: str | None = None, autocorrect: bool = True
) -> dict | None:
    """Fetch the artist.getInfo block.

    Disambiguation strategy (Sprint S Bloc D follow-up, 2026-05-06):
      * When we have a MusicBrainz ID, pass it as `mbid` — Last.fm
        looks the artist up by GID and **ignores the name argument**,
        which means no autocorrect/redirect surprises (caught: our
        Mallorcan band "Fades" silently became the English punk
        "The Fades" because Last.fm's name autocorrect prefers the
        higher-listener artist).
      * Without an MBID we fall back to name + autocorrect=1 (the
        legacy behaviour) but callers can pass `autocorrect=False`
        to disable the redirect — useful when staff has flagged a
        homonym collision.

    Returns the raw `artist` dict from Last.fm or None on any failure.
    """
    params: dict = {"artist": artist_name}
    if mbid:
        # `mbid` wins over `artist` on Last.fm's side, but pass both
        # so that on the rare case the MBID is rejected (deleted
        # entry, malformed) we degrade to the name lookup.
        params["mbid"] = mbid
    if not autocorrect:
        params["autocorrect"] = "0"
    data = _artist_api_call("artist.getInfo", **params)
    if not data:
        return None
    return data.get("artist") or None


def get_artist_similar(
    artist_name: str,
    limit: int = 100,
    mbid: str | None = None,
    autocorrect: bool = True,
) -> list[dict]:
    """Fetch the artist.getSimilar list. Same MBID-disambiguation
    strategy as `get_artist_info` — when we have an MBID, pass it
    so Last.fm bypasses name-based autocorrect. Callers can also
    force `autocorrect=False` to suppress the silent name-merge
    even on the no-MBID path (the API equivalent of the web
    `/music/+noredirect/<name>` trick)."""
    params: dict = {"artist": artist_name, "limit": limit}
    if mbid:
        params["mbid"] = mbid
    if not autocorrect:
        params["autocorrect"] = "0"
    data = _artist_api_call("artist.getSimilar", **params)
    if not data:
        return []
    similar = (data.get("similarartists") or {}).get("artist") or []
    if isinstance(similar, dict):
        similar = [similar]
    return similar
