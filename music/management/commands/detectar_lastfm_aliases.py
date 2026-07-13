"""Detect Last.fm pages that fragment an artist's signal across
multiple spelling variants, and queue them as `ArtistaLastfmAlias`
candidates for staff review.

This is the production-grade port of the one-shot script at
`scripts/lastfm_alias_audit.py` — same algorithm, but writes
candidates into the DB instead of stdout, and skips artists that
already have rejected/confirmed aliases at the same name.

Algorithm per approved artist:

  1. `artist.search?artist=<lastfm_nom>` — find candidate variants.
  2. Filter to hits whose normalised name (lowercase + strip
     diacritics + strip punctuation) matches the canonical's, AND
     whose Last.fm URL is different (not the same page).
  3. For each candidate, compute top-5 track overlap between the
     canonical and the variant (`artist.getTopTracks` on each, with
     `autocorrect=0` on the variant to get the literal page). Skip
     if overlap < `--top-tracks-overlap` (default 0.5) — too low
     and it's likely a homonym.
  4. Skip if the variant playcount is < `--min-fragmentation` of
     the canonical (default 5%) — not enough lost signal to bother.
  5. Insert as `ArtistaLastfmAlias(confirmat=False, rebutjat=False)`
     so it appears in the staff review queue.

Re-runnable: existing rows for the same (artista, nom) are skipped.
Staff confirms or rejects each candidate at /staff/artistes/<pk>;
once confirmed, `obtenir_senyal` sums the variant's playcount into
the artist's signal.

Usage:
    .venv/bin/python manage.py detectar_lastfm_aliases [--apply]
                                                       [--limit N]
                                                       [--artist-pk PK]
"""

from __future__ import annotations

import unicodedata
from typing import Optional

from django.core.management.base import BaseCommand

from ingesta.clients import lastfm
from music.models import Artista, ArtistaLastfmAlias


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in s)
    return " ".join(s.split())


def _normalize_lastfm_url(u: str) -> str:
    """Compare-friendly form of a Last.fm artist URL.

    Critical for variant detection — `autocorrect=0` on `getInfo`
    DOES NOT prevent Last.fm from case-folding the artist name
    internally. Searching 'ADRIÀ PUNTÍ' returns a hit with URL
    `…/music/ADRI%C3%80+PUNT%C3%8D` (different bytes), but a
    follow-up `getInfo?artist=ADRIÀ+PUNTÍ&autocorrect=0` returns
    URL `…/music/+noredirect/Adri%C3%A0+Punt%C3%AD` — i.e. the
    canonical page with case folded. Same playcount, same top
    tracks. The 'variant' isn't a real one.

    Strip the `+noredirect/` wrapper, lowercase, and compare paths
    only (not host) so two pages that resolve to the same canonical
    look identical. Caught 2026-05-01 with Adrià Puntí (75 candidates
    inserted; many were case-only false positives).
    """
    if not u:
        return ""
    from urllib.parse import urlparse

    path = urlparse(u).path
    # +noredirect/ wrapper appears only on autocorrect=0 responses.
    path = path.replace("/+noredirect/", "/")
    return path.lower()


def _search_artist(name: str, limit: int = 8) -> list[dict]:
    data = lastfm._artist_api_call("artist.search", artist=name, limit=limit)
    if not data:
        return []
    res = (data.get("results") or {}).get("artistmatches") or {}
    arts = res.get("artist") or []
    if isinstance(arts, dict):
        arts = [arts]
    return arts


def _lastfm_call_no_autocorrect(method: str, **extra) -> Optional[dict]:
    """Generic Last.fm call with `autocorrect=0`. Distinct from
    `lastfm._artist_api_call` (autocorrect=1) — needed so the
    detector sees the literal variant page, not the canonical."""
    import requests
    from django.conf import settings

    params = {
        "method": method,
        "api_key": settings.LASTFM_API_KEY,
        "format": "json",
        "autocorrect": 0,
        **extra,
    }
    if "artist" in params:
        params["artist"] = unicodedata.normalize("NFC", params["artist"])
    try:
        r = requests.get(
            "https://ws.audioscrobbler.com/2.0/", params=params, timeout=10
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return None
        return data
    except Exception:
        return None


def _top_tracks_set(name: str, autocorrect: int = 0, n: int = 10) -> set[str]:
    fn = lastfm._artist_api_call if autocorrect else _lastfm_call_no_autocorrect
    data = fn("artist.getTopTracks", artist=name, limit=n)
    if not data:
        return set()
    tracks = (data.get("toptracks") or {}).get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    return {_norm(t.get("name", "")) for t in tracks if t.get("name")}


def _top_tracks_overlap_score(
    canon_top: set[str], variant_name: str
) -> tuple[float, set[str]]:
    """Return (overlap_ratio, variant_tracks) so callers can store the
    score on the candidate row for staff context."""
    if not canon_top:
        return 0.0, set()
    variant_top = _top_tracks_set(variant_name)
    if not variant_top:
        return 0.0, set()
    overlap = canon_top & variant_top
    denom = min(len(canon_top), len(variant_top))
    return (len(overlap) / denom), variant_top


class Command(BaseCommand):
    help = (
        "Detect Last.fm pages that fragment an artist's signal across "
        "spelling variants. Inserts candidates as ArtistaLastfmAlias rows "
        "for staff review at /staff/artistes/<pk>."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--artist-pk", type=int, default=None)
        parser.add_argument(
            "--min-fragmentation",
            type=float,
            default=0.05,
            help="Variant playcount must be ≥ X * canonical to qualify.",
        )
        parser.add_argument(
            "--top-tracks-overlap",
            type=float,
            default=0.5,
            help=(
                "Minimum top-tracks overlap to confirm two pages are "
                "the same artist (vs homonyms)."
            ),
        )

    def handle(self, *args, **opts):
        apply_changes = opts["apply"]
        artist_pk = opts["artist_pk"]
        min_frag = opts["min_fragmentation"]
        overlap_th = opts["top_tracks_overlap"]

        qs = Artista.objects.public().exclude(lastfm_nom="")
        if artist_pk:
            qs = qs.filter(pk=artist_pk)
        if opts["limit"]:
            qs = qs[: opts["limit"]]
        total = qs.count()
        self.stdout.write(f"Auditing {total} approved artists…")

        # Collect existing aliases (any state) so we don't re-propose.
        existing = {
            (a.artista_id, a.nom)
            for a in ArtistaLastfmAlias.objects.all().only("artista_id", "nom")
        }

        proposed = 0
        already_known = 0
        for i, art in enumerate(qs.iterator(), 1):
            canon = art.lastfm_nom
            if not canon:
                continue
            canon_norm = _norm(canon)
            try:
                hits = _search_artist(canon)
            except Exception as exc:
                self.stderr.write(f"  [skip pk={art.pk}] {exc}")
                continue
            canon_info = lastfm.get_artist_info(canon)
            if not canon_info:
                continue
            canon_url = (canon_info.get("url") or "").lower()
            canon_pc = int((canon_info.get("stats") or {}).get("playcount", 0))
            if not canon_pc or not canon_url:
                continue

            # Build the variant list (URL-deduped, name-distinct).
            variants = []
            seen_urls = {canon_url}
            for h in hits:
                other_name = (h.get("name") or "").strip()
                if not other_name:
                    continue
                if _norm(other_name) != canon_norm:
                    continue
                if other_name == canon.strip():
                    continue
                other_url = (h.get("url") or "").lower()
                if not other_url or other_url in seen_urls:
                    continue
                seen_urls.add(other_url)
                variants.append((other_name, other_url))
            if not variants:
                continue

            canon_top = _top_tracks_set(canon, autocorrect=1)
            if not canon_top:
                continue

            for v_name, _v_url in variants:
                if (art.pk, v_name) in existing:
                    already_known += 1
                    continue

                v_data = _lastfm_call_no_autocorrect("artist.getInfo", artist=v_name)
                v_info = (v_data or {}).get("artist") or {}
                if not v_info:
                    continue
                # Critical filter: Last.fm sometimes returns the
                # canonical page even with autocorrect=0 (case-only
                # variants like 'ADRIÀ PUNTÍ'). Compare normalized
                # URLs — if they match, the 'variant' is the same
                # page in disguise and would double-count if summed.
                if _normalize_lastfm_url(
                    v_info.get("url", "")
                ) == _normalize_lastfm_url(canon_info.get("url", "")):
                    continue
                v_pc = int((v_info.get("stats") or {}).get("playcount", 0))
                if not v_pc or v_pc < canon_pc * min_frag:
                    continue

                overlap, _ = _top_tracks_overlap_score(canon_top, v_name)
                if overlap < overlap_th:
                    continue

                self.stdout.write(
                    f"  [{i}/{total}] {art.nom!r:30s} candidate "
                    f"{v_name!r} pc_canon={canon_pc:,} pc_var={v_pc:,} "
                    f"overlap={overlap:.2f}"
                )
                if apply_changes:
                    ArtistaLastfmAlias.objects.create(
                        artista=art,
                        nom=v_name,
                        playcount_canonical=canon_pc,
                        playcount_variant=v_pc,
                        top_tracks_overlap=round(overlap, 4),
                    )
                proposed += 1

        verb = "Inserted" if apply_changes else "Would insert"
        self.stdout.write("")
        self.stdout.write(f"{verb}: {proposed} candidate aliases")
        self.stdout.write(f"Already known (skipped): {already_known}")
        if not apply_changes and proposed:
            self.stdout.write("Re-run with --apply to commit.")
