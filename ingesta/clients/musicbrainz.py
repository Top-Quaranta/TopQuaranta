"""MusicBrainz API client.

Thin wrapper around MB's JSON web service. Obeys their 1 req/s rate
limit globally. Never raises on transport errors — returns None so
callers can mark the artist/release as "not found right now" and move
on.

Docs: https://musicbrainz.org/doc/MusicBrainz_API
Rate limit policy: a single IP may do 1 req/s sustained; we sleep
before every request. A descriptive User-Agent is MANDATORY; bans
are common when omitted.
"""

from __future__ import annotations

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://musicbrainz.org/ws/2"
USER_AGENT = "TopQuaranta/1.0 (miquelmatoses@gmail.com)"
RATE_LIMIT_SLEEP = 1.05  # seconds — MB enforces 1/s; small margin to be polite
MAX_RETRIES = 3

# One shared lock so the 1 req/s limit holds across threads/calls.
_rate_lock = threading.Lock()
_last_call_at: float = 0.0


def _pace() -> None:
    """Block until at least RATE_LIMIT_SLEEP seconds have passed since last call."""
    global _last_call_at
    with _rate_lock:
        now = time.time()
        gap = now - _last_call_at
        if gap < RATE_LIMIT_SLEEP:
            time.sleep(RATE_LIMIT_SLEEP - gap)
        _last_call_at = time.time()


def _get(path: str, params: dict | None = None) -> dict | None:
    """Fetch JSON from MB, respecting rate limits. None on unrecoverable failure."""
    params = dict(params or {})
    params.setdefault("fmt", "json")
    for attempt in range(MAX_RETRIES):
        _pace()
        try:
            r = requests.get(
                f"{API_BASE}{path}",
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=20,
            )
        except requests.RequestException as exc:
            logger.warning("MB transport error on %s: %s", path, exc)
            time.sleep(2**attempt)
            continue
        if r.status_code == 429:
            # Rate limited — back off harder.
            retry = int(r.headers.get("Retry-After", "5"))
            logger.warning("MB 429 on %s, sleeping %ds", path, retry)
            time.sleep(retry)
            continue
        if r.status_code == 503:
            time.sleep(2**attempt)
            continue
        if r.status_code == 404:
            return None
        if not r.ok:
            logger.warning("MB %s on %s", r.status_code, path)
            return None
        try:
            return r.json()
        except ValueError:
            return None
    return None


def search_artist(name: str) -> list[dict]:
    """Return top MB matches for a name query.

    MB's Lucene-flavoured search: quotes around multi-word names, escape
    Lucene-special chars. Shape returned: `[{id, name, score, area, country,
    life-span, disambiguation, type, gender}...]` (partial; what MB gives us).
    """
    query = _escape_lucene(name)
    data = _get("/artist", {"query": f'artist:"{query}"', "limit": 10}) or {}
    return data.get("artists", []) or []


def get_artist(mbid: str) -> dict | None:
    """Full artist entity with relations (for URLs), tags, aliases, area."""
    return _get(
        f"/artist/{mbid}",
        {
            "inc": "aliases+tags+ratings+url-rels+artist-rels+area-rels",
        },
    )


def get_artist_release_groups(mbid: str) -> list[dict]:
    """Every release-group by this artist.

    Paginates by offset/limit=100. Returns the full list of release-groups
    with their primary type, first-release-date, title, id, secondary types.
    """
    rgs: list[dict] = []
    offset = 0
    while True:
        data = _get(
            "/release-group",
            {"artist": mbid, "limit": 100, "offset": offset},
        )
        if not data:
            break
        chunk = data.get("release-groups", []) or []
        rgs.extend(chunk)
        total = data.get("release-group-count", 0)
        offset += len(chunk)
        if not chunk or offset >= total:
            break
    return rgs


def get_release_group_with_recordings(rg_mbid: str) -> dict | None:
    """Fetch a release-group's first release with its recordings + ISRCs + works.

    MB doesn't expose tracklists on release-groups directly — we pick the
    canonical release (status=Official preferred) and pull its media.
    Response includes recordings with `isrcs` list when editors filled them
    in, plus work relationships (language, iswc).
    """
    rg = _get(
        f"/release-group/{rg_mbid}",
        {"inc": "releases"},
    )
    if not rg or not rg.get("releases"):
        return rg
    releases = rg["releases"]
    # Prefer Official releases — bootlegs and promos often have incomplete data.
    official = [r for r in releases if r.get("status") == "Official"]
    picked = (official or releases)[0]
    detail = _get(
        f"/release/{picked['id']}",
        {"inc": "recordings+isrcs+work-rels+artist-credits"},
    )
    if detail:
        rg["_picked_release"] = detail
    return rg


def get_work(work_mbid: str) -> dict | None:
    """Work entity — gives us `language` of lyrics and `iswc`."""
    return _get(f"/work/{work_mbid}", {"inc": "aliases"})


def isrc_to_recordings(isrc: str) -> list[dict]:
    """Look up recordings by ISRC. Empty when MB has no data for it."""
    data = _get(f"/isrc/{isrc}", {"inc": "artist-credits"})
    if not data:
        return []
    return data.get("recordings", []) or []


# Lucene has a set of reserved characters that must be escaped in queries.
_LUCENE_SPECIAL = r'+-!(){}[]^"~*?:\/'


def _escape_lucene(s: str) -> str:
    out = []
    for ch in s:
        if ch in _LUCENE_SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)
