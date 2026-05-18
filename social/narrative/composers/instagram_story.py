"""Instagram-story composer (Fase 4 reset).

The story-set is image-only at IG; this composer returns the overlay
text the renderer will paint on the intro frame. Single short phrase,
no CTA / hashtags / top5 (the story is non-linkable and tiny)."""

from __future__ import annotations

import random

from social.narrative import scenarios as scen
from social.narrative.registry import pick_phrase

CHANNEL = "instagram_story"


def compose(scenarios, entries, *, territori, setmana, rng=None) -> dict:
    rng = rng or random.Random()
    hero = scenarios[0] if scenarios else scen.fallback_scenario(territori)
    pid, overlay = pick_phrase(hero, "short", territori, CHANNEL, rng=rng)
    phrase_ids = [pid] if pid else []
    return {
        "text": overlay,
        "hashtags": [],
        "cta": "",
        "phrase_ids": phrase_ids,
    }
