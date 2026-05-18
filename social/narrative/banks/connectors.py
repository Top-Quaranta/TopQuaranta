"""Connectors between the hero scenario and a secondary scenario.

Only used by channels with enough char budget to afford two
beats — Instagram feed and the newsletter. Short, no emoji, no
punctuation suffix (the caller appends a space + the secondary
phrase)."""

from __future__ import annotations

import random

CONNECTORS: list[str] = [
    "Per altra banda,",
    "Mentrestant,",
    "I no només això:",
    "També:",
    "A més,",
    "Al mateix temps,",
    "Però la setmana porta més:",
    "I encara hi ha més:",
    "Una altra notícia:",
    "Sense oblidar:",
    "I tampoc passa desapercebut:",
    "Hi ha més per a destacar:",
    "Una segona notícia de la setmana:",
    "L'altra cara de la setmana:",
    "I, en paral·lel,",
]


def lowercase_first(text: str) -> str:
    """Decapitalise the first letter of `text` only if it looks like a
    common word (lowercase ASCII letter after lowering). Skips proper
    nouns (artist names, acronyms in caps) so we don't damage
    `OBESES debuta…` into `oBESES debuta…`.

    Heuristic: lowercase only if the first TWO letters are not BOTH
    upper, AND the first letter isn't part of a quoted title."""
    if not text or text.startswith("«") or text.startswith('"'):
        return text
    first = text[0]
    second = text[1] if len(text) > 1 else ""
    if first.isupper() and second.isupper():
        # Looks like an acronym (OBESES, NAINA, …) — keep caps.
        return text
    if first.isalpha():
        return first.lower() + text[1:]
    return text


def pick_connector(rng: random.Random | None = None) -> str:
    """Pick one connector at random. The caller is expected to
    use it as `f"{connector} {secondary_phrase}"`."""
    return (rng or random).choice(CONNECTORS)
