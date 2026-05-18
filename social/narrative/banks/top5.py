"""Top-5 completion phrases.

Two banks per length tier — chosen by the composer depending on
whether the hero referent occupies the #1 slot or not:

* **CASE A — hero is #1.** The completion mention covers the rest
  of the top 5 (positions 2-5 minus any other already-mentioned
  referent). Templates take a single `{artistes}` (short) or
  `{detalls}` (long) variable.

* **CASE B — hero is NOT #1.** We name the #1 entry separately
  (leader) before listing the remaining top-5 entries. Templates
  take `{leader_canco}`, `{leader_de}` (apostrof-aware), and the
  rest as `{artistes}` / `{detalls}`.

Two registers: SHORT for Mastodon / Bluesky / story (plain artist
names), LONG for Instagram-feed / Telegram / newsletter (entries
with cançó + posició detail)."""

from __future__ import annotations

import random

from social.narrative.utils import apostrof_de, llista_amb_i

# ── CASE A — hero referent is #1 ──────────────────────────────────
# Variables: {artistes} (short) or {detalls} (long).

COMPLETING_SHORT_TEMPLATES: list[str] = [
    "Completen el top 5 {artistes}.",
    "També al top 5 hi trobem {artistes}.",
    "Acompanyen al top 5 {artistes}.",
    "No falten al top 5 {artistes}.",
    "Continuen al top 5 {artistes}.",
    "Al top 5 hi són igualment {artistes}.",
    "Completen el podi setmanal {artistes}.",
    "Hi són també {artistes}, al top 5.",
    "Tanquen el top 5 {artistes}.",
    "Al top 5 hi tenim, a més, {artistes}.",
    "Completen la fotografia del cim {artistes}.",
    "I al top 5 també hi són {artistes}.",
]

COMPLETING_LONG_TEMPLATES: list[str] = [
    "Completen el top 5 {detalls}.",
    "També al top 5 hi tenim {detalls}.",
    "El top 5 es tanca amb {detalls}.",
    "Hi són al top 5, a més, {detalls}.",
    "Acompanyen el cim {detalls}.",
    "Al top 5 hi trobem també {detalls}.",
    "Continuen al top 5 {detalls}.",
    "Mantenen presència al top 5 {detalls}.",
]


# ── CASE B — hero referent is NOT #1 ──────────────────────────────
# Variables: {leader_canco}, {leader_de}, {artistes}/{detalls}.

WITH_LEADER_SHORT_TEMPLATES: list[str] = [
    "Al cim continua «{leader_canco}», {leader_de}. També al top 5 hi trobem {artistes}.",
    "El #1 segueix sent de «{leader_canco}», {leader_de}. Al top 5 hi trobem també {artistes}.",
    "Al cap del rànquing, «{leader_canco}», {leader_de}. Al top 5 també hi són {artistes}.",
    "Al #1 segueix «{leader_canco}», {leader_de}; al top 5 acompanyen {artistes}.",
    "El primer lloc continua amb «{leader_canco}», {leader_de}. Al top 5 hi tenim també {artistes}.",
    "Al cim, «{leader_canco}» {leader_de}; també al top 5 {artistes}.",
    "El #1 és per a «{leader_canco}», {leader_de}. Al top 5 trobem també {artistes}.",
    "Al podi continua «{leader_canco}», {leader_de}, i al top 5 hi són també {artistes}.",
    "Sense canvis al cim ({leader_de}, «{leader_canco}»); al top 5 hi tenim {artistes}.",
    "«{leader_canco}», {leader_de}, manté el #1, i al top 5 acompanyen {artistes}.",
]

WITH_LEADER_LONG_TEMPLATES: list[str] = [
    "Al cim continua «{leader_canco}», {leader_de}, al #1. També al top 5 hi tenim {detalls}.",
    "El #1 segueix sent de «{leader_canco}», {leader_de}. Al top 5 hi trobem també {detalls}.",
    "Al cap del rànquing, «{leader_canco}», {leader_de}, manté el #1. Al top 5 també hi són {detalls}.",
    "El primer lloc continua amb «{leader_canco}», {leader_de}. Acompanyen al top 5 {detalls}.",
    "Al podi continua «{leader_canco}», {leader_de}, al cim. Al top 5 hi són també {detalls}.",
    "El cim és per a «{leader_canco}», {leader_de}. Al top 5 trobem també {detalls}.",
    "Al #1 segueix «{leader_canco}», {leader_de}; al top 5 acompanyen {detalls}.",
    "Al cap, «{leader_canco}» {leader_de} continua manant; al top 5 hi trobem també {detalls}.",
]


def _detall(entry: dict) -> str:
    """Render a long-form mention for one entry: «canço» de A al #N."""
    canco = entry.get("canco_nom") or "—"
    artista = entry.get("artista_nom") or "—"
    posicio = entry.get("posicio") or "?"
    return f"«{canco}» {apostrof_de(artista)} al #{posicio}"


def pick_short(
    others: list[dict],
    leader: dict | None = None,
    rng: random.Random | None = None,
) -> str:
    """Pick a SHORT top-5 completion line.

    `leader` is the #1 entry when the hero referent is NOT at the
    cim. When given, the template mentions `«leader_canco», leader_de`
    explicitly and lists `others` as completion. When `None`, the
    hero is the cim; the template is "Completen el top 5 X, Y i Z."
    Returns "" if there's nothing meaningful to say."""
    if leader is None:
        if not others:
            return ""
        artistes = llista_amb_i([(e.get("artista_nom") or "—") for e in others])
        tpl = (rng or random).choice(COMPLETING_SHORT_TEMPLATES)
        return tpl.format(artistes=artistes)
    # Case B
    leader_canco = leader.get("canco_nom") or "—"
    leader_artista = leader.get("artista_nom") or "—"
    if not others:
        # Nothing else to mention; just give the leader its line.
        return f"Al cim continua «{leader_canco}», {apostrof_de(leader_artista)}."
    artistes = llista_amb_i([(e.get("artista_nom") or "—") for e in others])
    tpl = (rng or random).choice(WITH_LEADER_SHORT_TEMPLATES)
    return tpl.format(
        leader_canco=leader_canco,
        leader_de=apostrof_de(leader_artista),
        artistes=artistes,
    )


def pick_long(
    others: list[dict],
    leader: dict | None = None,
    rng: random.Random | None = None,
) -> str:
    """Pick a LONG top-5 completion line (with cançó+posició
    detail). Same `leader` semantics as `pick_short`."""
    if leader is None:
        if not others:
            return ""
        detalls = llista_amb_i([_detall(e) for e in others])
        tpl = (rng or random).choice(COMPLETING_LONG_TEMPLATES)
        return tpl.format(detalls=detalls)
    # Case B
    leader_canco = leader.get("canco_nom") or "—"
    leader_artista = leader.get("artista_nom") or "—"
    if not others:
        return (
            f"Al cim continua «{leader_canco}», "
            f"{apostrof_de(leader_artista)}, al #1."
        )
    detalls = llista_amb_i([_detall(e) for e in others])
    tpl = (rng or random).choice(WITH_LEADER_LONG_TEMPLATES)
    return tpl.format(
        leader_canco=leader_canco,
        leader_de=apostrof_de(leader_artista),
        detalls=detalls,
    )
