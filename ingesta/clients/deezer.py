import logging
import time
import unicodedata
from datetime import date

import requests

from music.constants import DEEZER_RATE_LIMIT, MAX_API_RETRIES

logger = logging.getLogger(__name__)

API_BASE = "https://api.deezer.com"
RATE_LIMIT_SLEEP = DEEZER_RATE_LIMIT
MAX_RETRIES = MAX_API_RETRIES

# Deezer quota error: code 4, "Quota limit exceeded".
# No rate-limit headers are returned — the only signal is the error response.
# Once hit, all subsequent calls fail until the quota resets (~next day).
# This flag stops wasting requests after the first quota error.
_quota_exhausted = False

# Deezer error codes that mean "stop calling":
# 4 = Quota limit exceeded (daily IP-based limit, undocumented exact number)
_QUOTA_ERROR_CODES = {4}


def quota_exhausted() -> bool:
    """Check if Deezer quota has been hit this session."""
    return _quota_exhausted


def _normalize(name: str) -> str:
    """Lowercase, strip accents, strip whitespace."""
    name = name.strip().lower()
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _get(url: str, params: dict | None = None) -> dict | None:
    """GET with retry and rate limiting. Returns parsed JSON or None."""
    global _quota_exhausted

    if _quota_exhausted:
        return None

    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(RATE_LIMIT_SLEEP)
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                error = data["error"]
                error_code = error.get("code")
                if error_code in _QUOTA_ERROR_CODES:
                    _quota_exhausted = True
                    logger.error(
                        "Quota Deezer exhaurida — reintenta demà "
                        "(error code=%s, message='%s')",
                        error_code,
                        error.get("message", ""),
                    )
                    return None
                logger.warning("Deezer error for %s: %s", url, error)
                return None

            return data

        except requests.RequestException as exc:
            wait = 2**attempt
            logger.warning(
                "Deezer attempt %d/%d failed for %s: %s — retry in %ds",
                attempt + 1,
                MAX_RETRIES,
                url,
                exc,
                wait,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)

    logger.error("Deezer: all retries exhausted for %s", url)
    return None


def search_artist(nom: str) -> dict | None:
    """
    Search Deezer for an artist by name.
    Returns {"id": int, "name": str} for the best match, or None.

    Matching strategy:
    1. Exact normalized name match
    2. Containment (Deezer name contains ours or vice versa)
    Never returns the first result without verification.
    """
    data = _get(f"{API_BASE}/search/artist", params={"q": nom, "limit": 10})
    if not data:
        return None

    results = data.get("data", [])
    if not results:
        return None

    nom_norm = _normalize(nom)

    # Pass 1: exact normalized match
    for artist in results:
        if _normalize(artist["name"]) == nom_norm:
            return {"id": artist["id"], "name": artist["name"]}

    # Pass 2: containment — our name in theirs or theirs in ours
    for artist in results:
        deezer_norm = _normalize(artist["name"])
        if nom_norm in deezer_norm or deezer_norm in nom_norm:
            return {"id": artist["id"], "name": artist["name"]}

    logger.info(
        "Deezer: no matching artist for '%s' (candidates: %s)",
        nom,
        [a["name"] for a in results[:3]],
    )
    return None


def get_artist_info(deezer_id: int) -> dict | None:
    """
    Fetch artist details from Deezer.
    Returns {"id": int, "name": str, "nb_fan": int, "nb_album": int} or None.
    """
    data = _get(f"{API_BASE}/artist/{deezer_id}")
    if not data:
        return None
    return {
        "id": data.get("id"),
        "name": data.get("name", ""),
        "nb_fan": data.get("nb_fan", 0),
        "nb_album": data.get("nb_album", 0),
    }


def get_album_titular_id(album_id: int) -> int | None:
    """Deezer album's titular artist id (``album.artist.id``), or ``None``
    when the album can't be resolved (network/API error, deleted album).

    Used by the ingest's album-alien guard to distinguish an artista's OWN
    album (titular ∈ our deezer_ids → ingest the whole album) from a foreign
    album they only guest on (ingest only the tracks they actually contribute
    to). The ``/artist/{id}/albums`` listing does NOT carry the titular, so
    this is one extra call per album — the caller resolves it once and reuses
    it for every track. ``None`` means "unresolved": the caller stays
    conservative (does not skip) so a transient failure never silently drops
    real tracks.
    """
    data = _get(f"{API_BASE}/album/{album_id}")
    if not data:
        return None
    return (data.get("artist") or {}).get("id")


def get_artist_albums(deezer_id: int, min_date: date | None = None) -> list[dict]:
    """
    Fetch albums for a Deezer artist, optionally filtered by release date.
    Returns list of dicts: {id, title, release_date, cover_xl, record_type}.
    """
    albums = []
    url = f"{API_BASE}/artist/{deezer_id}/albums"
    params = {"limit": 100}

    while url:
        data = _get(url, params=params)
        if not data:
            break

        for item in data.get("data", []):
            release_str = item.get("release_date", "")
            release_date = _parse_date(release_str)

            if min_date and release_date and release_date < min_date:
                continue

            record_type = item.get("record_type", "album")

            albums.append(
                {
                    "id": item["id"],
                    "title": item.get("title", ""),
                    "release_date": release_date,
                    "cover_xl": item.get("cover_xl", ""),
                    "record_type": record_type,
                }
            )

        next_url = data.get("next")
        if next_url:
            url = next_url
            params = None
        else:
            break

    return albums


def get_album_tracks(album_id: int) -> list[dict]:
    """
    Fetch tracks for a Deezer album.
    For each track, fetches the full track endpoint to get ISRC, preview,
    album_release_date (prefers album.release_date over track.release_date),
    and contributors.
    """
    data = _get(f"{API_BASE}/album/{album_id}/tracks")
    if not data:
        return []

    tracks = []
    for item in data.get("data", []):
        track_id = item["id"]

        # Fetch full track to get ISRC, contributors, preview, and album release date
        full = _get(f"{API_BASE}/track/{track_id}")
        isrc = full.get("isrc", "") if full else ""
        preview = full.get("preview", "") if full else ""
        # Use album.release_date (original), not track.release_date (may be re-release)
        album_release = (
            (full.get("album", {}).get("release_date") or full.get("release_date", ""))
            if full
            else ""
        )
        contributors = []
        if full:
            for c in full.get("contributors", []):
                contributors.append({"id": c.get("id"), "name": c.get("name", "")})

        artist = item.get("artist", {})
        tracks.append(
            {
                "id": track_id,
                "title": item.get("title", ""),
                "duration": item.get("duration", 0),
                "isrc": isrc,
                "artist_id": artist.get("id"),
                "artist_name": artist.get("name", ""),
                "preview": preview,
                "album_release_date": album_release,
                "contributors": contributors,
            }
        )

    return tracks


def _parse_date(date_str: str) -> date | None:
    """Parse YYYY-MM-DD date string."""
    if not date_str:
        return None
    try:
        parts = date_str.split("-")
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, TypeError):
        return None
    return None
