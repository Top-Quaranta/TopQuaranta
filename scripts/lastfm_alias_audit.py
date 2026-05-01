"""Detect approved artists whose Last.fm signal is fragmented across
multiple pages (spelling variants of the canonical name).

The hard part is distinguishing TRUE variants of the same artist
(e.g. 'Delên' / 'Delen' / 'dêlen' — accent / case differences from
inconsistent scrobbling) from HOMONYMS (e.g. 'Abril.' the PPCC group
vs 'Abril' a different artist altogether). Name similarity alone is
not enough; we need a content signal.

Strategy per artist:
  1. Take the canonical `lastfm_nom`.
  2. `artist.search?artist=<lastfm_nom>` to find candidate variants.
  3. Filter to hits whose normalised name (lowercase + strip
     diacritics + strip punctuation) matches the canonical's, AND
     whose URL is different (not the same Last.fm page).
  4. For each candidate variant, fetch `artist.getTopTracks` and
     compare with the canonical's top tracks. If the top-5 track
     names overlap by ≥50 %, treat as the same artist (true
     variant). If overlap is <50 % they're homonyms and we skip.
  5. Only after the top-tracks check, count playcounts and report.

Output: tab-separated lines per artist with split signal, sorted by
fragmentation severity. Run with rate limiting (~5 req/s).

Usage:
    DJANGO_SETTINGS_MODULE=topquaranta.settings.web_server \
        .venv/bin/python scripts/lastfm_alias_audit.py [--limit N]
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata

import django

# Make sure the project root is on sys.path so `topquaranta.settings.*`
# resolves when this script is run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "topquaranta.settings.web_server")
django.setup()

from ingesta.clients import lastfm  # noqa: E402
from music.models import Artista  # noqa: E402


def _norm(name: str) -> str:
    """Lowercase + strip diacritics + collapse whitespace + strip
    punctuation. The point: make 'Delên', 'Delen', 'dêlen' all equal."""
    s = unicodedata.normalize("NFKD", name).lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    keep = []
    for c in s:
        if c.isalnum() or c.isspace():
            keep.append(c)
    s = "".join(keep)
    return " ".join(s.split())


def _search_artist(name: str, limit: int = 8) -> list[dict]:
    data = lastfm._artist_api_call("artist.search", artist=name, limit=limit)
    if not data:
        return []
    res = (data.get("results") or {}).get("artistmatches") or {}
    arts = res.get("artist") or []
    if isinstance(arts, dict):
        arts = [arts]
    return arts


def _lastfm_call_no_autocorrect(method: str, **extra) -> dict | None:
    """Generic Last.fm call with `autocorrect=0` — returns the
    LITERAL page for the given name. Critical: the canonical
    `_artist_api_call` uses `autocorrect=1`, which silently
    redirects 'Delen' → 'Delên' and would make variant detection
    impossible (same response for both)."""
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


def _get_artist_info_no_autocorrect(name: str) -> dict | None:
    data = _lastfm_call_no_autocorrect("artist.getInfo", artist=name)
    return (data or {}).get("artist") or None


def _top_tracks_set(name: str, autocorrect: int = 0, n: int = 10) -> set[str]:
    """Return the top-N track names for a Last.fm artist page,
    normalised for comparison."""
    fn = lastfm._artist_api_call if autocorrect else _lastfm_call_no_autocorrect
    data = fn("artist.getTopTracks", artist=name, limit=n)
    if not data:
        return set()
    tracks = (data.get("toptracks") or {}).get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    return {_norm(t.get("name", "")) for t in tracks if t.get("name")}


def _shares_top_tracks(
    canon_top: set[str], variant_name: str, threshold: float
) -> bool:
    """True if the variant's top tracks overlap ≥ threshold with the
    canonical's. The point: 'Delên' and 'Delen' will share most top
    tracks; 'Abril.' and 'Abril' (homonyms) won't."""
    if not canon_top:
        return False
    variant_top = _top_tracks_set(variant_name)
    if not variant_top:
        return False
    overlap = canon_top & variant_top
    # Use the smaller set as denominator: if either page has only 3
    # tracks total, we can't expect 5 overlaps. The variant page is
    # often the smaller one (fewer scrobbles).
    denom = min(len(canon_top), len(variant_top))
    return (len(overlap) / denom) >= threshold


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--min-fragmentation",
        type=float,
        default=0.01,
        help="Variant playcount must be ≥ X * canonical playcount to count.",
    )
    parser.add_argument(
        "--top-tracks-overlap",
        type=float,
        default=0.5,
        help=(
            "Minimum top-tracks overlap to confirm two pages are the same "
            "artist (vs homonyms). 0.5 = at least half of the smaller "
            "page's top tracks must appear on the other."
        ),
    )
    args = parser.parse_args()

    qs = Artista.objects.filter(aprovat=True).exclude(lastfm_nom="")
    if args.limit:
        qs = qs[: args.limit]
    total = qs.count()
    print(f"# Auditing {total} approved artists (1 req/s + retries)…", file=sys.stderr)

    findings: list[dict] = []
    for i, art in enumerate(qs.iterator(), 1):
        canon = art.lastfm_nom
        canon_norm = _norm(canon)
        if not canon_norm:
            continue
        try:
            hits = _search_artist(canon)
        except Exception as exc:
            print(f"  [skip pk={art.pk}] {exc}", file=sys.stderr)
            continue

        # Resolve canonical to its URL (autocorrect ON — that's how
        # we'd query it normally). Then for each variant from search,
        # query LITERALLY (autocorrect OFF) and only keep those whose
        # URL differs from the canonical. Same URL → same Last.fm page.
        canon_info = lastfm.get_artist_info(canon)
        if not canon_info:
            continue
        canon_url = canon_info.get("url", "").lower()
        canon_pc = int((canon_info.get("stats") or {}).get("playcount", 0))
        if not canon_pc or not canon_url:
            continue

        variants = []
        seen_urls = {canon_url}
        for h in hits:
            other_name = h.get("name", "")
            if not other_name:
                continue
            if _norm(other_name) != canon_norm:
                continue
            if other_name.strip() == canon.strip():
                continue
            other_url = (h.get("url") or "").lower()
            if not other_url or other_url in seen_urls:
                continue
            seen_urls.add(other_url)
            variants.append((other_name, other_url))

        if not variants:
            continue

        # Fetch canonical top-tracks ONCE per artist — used to
        # validate every variant via overlap.
        canon_top = _top_tracks_set(canon, autocorrect=1)
        if not canon_top:
            # Canonical with no top-tracks data is too low-signal to
            # judge variants against. Skip rather than guess.
            continue

        rows = []
        for v_name, v_url in variants:
            v_info = _get_artist_info_no_autocorrect(v_name)
            if not v_info:
                continue
            if (v_info.get("url") or "").lower() != v_url:
                continue
            v_pc = int((v_info.get("stats") or {}).get("playcount", 0))
            if not v_pc or v_pc < canon_pc * args.min_fragmentation:
                continue
            # The decisive check: top-tracks overlap. Without this we
            # confuse spelling variants (Delên/Delen) with homonyms
            # (Abril./Abril, different artists altogether).
            if not _shares_top_tracks(canon_top, v_name, args.top_tracks_overlap):
                continue
            rows.append((v_name, v_pc, v_url))

        if rows:
            total_variant = sum(v_pc for _, v_pc, _ in rows)
            ratio = total_variant / max(canon_pc, 1)
            findings.append(
                {
                    "pk": art.pk,
                    "nom": art.nom,
                    "canon": canon,
                    "canon_pc": canon_pc,
                    "variants": rows,
                    "ratio": ratio,
                }
            )
            print(
                f"  ({i}/{total}) {canon!r}: canon={canon_pc:,} "
                f"variants={total_variant:,} ratio={ratio:.2f} "
                f"({len(rows)} variants)",
                file=sys.stderr,
            )

    findings.sort(key=lambda f: -f["ratio"])
    print()
    print("=" * 80)
    print(f"# Total artistes amb fragmentació detectada: {len(findings)} / {total}")
    print(
        f"# Llindar: variant playcount ≥ {args.min_fragmentation*100:.1f}% del canònic"
    )
    print()
    print("ratio\tcanon_pc\tvariant_pc_total\tnom_canonic\tpk\tvariants")
    for f in findings:
        var_total = sum(v_pc for _, v_pc, _ in f["variants"])
        var_str = "; ".join(f"{v} ({v_pc:,})" for v, v_pc, _ in f["variants"])
        print(
            f"{f['ratio']:.2f}\t{f['canon_pc']}\t{var_total}\t"
            f"{f['canon']!r}\t{f['pk']}\t{var_str}"
        )


if __name__ == "__main__":
    main()
