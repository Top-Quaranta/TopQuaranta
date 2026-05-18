"""Universal pattern detectors over `TopSetmanal`.

Each detector returns a `Scenario` or None. `severity` is a numeric
score so callers can sort and pick the "hero" pattern of the week.
Empirical priorities (audit 2026-05-18): A2 streaks at long counts
beat A4 strong debuts which beat A5 multi-track artists. The
severity scale is intentionally not normalised across detectors —
callers compare within-detector except for the final tie-break
which is encoded in `detect_all`'s explicit ordering.

Detectors are cheap: a single QuerySet per detector, no joins
beyond the `canco__artista` select_related already implied by
TopSetmanal usage.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

# Visitor-facing label for each territori code. Mirrors
# `web-react/src/components/editorial.jsx::TERRITORI_NOM` (PPCC →
# "Global" on public surfaces; DB code stays as PPCC).
TERRITORI_LABELS = {
    "PPCC": "Global",
    "CAT": "Catalunya",
    "VAL": "País Valencià",
    "BAL": "Illes Balears",
    "AND": "Andorra",
    "CNO": "Catalunya del Nord",
    "FRA": "Franja de Ponent",
    "ALG": "L'Alguer",
    "ALT": "Altres",
    "CAR": "El Carxe",
}


@dataclass
class Scenario:
    """A single detected narrative pattern.

    `code` matches the `phrases.PHRASES` key used by the composer to
    pick a templated copy line. `severity` is the within-code score
    used to rank multi-fires. `data` contains the interpolation
    variables for the phrase templates.
    """

    code: str
    severity: int
    data: dict = field(default_factory=dict)


def _label(territori: str) -> str:
    return TERRITORI_LABELS.get(territori, territori)


def detect_a2_streak(territori: str, setmana: date) -> Optional[Scenario]:
    """A2 — Same canco at #1 as last week (and possibly earlier).

    Walks back consecutive weeks counting how long the streak has
    been running. Returns None when the streak is just 1 week
    (i.e. nothing has held over) — the headline value of A2 only
    starts at 2 consecutive weeks.
    """
    from ranking.models import TopSetmanal

    current = (
        TopSetmanal.objects.filter(
            territori=territori, setmana=setmana, posicio=1
        )
        .select_related("canco__artista")
        .first()
    )
    if not current or current.canco_id is None:
        return None

    streak = 1
    probe = setmana - timedelta(days=7)
    while True:
        prev = TopSetmanal.objects.filter(
            territori=territori, setmana=probe, posicio=1
        ).first()
        if prev is None or prev.canco_id != current.canco_id:
            break
        streak += 1
        probe -= timedelta(days=7)

    if streak < 2:
        return None

    return Scenario(
        code="a2_streak",
        severity=streak,
        data={
            "artista": current.canco.artista.nom,
            "canco": current.canco.nom,
            "streak": streak,
            "territori_label": _label(territori),
        },
    )


def detect_a4_debut_alt(territori: str, setmana: date) -> Optional[Scenario]:
    """A4 — A canco NEW to the top (absent last week) debuts at ≤ #3.

    "New" means it wasn't anywhere in last week's top, not just
    "not at this position". `severity` is `10 - posicio` so a #1
    debut (sev=9) beats a #2 debut (sev=8) beats a #3 debut (sev=7).
    """
    from ranking.models import TopSetmanal

    last_week = setmana - timedelta(days=7)
    last_week_cancos = set(
        TopSetmanal.objects.filter(territori=territori, setmana=last_week)
        .exclude(canco_id__isnull=True)
        .values_list("canco_id", flat=True)
    )
    debut = (
        TopSetmanal.objects.filter(
            territori=territori, setmana=setmana, posicio__lte=3
        )
        .exclude(canco_id__in=last_week_cancos)
        .exclude(canco_id__isnull=True)
        .select_related("canco__artista")
        .order_by("posicio")
        .first()
    )
    if debut is None:
        return None

    return Scenario(
        code="a4_debut_alt",
        severity=10 - debut.posicio,
        data={
            "artista": debut.canco.artista.nom,
            "canco": debut.canco.nom,
            "posicio": debut.posicio,
            "territori_label": _label(territori),
        },
    )


def detect_a5_artista_multiple(
    territori: str, setmana: date
) -> Optional[Scenario]:
    """A5 — An artista has 3+ cançons in this week's top.

    Picks the most prolific artista that week (ties broken by
    lowest min-posicio). `severity` equals the cançó count, so a
    9-track week (Maria Jaume BAL 2026-05-04) beats a 4-track week.
    """
    from ranking.models import TopSetmanal

    rows = list(
        TopSetmanal.objects.filter(territori=territori, setmana=setmana)
        .exclude(canco_id__isnull=True)
        .select_related("canco__artista")
    )
    if not rows:
        return None

    by_artista: dict[int, list] = defaultdict(list)
    for r in rows:
        by_artista[r.canco.artista_id].append(r)

    # Pick artist with most cançons; tie-break: lowest best posicio.
    best_artist_rows = max(
        by_artista.values(),
        key=lambda lst: (len(lst), -min(r.posicio for r in lst)),
    )
    if len(best_artist_rows) < 3:
        return None

    artista = best_artist_rows[0].canco.artista
    posicions = sorted(r.posicio for r in best_artist_rows)

    return Scenario(
        code="a5_artista_multiple",
        severity=len(best_artist_rows),
        data={
            "artista": artista.nom,
            "n_cancons": len(best_artist_rows),
            "posicions": posicions,
            "territori_label": _label(territori),
        },
    )


def detect_all(territori: str, setmana: date) -> list[Scenario]:
    """Run all detectors and return scenarios sorted by severity
    descending. The composer treats the first item as the "hero"
    and (optionally) the second as the "supporting beat"."""
    out: list[Scenario] = []
    for detector in (
        detect_a2_streak,
        detect_a4_debut_alt,
        detect_a5_artista_multiple,
    ):
        s = detector(territori, setmana)
        if s is not None:
            out.append(s)
    out.sort(key=lambda s: s.severity, reverse=True)
    return out
