"""Hashtag policy per channel.

Each channel has its own density preference; Mastodon/Bluesky
audiences read hashtags as noise above a tight threshold while
Instagram's discovery surface benefits from 8-12. We start from a
territory-specific accent then top up with generic discovery tags
up to the channel budget."""

from __future__ import annotations

import random

# ── Per-territori accent (always at the front) ───────────────────
TERRITORY_HASHTAGS: dict[str, list[str]] = {
    # PPCC (global top): neutral hashtags only — no "#PaïsosCatalans"
    # (never user-visible; the public name is "Global"). No replacement
    # global hashtag.
    "PPCC": ["#TopQuaranta", "#MúsicaEnCatalà"],
    "CAT": ["#TopQuaranta", "#MúsicaEnCatalà", "#Catalunya"],
    "VAL": ["#TopQuaranta", "#MúsicaEnValencià", "#PaísValencià"],
    "BAL": ["#TopQuaranta", "#MúsicaBalear", "#IllesBalears"],
    "AND": ["#TopQuaranta", "#MúsicaEnCatalà", "#Andorra"],
    "CNO": ["#TopQuaranta", "#MúsicaEnCatalà", "#CatalunyaNord"],
    "FRA": ["#TopQuaranta", "#MúsicaEnCatalà", "#FranjaPonent"],
    "ALG": ["#TopQuaranta", "#MúsicaEnCatalà", "#Alguer"],
}

# Generic discovery hashtags — used to pad up to the channel
# budget. Picked at random from this pool per post so the same
# post next week doesn't carry the identical hashtag wall.
GENERIC_HASHTAGS: list[str] = [
    "#TopSetmanal",
    "#NovaMúsica",
    "#Música",
    "#MúsicaIndependent",
    "#MúsicaEnDirecte",
    "#Indie",
    "#PopRock",
    "#Cançó",
    "#MúsicaCatalana",
    "#EscenaCatalana",
    "#TopSetmana",
]

# Per-channel preferred range. Build picks a random N within
# [low, high] (inclusive) per post so the density isn't fixed.
CHANNEL_HASHTAG_POLICY: dict[str, tuple[int, int]] = {
    "instagram_feed": (8, 12),
    "instagram_story": (3, 5),
    "mastodon": (3, 4),
    "bluesky": (1, 2),
    "telegram": (3, 5),
    "newsletter": (0, 3),
}


def build_hashtags(
    territori: str,
    channel: str,
    rng: random.Random | None = None,
) -> list[str]:
    """Return a deduplicated list of hashtags for this post.
    Territory accent first (always-on), then generic discovery
    tags sampled to fit the channel's density budget."""
    low, high = CHANNEL_HASHTAG_POLICY.get(channel, (3, 5))
    if high <= 0:
        return []
    target = (rng or random).randint(low, high)
    base = list(TERRITORY_HASHTAGS.get(territori, ["#TopQuaranta", "#MúsicaEnCatalà"]))
    # Drop duplicates while preserving order.
    seen = set(base)
    pool = [h for h in GENERIC_HASHTAGS if h not in seen]
    (rng or random).shuffle(pool)
    out = list(base)
    for h in pool:
        if len(out) >= target:
            break
        out.append(h)
    return out[:target]
