"""Headline synthesis for the #1 story hero slide (Step 3).

Parallel to `comptes.newsletter_meta.derive_subject` but tuned for a big
visual headline above the #1 cover: short (≤ 50 chars so it fits a large
Playfair line), uppercased, no "Setmana N" prefix. Picks a template per
hero `scenario_code` and fills it from the scenario data
(`streak`, `gap_setmanes_str`, …). Created in PR 3a; the renderer wires
it into the #1 hero slide in PR 3b.
"""

from __future__ import annotations

import random

_MAX = 50

_STORY_HERO: dict[str, list[str]] = {
    "a1_outside_to_top1": ["DEBUT AL CIM", "NOU #1", "ASSALT AL #1"],
    "a2_streak": [
        "{streak}a SETMANA AL CIM",
        "{streak} SETMANES AL #1",
        "SEGUEIX MANANT",
    ],
    "a3_fall_from_top1": ["NOU #1", "CANVI AL CIM"],
    "a4_debut_alt": ["DEBUT FORT AL TOP", "ENTRADA DIRECTA"],
    "a5_artista_multiple": ["DOMINI ABSOLUT", "LA SETMANA ÉS SEVA"],
    "a6_canco_recent": ["NOVETAT AL CIM", "PUJA RÀPID AL #1"],
    "a7_long_runner": ["UN CLÀSSIC AL CIM", "RESISTÈNCIA AL TOP"],
    "a8_pujada_forta": ["GRAN SALT AL #1", "PUJADA FORTA AL CIM"],
    "a9_debut_anywhere": ["NOVA ENTRADA", "CARA NOVA AL TOP"],
    "a10_artista_first_ever": ["ESTRENA ABSOLUTA", "PRIMER COP AL #1"],
    "a11_top5_drop_generic": ["NOU LIDERATGE"],
    "a12_artista_emerging": ["REAPARICIÓ AL CIM"],
    "a13_top1_return": [
        "TORNA AL #1",
        "RECONQUESTA DEL CIM",
        "TORNA AL CIM DESPRÉS DE {gap_setmanes_str}",
    ],
    "fallback_no_event": ["EL #1 DE LA SETMANA", "AL CAPDAMUNT DEL TOP"],
}


def synthesize_hero(scenario, rng: random.Random | None = None) -> str:
    """Return a short uppercase headline for the #1 hero slide.

    Falls back to a generic headline on an unknown code, a missing
    placeholder, or an over-length result."""
    rng = rng or random.Random()
    code = getattr(scenario, "code", "fallback_no_event")
    data = getattr(scenario, "data", {}) or {}
    options = _STORY_HERO.get(code) or _STORY_HERO["fallback_no_event"]
    try:
        text = rng.choice(options).format(**data)
    except (KeyError, IndexError):
        text = rng.choice(_STORY_HERO["fallback_no_event"])
    text = text.upper()
    if len(text) > _MAX:
        text = rng.choice(_STORY_HERO["fallback_no_event"]).upper()
    return text
