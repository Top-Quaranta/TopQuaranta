"""Transition paragraphs between narrative and listing — newsletter
only. The newsletter's HTML template already renders the `<ol>` of
entries below the narrative; this small bank gives the composer a
soft hand-off so the reader doesn't jump from a sentence into a
numbered list cold."""

from __future__ import annotations

import random

NEWSLETTER_TRANSITIONS: list[str] = [
    "A continuació, el rànquing complet d'aquesta setmana.",
    "Tens el top sencer just a sota.",
    "Aquí baix, el rànquing detallat de les 40 cançons d'aquesta setmana.",
    "I la classificació sencera, just a continuació.",
    "Repassem el rànquing complet, posició a posició:",
    "Per als detalls de tota la setmana, mira la llista que ve a sota.",
    "El top sencer de la setmana, ordenat per posició:",
    "I aquí tens la classificació completa:",
]


def pick_transition(rng: random.Random | None = None) -> str:
    return (rng or random).choice(NEWSLETTER_TRANSITIONS)
