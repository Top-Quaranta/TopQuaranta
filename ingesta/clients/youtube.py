"""YouTube Data API v3 client — Topic channels, Art Tracks, statistics.

Why YouTube at all: Last.fm only sees what its users scrobble, and for
Valencian and Balearic music that sample is close to empty — a 2026-08
recon found 116 of 400 eligible VAL tracks with no signal whatsoever.
YouTube auto-creates a **"<artist> - Topic" channel** for anything a
distributor delivers, holding "Art Tracks" (cover art + audio). It
exists whether or not anybody has ever scrobbled the act: 30 of 30
sampled VAL/BAL artists had one.

Quota is the whole design constraint. 10.000 units/day, free, with no
paid tier — an extension needs a manual Google audit. Costs:

    search.list        100 units   ← discovery, the expensive half
    channels.list        1 unit
    playlistItems.list   1 unit    (50 videos)
    videos.list          1 unit    (50 videos, with statistics)

So *finding* an artist costs 100 units and *polling the whole
catalogue every day* costs ~60. Discovery is rationed by
`descobrir_youtube`; the daily poll is effectively free.

**The Topic suffix is not optional.** Searching "Auxili - Topic"
returns the band's own human channel ("AUXILI") first — full of
videoclips titled "AUXILI - TARRINETES AL SOL ft DJ Trapella", which
match nothing. Requiring the literal "- Topic" suffix took the sampled
match rate from 63% to 76%. `find_topic_channel` enforces it.

# Spec: docs/architecture/pipeline.md
"""

from __future__ import annotations

import logging
import time

import requests
from django.conf import settings

from music.models import normalitza_nom_homonim

logger = logging.getLogger(__name__)

API_URL = "https://www.googleapis.com/youtube/v3/"
RATE_LIMIT_SLEEP = 0.1
TIMEOUT = 20

# Quota cost per endpoint, per the published table. Callers use these to
# budget a run rather than hardcoding numbers at each call site.
COST_SEARCH = 100
COST_LIST = 1

# Daily quota of a Google Cloud project. Not configurable by us.
DAILY_QUOTA = 10_000


class QuotaExhausted(RuntimeError):
    """Google returned quotaExceeded. Nothing to do but stop for today."""


def _get(endpoint: str, **params) -> dict:
    params["key"] = settings.YOUTUBE_API_KEY
    time.sleep(RATE_LIMIT_SLEEP)
    r = requests.get(API_URL + endpoint, params=params, timeout=TIMEOUT)
    data = r.json()
    if "error" in data:
        reasons = {e.get("reason", "") for e in data["error"].get("errors", []) or [{}]}
        message = data["error"].get("message", "")
        # Google's per-metric limits ("Search Queries per day") come back
        # with reasons OUTSIDE the two canonical ones. On 2026-08-12/13
        # that mismatch turned quota death into "empty result", and
        # discovery stamped 27 artists as "has no channel" — a silent
        # lie that parked them out of the queue. Match the message too.
        if (
            "quotaExceeded" in reasons
            or "dailyLimitExceeded" in reasons
            or "rateLimitExceeded" in reasons
            or "quota exceeded" in message.lower()
        ):
            raise QuotaExhausted(message or "quota exceeded")
        logger.warning(
            "YouTube %s failed: %s", endpoint, data["error"].get("message", "")[:200]
        )
        return {}
    return data


# YouTube localises the auto-generated channel suffix: a Catalan browser
# shows "Malifeta - Tema", an English one "Malifeta - Topic". Our server
# currently gets English, but that is an accident of the API's default
# locale, not a contract — and if it ever changes, requiring the English
# word would make discovery return nothing at all, silently. Cheap
# insurance.
_TOPIC_SUFIXOS = (
    "topic",
    "tema",
    "thema",
    "sujet",
    "tópico",
    "tópicos",
    "argomento",
    "onderwerp",
)


def topic_suffix_name(title: str) -> str | None:
    """The artist name when `title` is an auto-generated channel, else None.

    "Malifeta - Topic" → "Malifeta"; "Malifeta - Tema" → "Malifeta";
    "MALIFETA" → None (that is the band's own channel).
    """
    net = (title or "").strip()
    for sufix in _TOPIC_SUFIXOS:
        cua = f"- {sufix}"
        if net.lower().endswith(cua):
            return net[: -len(cua)].strip()
    return None


def _norm_channel_title(title: str) -> str:
    """Fold a channel title down to a comparable key.

    Lowercasing alone is not enough, and the two misses it produced are
    both real: our "Bèrnia" never matched the channel literally called
    `bernia - Topic`, and "Clàudia Xiva" never matched `Clàudia Xiva -
    Topic` because one side was NFC and the other NFD. Reuses the
    project's existing homonym key (NFKD, drop diacritics, drop
    everything non-alphanumeric) rather than growing a second one.

    Loosening this does NOT widen the exploit surface: the candidate
    must still carry the literal "- Topic" suffix, which is what keeps
    the padel channels and the events companies out.
    """
    return normalitza_nom_homonim(title)


def find_topic_channel(artist_name: str) -> str | None:
    """The `UC…` id of the artist's auto-generated Topic channel.

    Costs `COST_SEARCH`. Returns None when no candidate carries the
    literal "- Topic" suffix with a matching name — deliberately strict,
    since the alternative (falling back to whatever ranked first) picks
    the band's human channel and poisons every downstream match.
    """
    data = _get(
        "search",
        part="snippet",
        q=f"{artist_name} - Topic",
        type="channel",
        maxResults=5,
    )
    target = _norm_channel_title(artist_name)
    for item in data.get("items", []):
        title = (item.get("snippet", {}).get("title") or "").strip()
        nom = topic_suffix_name(title)
        if nom is None:
            continue
        if _norm_channel_title(nom) == target:
            return item["snippet"].get("channelId") or None
    return None


def channel_info(*, channel_id: str = "", handle: str = "") -> dict | None:
    """`{"id", "title"}` for a channel, by id or by handle. Costs `COST_LIST`.

    One unit, not the hundred a `search.list` would cost, which is what
    makes accepting handles viable at all: YouTube stopped showing the
    `UC…` id anywhere in its UI, so the handle is what a human can copy
    out of the address bar. The title comes back too because the caller
    needs it to tell an artist's own channel from the auto-generated one.
    """
    if handle:
        data = _get("channels", part="snippet", forHandle=handle.lstrip("@"))
    elif channel_id:
        data = _get("channels", part="snippet", id=channel_id)
    else:
        return None
    items = data.get("items") or []
    if not items:
        return None
    return {
        "id": items[0].get("id") or "",
        "title": (items[0].get("snippet", {}).get("title") or "").strip(),
    }


def resolve_handle(handle: str) -> str | None:
    """`@malifeta` → `UCZ_RdKPMxRUQv4j3XX8Hsjg`. Costs `COST_LIST`."""
    info = channel_info(handle=handle)
    return info["id"] if info else None


def uploads_playlist(channel_id: str) -> str | None:
    """The channel's uploads playlist id. Costs `COST_LIST`."""
    data = _get("channels", part="contentDetails", id=channel_id)
    items = data.get("items") or []
    if not items:
        return None
    return items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")


def playlist_videos(playlist_id: str, *, max_pages: int = 6) -> list[dict]:
    """Every Art Track on the playlist as `{video_id, title}`.

    Costs `COST_LIST` per page of 50. `max_pages` bounds a runaway back
    catalogue (300 videos covers every artist in the sample; Joan
    Bibiloni, the deepest, has 290).
    """
    out: list[dict] = []
    token = None
    for _ in range(max_pages):
        params = {"part": "snippet", "playlistId": playlist_id, "maxResults": 50}
        if token:
            params["pageToken"] = token
        data = _get("playlistItems", **params)
        for item in data.get("items", []):
            snip = item.get("snippet", {})
            vid = (snip.get("resourceId") or {}).get("videoId")
            if vid:
                out.append({"video_id": vid, "title": snip.get("title") or ""})
        token = data.get("nextPageToken")
        if not token:
            break
    return out


def video_stats(video_ids: list[str]) -> dict[str, dict]:
    """`{video_id: {"views": int, "likes": int|None}}` for up to 50 ids.

    One quota unit per call regardless of how many ids, which is what
    makes a daily poll of the whole catalogue affordable. `likeCount` is
    absent when the uploader hides it — views are what we actually use.
    """
    if not video_ids:
        return {}
    data = _get("videos", part="statistics", id=",".join(video_ids[:50]))
    out: dict[str, dict] = {}
    for item in data.get("items", []):
        stats = item.get("statistics", {})
        views = stats.get("viewCount")
        likes = stats.get("likeCount")
        out[item["id"]] = {
            "views": int(views) if views is not None else None,
            "likes": int(likes) if likes is not None else None,
        }
    return out
