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
        if "quotaExceeded" in reasons or "dailyLimitExceeded" in reasons:
            raise QuotaExhausted(data["error"].get("message", "quota exceeded"))
        logger.warning(
            "YouTube %s failed: %s", endpoint, data["error"].get("message", "")[:200]
        )
        return {}
    return data


def _norm_channel_title(title: str) -> str:
    return title.strip().lower()


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
        if not title.lower().endswith("- topic"):
            continue
        if _norm_channel_title(title[: -len("- topic")]) == target:
            return item["snippet"].get("channelId") or None
    return None


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
