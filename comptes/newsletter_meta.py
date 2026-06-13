"""Trend indicators + editorial subject for the newsletter (Step 2).

`trend_indicator` classifies a top entry's week-over-week movement
(from `posicio` + `posicio_anterior`, which `payload.build_top` already
exposes) into a small labelled badge; `a13_top1_return` overrides it to
TORNA. `derive_subject` builds a short, varied subject line from the
hero scenario (highest severity) with a per-code phrase bank.
"""

from __future__ import annotations

import random

# Redisseny movement palette (web index.css L163-166): tuned for legibility
# on the dark newsletter surface (#141319), mirroring the site's top rows.
_GREEN = "#7bbf7b"  # pujada (up accent)
_RED = "#dd7882"  # baixada (down accent)
_GRAY = "#9aa0a6"  # estable (neutral)
_YELLOW = "#facc15"  # debut (new entry)
_REENTRY = "#e8a44d"  # torna (re-entry accent)
_INK = "#0a0a0a"  # badge foreground on the accent fills

# kind → (text colour, badge bg or None). With a bg the partial renders a
# filled badge (DEBUT/TORNA); without one, coloured text (↑N/↓N/→).
_TREND_STYLES = {
    "pujada": (_GREEN, None),
    "baixada": (_RED, None),
    "estable": (_GRAY, None),
    "debut": (_INK, _YELLOW),  # ink text on the yellow "new" fill
    "torna": (_INK, _REENTRY),  # ink text on the amber "re-entry" fill
}


def trend_indicator(
    posicio: int,
    posicio_anterior: int | None,
    *,
    is_return: bool = False,
) -> dict:
    """Classify movement → ``{"text", "kind", "color", "bg"}``.

    * `is_return` (a13 fired for this song) → TORNA (wins over a fresh
      DEBUT, since a returning #1 was in the top before).
    * `posicio_anterior is None` → DEBUT.
    * else ↑N / ↓N / → from the delta.
    """
    if is_return:
        kind, text = "torna", "TORNA"
    elif posicio_anterior is None:
        kind, text = "debut", "DEBUT"
    else:
        delta = posicio_anterior - posicio
        if delta > 0:
            kind, text = "pujada", f"↑{delta}"
        elif delta < 0:
            kind, text = "baixada", f"↓{-delta}"
        else:
            kind, text = "estable", "→"
    color, bg = _TREND_STYLES[kind]
    return {"text": text, "kind": kind, "color": color, "bg": bg}


# ── Editorial subject ────────────────────────────────────────────────
# Short descriptors (~30-50 chars) per hero scenario_code. The final
# subject is "Setmana {N} · {descriptor}". `{artista}` / `{canco}` are
# filled from the scenario's data.
_SUBJECT_BANK: dict[str, list[str]] = {
    "a1_outside_to_top1": [
        "{artista} entra al #1",
        "Nou #1: {artista}",
        "{artista} assalta el cim",
    ],
    "a2_streak": [
        "{artista} manté el #1",
        "{artista} no afluixa al cim",
        "Segueix manant {artista}",
    ],
    "a3_fall_from_top1": [
        "Canvi al cim",
        "El #1 canvia de mans",
        "Nou líder aquesta setmana",
    ],
    "a4_debut_alt": [
        "Debut fort: {artista}",
        "{artista} entra per la porta gran",
        "Estrena destacada: {canco}",
    ],
    "a5_artista_multiple": [
        "Setmana de {artista}",
        "{artista} omple el top",
        "Domini de {artista}",
    ],
    "a6_canco_recent": [
        "Puja ràpid: {canco}",
        "{artista} irromp al top",
        "Estrena recent en alça",
    ],
    "a7_long_runner": [
        "Un clàssic resisteix",
        "{canco} no marxa del top",
        "Llarga vida a {canco}",
    ],
    "a8_pujada_forta": [
        "{artista} s'enfila",
        "Gran salt de {canco}",
        "Pujada forta: {artista}",
    ],
    "a9_debut_anywhere": [
        "Cara nova al top: {artista}",
        "Nova entrada: {canco}",
    ],
    "a10_artista_first_ever": [
        "Estrena absoluta: {artista}",
        "{artista}, per primer cop al top",
    ],
    "a11_top5_drop_generic": [
        "Sotrac al top 5",
        "Caigudes a la part alta",
    ],
    "a12_artista_emerging": [
        "Reapareix {artista}",
        "{artista} torna a sonar",
    ],
    "a13_top1_return": [
        "Torna {artista}",
        "{artista} reconquereix el #1",
        "El retorn de {artista}",
    ],
    "fallback_no_event": [
        "Top Global",
        "El top de la setmana",
        "Nou top setmanal",
    ],
}

_MAX_SUBJECT = 60


def derive_subject(
    hero_scenario,
    project_week: int,
    rng: random.Random | None = None,
) -> str:
    """Build ``"Setmana {N} · {descriptor}"`` from the hero scenario.

    Falls back to the generic descriptor on an unknown code, a missing
    placeholder, or an over-length result."""
    rng = rng or random.Random()
    prefix = f"Setmana {project_week} · "
    code = getattr(hero_scenario, "code", "fallback_no_event")
    data = getattr(hero_scenario, "data", {}) or {}
    options = _SUBJECT_BANK.get(code) or _SUBJECT_BANK["fallback_no_event"]
    try:
        descriptor = rng.choice(options).format(**data)
    except (KeyError, IndexError):
        descriptor = rng.choice(_SUBJECT_BANK["fallback_no_event"])
    subject = f"{prefix}{descriptor}"
    if len(subject) > _MAX_SUBJECT:
        # Trim to a clean fallback rather than truncating mid-word.
        subject = f"{prefix}Top Global"
    return subject
