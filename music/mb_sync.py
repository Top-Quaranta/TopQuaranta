"""Map MusicBrainz data onto our Artista / Album / Canco rows.

Called from `obtenir_metadata_musicbrainz` (and ad-hoc from staff UI).
Never raises — on any failure we mark the artist's sync timestamp so
we don't hammer MB on the same error hourly. Returns a dict of
counters so callers can log.

Two entry points:
  * `resolve_mbid(artista)` — called when artista.musicbrainz_id is
    empty. Searches MB by name; if exactly one strong Catalan hit,
    writes it. Otherwise leaves it empty (staff must disambiguate).
  * `sync_from_mbid(artista)` — called when artista has an MBID.
    Pulls artist core + discography + relationships + work languages,
    reconciles against our existing Albums/Cançons.
"""

from __future__ import annotations

import datetime
import logging
from difflib import SequenceMatcher

from django.utils import timezone

from ingesta.clients import musicbrainz as mb

logger = logging.getLogger(__name__)

# PPCC-area MB names we consider a positive territori signal.
_PPCC_AREA_TOKENS = {
    "Catalonia",
    "Catalunya",
    "Barcelona",
    "Girona",
    "Lleida",
    "Tarragona",
    "Valencia",
    "València",
    "Valencian Community",
    "Comunidad Valenciana",
    "Balearic Islands",
    "Illes Balears",
    "Mallorca",
    "Menorca",
    "Ibiza",
    "Andorra",
    "Alghero",
    "Perpignan",
    "Northern Catalonia",
}

# MB URL relationship types → our Artista field.
_URL_REL_MAP = {
    "official homepage": "web_url",
    "bandcamp": "bandcamp_url",
    "spotify": "spotify_url",
    "youtube": "youtube_url",
    "youtube music": "youtube_url",
    "soundcloud": "soundcloud_url",
    "wikipedia": "viquipedia_url",
    "viasona": "viasona_url",
    "facebook": "facebook_url",
    "myspace": "myspace_url",
}

# Instagram / X don't have dedicated MB url-rel types — both are
# exposed as the generic "social network" relation, distinguished only
# by the URL host. We route them to the right field by inspecting
# the URL after the relation type filter passes.
_SOCIAL_NETWORK_REL_TYPES = {"social network", "social"}
_SOCIAL_HOST_MAP = {
    "instagram.com": "instagram_url",
    "www.instagram.com": "instagram_url",
    "twitter.com": "twitter_url",
    "www.twitter.com": "twitter_url",
    "x.com": "twitter_url",
    "www.x.com": "twitter_url",
    "mobile.twitter.com": "twitter_url",
    "tiktok.com": "tiktok_url",
    "www.tiktok.com": "tiktok_url",
}

# Confidence threshold for single-match auto-assignment. Lives in
# `music/constants.py` since 2026-04-25 (Sprint A) — re-exported here
# under the historical name to keep call sites stable.
from music.constants import MB_AUTO_MATCH_SCORE as AUTO_MATCH_SCORE  # noqa: E402, F401


def _looks_ppcc(area_name: str, disambiguation: str = "") -> bool:
    text = f"{area_name} {disambiguation}".lower()
    return any(tok.lower() in text for tok in _PPCC_AREA_TOKENS)


def _parse_date(raw: str) -> datetime.date | None:
    """MB uses partial dates: '2025', '2025-03', '2025-03-24'. Parse what we can."""
    if not raw:
        return None
    parts = raw.split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return datetime.date(year, month, day)
    except (ValueError, IndexError):
        return None


def _normalize_title(s: str) -> str:
    """Lowercase + strip parentheticals + fold whitespace for fuzzy match."""
    import re

    s = s.lower()
    s = re.sub(r"\s*[\(\[][^\)\]]+[\)\]]\s*", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def resolve_mbid(artista) -> str | None:
    """Search MB by name; return a single strong PPCC match or None.

    Strict rules to avoid false positives:
      * exact-name match (case-insensitive) AND score ≥ AUTO_MATCH_SCORE
      * only one candidate passes the above; ambiguous → None
      * prefer candidates with PPCC-area hint, but don't demand it
        (some groups lack area on MB even when they're from here).
    """
    name = artista.nom.strip()
    if not name:
        return None
    # Staff-controlled escape hatches: stop auto-matching entirely, or
    # skip previously-rejected MBIDs. Both survive re-runs of the cron.
    if getattr(artista, "mb_auto_match_disabled", False):
        return None
    blocked = set(getattr(artista, "mb_blocked_mbids", []) or [])
    try:
        candidates = mb.search_artist(name)
    except Exception:
        logger.exception("MB search failed for %s", name)
        return None

    want = name.lower()
    strong = []
    for c in candidates:
        if c.get("score", 0) < AUTO_MATCH_SCORE:
            continue
        if c.get("name", "").lower() != want:
            continue
        if c.get("id") in blocked:
            continue
        strong.append(c)

    if not strong:
        return None
    if len(strong) == 1:
        return strong[0]["id"]
    # Multiple exact-name matches → disambiguate by PPCC area if possible.
    ppcc_hits = [
        c
        for c in strong
        if _looks_ppcc(
            (c.get("area") or {}).get("name", ""),
            c.get("disambiguation", ""),
        )
    ]
    if len(ppcc_hits) == 1:
        return ppcc_hits[0]["id"]
    return None  # still ambiguous — let staff pick


def _field_for_relation(rel_type: str, url: str) -> str | None:
    """Return the Artista field name for a MB url-rel, or None to skip.

    Most rel types map 1:1 via `_URL_REL_MAP`. Instagram, X (Twitter)
    and TikTok all share the generic "social network" rel type on MB,
    so for that type we route by URL host via `_SOCIAL_HOST_MAP`.
    """
    field = _URL_REL_MAP.get(rel_type)
    if field:
        return field
    if rel_type in _SOCIAL_NETWORK_REL_TYPES:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
        return _SOCIAL_HOST_MAP.get(host)
    return None


def _apply_url_relations(artista, relations: list[dict]) -> int:
    """Fill missing social URL fields from MB's url-rels. Never overwrite."""
    filled = 0
    for rel in relations or []:
        if rel.get("target-type") != "url":
            continue
        rel_type = (rel.get("type") or "").lower()
        url = (rel.get("url") or {}).get("resource", "")
        if not url.startswith(("http://", "https://")):
            continue
        field = _field_for_relation(rel_type, url)
        if not field:
            continue
        if getattr(artista, field, None):
            continue  # already set, don't overwrite
        setattr(artista, field, url)
        filled += 1
    return filled


def sync_from_mbid(artista) -> dict:
    """Pull artist + discography from MB, reconcile with our data.

    Returns `{counters…}` for logging. Never raises.
    """
    from music.models import Album, Canco

    result = {
        "artist_found": False,
        "urls_filled": 0,
        "rgs": 0,
        "albums_matched": 0,
        "recordings": 0,
        "cancons_matched": 0,
        "isrcs": 0,
        "cat_work": 0,
    }
    if not artista.musicbrainz_id:
        return result

    data = mb.get_artist(artista.musicbrainz_id)
    if not data:
        artista.mb_last_sync = timezone.now()
        artista.save(update_fields=["mb_last_sync"])
        return result
    result["artist_found"] = True

    # Core fields.
    artista.mb_type = (data.get("type") or "")[:20]
    artista.mb_gender = (data.get("gender") or "")[:20]
    area = data.get("area") or {}
    artista.mb_area = (area.get("name") or "")[:120]
    artista.mb_area_hierarchy = _flatten_area(area)
    ls = data.get("life-span") or {}
    artista.mb_begin_date = _parse_date(ls.get("begin", "")) or None
    artista.mb_end_date = _parse_date(ls.get("end", "")) or None
    artista.mb_disambiguation = (data.get("disambiguation") or "")[:255]
    artista.mb_sort_name = (data.get("sort-name") or "")[:255]
    artista.mb_aliases = [
        a.get("name", "") for a in (data.get("aliases") or []) if a.get("name")
    ]
    artista.mb_tags = sorted(
        [t.get("name", "") for t in (data.get("tags") or []) if t.get("name")]
    )
    rating = (data.get("rating") or {}).get("value")
    artista.mb_rating = round(float(rating), 2) if rating else None

    result["urls_filled"] = _apply_url_relations(artista, data.get("relations") or [])

    # Discography — release-groups.
    try:
        rgs = mb.get_artist_release_groups(artista.musicbrainz_id)
    except Exception:
        logger.exception("MB release-groups failed for %s", artista.musicbrainz_id)
        rgs = []
    result["rgs"] = len(rgs)

    # Reset any stale MB-reconciliation fields on this artist's albums
    # and cançons before re-matching. Motivation: if staff corrected an
    # MBID after a wrong auto-resolve (e.g. Meteor valencià → Meteor
    # Medellín), the obsolete mb_release_group_id / mb_recording_id /
    # mb_work_id / mb_lyrics_language / mbrainz_confirmed stay behind
    # because sync_from_mbid only sets True on new matches. Reset
    # wholesale here so the new sync is authoritative.
    Album.objects.filter(artista=artista).update(
        mb_release_group_id="",
        mb_type_secondary="",
        mb_status="",
        mbrainz_confirmed=None,
    )
    Canco.objects.filter(artista=artista).update(
        mb_recording_id="",
        mb_work_id="",
        mb_lyrics_language="",
        mbrainz_confirmed=None,
    )

    # Index our albums by normalized title for matching.
    nostres_albums = {
        _normalize_title(a.nom): a for a in Album.objects.filter(artista=artista)
    }
    isrc_to_canco = {
        c.isrc: c for c in Canco.objects.filter(artista=artista).exclude(isrc="")
    }
    title_to_canco = {
        _normalize_title(c.nom): c for c in Canco.objects.filter(artista=artista)
    }

    discography_isrcs: set[str] = set()
    discography_titles: list[dict] = []

    for rg in rgs:
        rg_id = rg.get("id")
        rg_title = rg.get("title", "")
        rg_date = _parse_date(rg.get("first-release-date", ""))
        primary = rg.get("primary-type", "") or ""
        secondary = ",".join(rg.get("secondary-types", []) or [])

        nkey = _normalize_title(rg_title)
        alb = nostres_albums.get(nkey)
        if not alb:
            # Fuzzy — find the single best > 0.9.
            alb = _best_fuzzy(nkey, nostres_albums)
        if alb:
            alb.mb_release_group_id = rg_id
            alb.mb_type_secondary = secondary[:30]
            alb.mbrainz_confirmed = True
            alb.save(
                update_fields=[
                    "mb_release_group_id",
                    "mb_type_secondary",
                    "mbrainz_confirmed",
                ]
            )
            result["albums_matched"] += 1

        # Fetch recordings for discography cache + canço reconciliation.
        try:
            detail = mb.get_release_group_with_recordings(rg_id)
        except Exception:
            detail = None
        if not detail or not detail.get("_picked_release"):
            continue
        release = detail["_picked_release"]
        if alb and not alb.mb_status:
            alb.mb_status = (release.get("status") or "")[:30]
            alb.save(update_fields=["mb_status"])
        for medium in release.get("media", []) or []:
            for tr in medium.get("tracks", []) or []:
                rec = tr.get("recording") or {}
                result["recordings"] += 1
                title = rec.get("title", tr.get("title", ""))
                isrcs = rec.get("isrcs", []) or []
                for i in isrcs:
                    discography_isrcs.add(i.strip())
                discography_titles.append(
                    {
                        "title": title,
                        "rg": rg_title,
                        "date": rg_date.isoformat() if rg_date else None,
                    }
                )

                # Reconcile canço.
                match = None
                for i in isrcs:
                    if i in isrc_to_canco:
                        match = isrc_to_canco[i]
                        break
                if not match:
                    nt = _normalize_title(title)
                    match = title_to_canco.get(nt) or _best_fuzzy(nt, title_to_canco)
                if match:
                    match.mb_recording_id = rec.get("id", "")
                    match.mbrainz_confirmed = True
                    # Pull work language if present.
                    for wrel in rec.get("relations", []) or []:
                        if wrel.get("target-type") == "work":
                            w = wrel.get("work") or {}
                            if w.get("id"):
                                match.mb_work_id = w["id"]
                            lang = (w.get("languages") or [None])[0] or w.get(
                                "language"
                            )
                            if lang:
                                match.mb_lyrics_language = lang[:3]
                                if lang == "cat":
                                    result["cat_work"] += 1
                            break
                    match.save(
                        update_fields=[
                            "mb_recording_id",
                            "mbrainz_confirmed",
                            "mb_work_id",
                            "mb_lyrics_language",
                        ]
                    )
                    result["cancons_matched"] += 1

    # Cache the canonical discography for quick Canco-creation checks.
    artista.mb_discography_cache = {
        "isrcs": sorted(discography_isrcs),
        "titles": discography_titles[:500],  # cap to keep row size reasonable
    }
    result["isrcs"] = len(discography_isrcs)
    artista.mb_last_sync = timezone.now()
    artista.save()
    return result


def _best_fuzzy(target_key: str, pool: dict) -> object | None:
    """Pick the single best fuzzy match in pool[key→obj] if ratio ≥ 0.9."""
    best = None
    best_ratio = 0.9
    for k, v in pool.items():
        r = SequenceMatcher(None, target_key, k).ratio()
        if r > best_ratio:
            best_ratio = r
            best = v
    return best


def _flatten_area(area: dict) -> list[str]:
    """MB area is a single object; full hierarchy requires area-rels expansion.

    Best-effort: take the primary name only (MB's artist endpoint doesn't
    ship the parent chain without extra calls). Richer hierarchy is a
    future improvement.
    """
    name = (area or {}).get("name", "")
    return [name] if name else []
