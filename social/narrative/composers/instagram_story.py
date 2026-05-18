"""Instagram story composer.

A story-set is a sequence of vertical PNG frames rendered by
`social/renderer.py`. The text this composer returns is the
overlay copy that the renderer paints on the intro frame (and
possibly on closing frames in future iterations). Hashtags are
not used inside story media; the channel is non-linkable for IG.
"""

from __future__ import annotations

from social.narrative.registry import pick_phrase

CHANNEL = "instagram_story"


def compose(
    scenarios: list,
    entries: list[dict],
    *,
    territori: str,
    setmana,
    rng=None,
) -> dict:
    overlay = ""
    if scenarios:
        hero = scenarios[0]
        _, overlay = pick_phrase(hero, "short", territori, CHANNEL, rng=rng)
    return {"text": overlay, "hashtags": [], "cta": ""}
