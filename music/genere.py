"""Canonical genre mapping for the `/genere/<slug>` SEO surface.

Source data: `Artista.lastfm_tags` (free-text, community-voted from
Last.fm) and `Artista.mb_tags` (same, from MusicBrainz). Both are
JSONField lists of `{name, count, url}` dicts.

Output: a single `Artista.genere_canonical` value from the 16-entry
choice list (see `Artista.GENERE_CANONICAL_CHOICES`).

Algorithm:
  1. Read all tag names from both sources, lower-cased + stripped.
  2. For each tag, look it up in `TAG_TO_CANONICAL` (priority,
     canonical) — explicit mapping wins over fuzzy substring fall-
     back.
  3. Aggregate per-canonical: sum (priority × occurrences).
  4. Pick the canonical with highest aggregate score; on a tie,
     break by most-specific (highest priority among the
     contributing tags).
  5. If nothing matches: leave `genere_canonical=""` (no /genere/
     page exposes the artiste).

Priority semantics:
  9 — very specific subgenre that tells us the parent canonical
      unambiguously (e.g. "death metal" → metal).
  5 — the canonical's exact tag (e.g. "punk" → punk).
  3 — a mid-specificity variant (e.g. "alternative rock" → rock).
  1 — a fallback that only wins if nothing else matches
      (e.g. "alternative" → indie; "indie" alone is too generic
      to outrank a specific genre).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

# (priority, canonical). Order doesn't matter; priority does.
# Tag names are lower-cased before lookup.
TAG_TO_CANONICAL: dict[str, tuple[int, str]] = {
    # ── metal (priority 9 for subgenres, 5 for the umbrella) ───
    "metal": (5, "metal"),
    "death metal": (9, "metal"),
    "black metal": (9, "metal"),
    "doom metal": (9, "metal"),
    "thrash metal": (9, "metal"),
    "heavy metal": (9, "metal"),
    "metalcore": (9, "metal"),
    "deathcore": (9, "metal"),
    "black metal/punk": (8, "metal"),
    "depressive black metal": (9, "metal"),
    "djent": (9, "metal"),
    "power metal": (9, "metal"),
    # ── hardcore ────────────────────────────────────────────────
    "hardcore": (5, "hardcore"),
    "hardcore punk": (9, "hardcore"),
    "post-hardcore": (9, "hardcore"),
    "melodic hardcore": (9, "hardcore"),
    # ── punk ────────────────────────────────────────────────────
    "punk": (5, "punk"),
    "punk rock": (8, "punk"),
    "pop punk": (8, "punk"),
    "post-punk": (8, "punk"),
    "skate punk": (8, "punk"),
    "oi": (8, "punk"),
    "anarcho-punk": (8, "punk"),
    "street punk": (8, "punk"),
    # ── ska / reggae ────────────────────────────────────────────
    "ska": (5, "ska"),
    "ska punk": (8, "ska"),
    "rocksteady": (8, "ska"),
    "two tone": (8, "ska"),
    "2 tone": (8, "ska"),
    "ska català": (8, "ska"),
    "reggae": (5, "reggae"),
    "dub": (8, "reggae"),
    "dancehall": (8, "reggae"),
    "roots reggae": (8, "reggae"),
    "ragga": (8, "reggae"),
    # ── electrònica ─────────────────────────────────────────────
    "electronic": (5, "electronica"),
    "electronica": (5, "electronica"),
    "electrònica": (5, "electronica"),
    "techno": (8, "electronica"),
    "house": (8, "electronica"),
    "ambient": (5, "electronica"),
    "drum and bass": (8, "electronica"),
    "drum n bass": (8, "electronica"),
    "dnb": (8, "electronica"),
    "dubstep": (8, "electronica"),
    "edm": (5, "electronica"),
    "idm": (8, "electronica"),
    "synthpop": (8, "electronica"),
    "synth-pop": (8, "electronica"),
    "synthwave": (8, "electronica"),
    "trance": (8, "electronica"),
    "electro": (5, "electronica"),
    "electroclash": (8, "electronica"),
    "downtempo": (5, "electronica"),
    "breakbeat": (8, "electronica"),
    # ── hip-hop / urbà ──────────────────────────────────────────
    "hip-hop": (5, "hip-hop"),
    "hip hop": (5, "hip-hop"),
    "hiphop": (5, "hip-hop"),
    "rap": (5, "hip-hop"),
    "jazz rap": (8, "hip-hop"),
    "boom bap": (8, "hip-hop"),
    "conscious hip hop": (8, "hip-hop"),
    "trap": (5, "urba"),
    "drill": (5, "urba"),
    "reggaeton": (5, "urba"),
    "reggaetón": (5, "urba"),
    "dembow": (5, "urba"),
    "urban": (3, "urba"),
    "urbà": (5, "urba"),
    "afrobeats": (5, "urba"),
    # ── jazz ────────────────────────────────────────────────────
    "jazz": (5, "jazz"),
    "bebop": (8, "jazz"),
    "bossa nova": (8, "jazz"),
    "bossanova": (8, "jazz"),
    "swing": (8, "jazz"),
    "cool jazz": (8, "jazz"),
    "fusion": (5, "jazz"),
    "neo-soul": (5, "jazz"),
    "smooth jazz": (8, "jazz"),
    "free jazz": (8, "jazz"),
    "flamenco jazz": (8, "jazz"),
    # ── folk ────────────────────────────────────────────────────
    "folk": (5, "folk"),
    "folk rock": (3, "folk"),
    "folk-rock": (3, "folk"),
    "celtic": (8, "folk"),
    "americana": (8, "folk"),
    "bluegrass": (8, "folk"),
    "country": (5, "folk"),
    "alt-country": (5, "folk"),
    "world": (3, "folk"),
    "world music": (3, "folk"),
    "balkan": (5, "folk"),
    "ladino": (5, "folk"),
    "flamenco": (5, "folk"),
    # ── cantautor ───────────────────────────────────────────────
    "cantautor": (5, "cantautor"),
    "cantautora": (5, "cantautor"),
    "singer-songwriter": (5, "cantautor"),
    "singer/songwriter": (5, "cantautor"),
    "acoustic": (3, "cantautor"),
    "lo-fi": (3, "cantautor"),
    # ── pop ─────────────────────────────────────────────────────
    "pop": (5, "pop"),
    "indie pop": (8, "pop"),
    "synth pop": (8, "electronica"),  # synth wins over pop here
    "dream pop": (8, "pop"),
    "j-pop": (8, "pop"),
    "k-pop": (8, "pop"),
    "art pop": (8, "pop"),
    "pop català": (8, "pop"),
    # ── rock ────────────────────────────────────────────────────
    "rock": (5, "rock"),
    "indie rock": (3, "rock"),
    "pop rock": (3, "rock"),
    "alternative rock": (3, "rock"),
    "alt rock": (3, "rock"),
    "art rock": (3, "rock"),
    "glam rock": (3, "rock"),
    "garage rock": (3, "rock"),
    "progressive rock": (3, "rock"),
    "prog rock": (3, "rock"),
    "psychedelic rock": (3, "rock"),
    "rock and roll": (3, "rock"),
    "rock català": (3, "rock"),
    "rock'n'roll": (3, "rock"),
    "stoner rock": (3, "rock"),
    "soft rock": (3, "rock"),
    "blues rock": (3, "rock"),
    "blues": (5, "rock"),  # strictly its own genre but we have 0 — fold
    # ── experimental ────────────────────────────────────────────
    "experimental": (5, "experimental"),
    "avant-garde": (8, "experimental"),
    "avantgarde": (8, "experimental"),
    "noise": (5, "experimental"),
    "drone": (8, "experimental"),
    "post-rock": (5, "experimental"),
    "post rock": (5, "experimental"),
    # ── infantil ────────────────────────────────────────────────
    "infantil": (5, "infantil"),
    "kids music": (5, "infantil"),
    "kids": (5, "infantil"),
    "children": (5, "infantil"),
    "children's music": (5, "infantil"),
    # ── indie / alternative (low priority — only if nothing else) ─
    "indie": (1, "indie"),
    "alternative": (1, "indie"),
    "alternativa": (1, "indie"),
}

# Tags that explicitly tell us NOTHING about genre — short-circuit
# the loop so they don't pollute counts. (Last.fm tags are a mess.)
NOISE_TAGS = {
    "catalan",
    "català",
    "spanish",
    "espanyol",
    "spain",
    "españa",
    "espana",
    "valencian",
    "catalunya",
    "valencia",
    "balear",
    "andorra",
    "catalan rock",
    "rock catala",  # too generic; we already know
    "barcelona",
    "all",
    "favorites",
    "seen live",
    "favorite",
    "memes",
    "best",
    "love",
    "english",
    "language",
    "female vocalists",
    "female vocalist",
    "male vocalists",
    "band",
    "musica catalana",
    "música catalana",
    "musica en català",
    "música en català",
    "musica",
    "latin",
    "latino",
    "iberian",
}


def _normalise_tag(t: str) -> str:
    """Lower-case + collapse whitespace + strip punctuation noise."""
    return " ".join((t or "").lower().strip().split())


def _iter_tag_names(raw) -> Iterable[str]:
    """Pull tag names from any of our supported shapes:
    - JSON list of {name, count, url} dicts (Last.fm format)
    - JSON list of strings
    - Comma-separated string (legacy)"""
    if not raw:
        return
    if isinstance(raw, str):
        for t in raw.split(","):
            t = _normalise_tag(t)
            if t:
                yield t
        return
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                yield _normalise_tag(item.get("name", ""))
            elif isinstance(item, str):
                yield _normalise_tag(item)


def infer_canonical(lastfm_tags, mb_tags) -> str:
    """Score every canonical via the priority-weighted tag map and
    return the winner, or "" if no signal.

    Last.fm tags weigh slightly more than MB tags because their
    sample size is larger and the community votes are more diverse;
    MB tags are curator-set and tend to be sparse but accurate.
    """
    score: dict[str, int] = defaultdict(int)
    seen_priorities: dict[str, int] = defaultdict(int)

    for source, weight in [(lastfm_tags, 1.0), (mb_tags, 0.8)]:
        for tag in _iter_tag_names(source):
            if not tag or tag in NOISE_TAGS:
                continue
            entry = TAG_TO_CANONICAL.get(tag)
            if not entry:
                continue
            priority, canonical = entry
            score[canonical] += int(round(priority * weight))
            seen_priorities[canonical] = max(seen_priorities[canonical], priority)

    if not score:
        return ""

    # Pick the canonical with highest score; tiebreak by max
    # priority seen for that canonical (more specific wins).
    return max(
        score.items(),
        key=lambda kv: (kv[1], seen_priorities[kv[0]]),
    )[0]
