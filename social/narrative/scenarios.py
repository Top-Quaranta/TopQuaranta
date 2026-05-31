"""Scenario detectors over `TopSetmanal` (Fase 4 reset, 2026-05-18).

# Spec: docs/architecture/social.md

Twelve detectors + a fallback (a1-a12, see ADR-0008). Each
detector returns at most one
`Scenario` (the strongest case of its kind for the given week);
`detect_all` calls every detector and returns the list sorted by
severity desc so the composer picks the headline beat first.

`Scenario.data` carries everything a hero template might need,
pre-rendered: `artista`, `de_artista` (apostrof-aware), `canco`,
`territori_label`, plus the scenario-specific fields. Templates
just `.format(**scenario.data)` — no string surgery at compose
time."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from social.narrative.utils import (
    ordinal_ca,
    territori_label,
    territori_ordinal,
    with_preposition,
)

# ── Data class ─────────────────────────────────────────────────────


@dataclass
class Scenario:
    code: str
    severity: int
    data: dict = field(default_factory=dict)


# ── Helpers ────────────────────────────────────────────────────────


def _previous_monday(setmana: datetime.date) -> datetime.date:
    return setmana - datetime.timedelta(days=7)


def _load_week(territori: str, setmana: datetime.date):
    """Return the ordered TopSetmanal queryset for the week. Locally
    imported to keep this module importable in non-Django contexts."""
    from ranking.models import TopSetmanal

    return (
        TopSetmanal.objects.filter(territori=territori, setmana=setmana)
        .select_related("canco", "canco__artista")
        .order_by("posicio")
    )


def _previous_positions(territori: str, setmana: datetime.date) -> dict[int, int]:
    """`{canco_id: posicio}` of the previous week. Empty dict if
    nothing for that week (first run of a new territori, e.g.)."""
    from ranking.models import TopSetmanal

    prev = TopSetmanal.objects.filter(
        territori=territori,
        setmana=_previous_monday(setmana),
    ).values_list("canco_id", "posicio")
    return {cid: p for cid, p in prev if cid is not None}


def _row_data(row, territori: str) -> tuple[str, str]:
    """Extract `(artista_nom, canco_nom)` from a TopSetmanal row,
    falling back to snapshots if the FKs were nulled."""
    artista = ""
    if row.canco_id and row.canco and row.canco.artista_id:
        artista = row.canco.artista.nom
    if not artista:
        artista = row.artista_nom_snapshot or "—"
    canco = ""
    if row.canco_id and row.canco:
        canco = row.canco.nom
    if not canco:
        canco = row.canco_nom_snapshot or "—"
    return artista, canco


def _base_data(artista: str, canco: str, territori: str) -> dict:
    """The four (now six) invariants every hero template can
    interpolate. The pre-rendered preposition+artist variants
    (`de_artista`, `per_a_artista`, `per_artista`) collapse the
    Catalan contraction rules (article-stripping + apostrof
    elision) at compose-time so templates can just write
    `{de_artista}`, `{per_a_artista}` etc. without string
    surgery. See `social/narrative/utils.with_preposition`."""
    return {
        "artista": artista,
        "de_artista": with_preposition(artista, "de"),
        "per_a_artista": with_preposition(artista, "per_a"),
        "per_artista": with_preposition(artista, "per"),
        "canco": canco,
        "territori_label": territori_label(territori),
        "territori_ordinal": territori_ordinal(territori),
    }


# ── Detectors ──────────────────────────────────────────────────────


def detect_a1_outside_to_top1(
    territori: str, setmana: datetime.date
) -> Optional[Scenario]:
    """Cançó al #1 que la setmana anterior estava fora del top 40 o
    >= #5. Severity 10 si era fora del top, 8 si >=10, 6 si entre
    #5 i #9. Si era <#5 la setmana passada, no és un A1."""
    rows = list(_load_week(territori, setmana)[:1])
    if not rows:
        return None
    top1 = rows[0]
    if top1.posicio != 1 or not top1.canco_id:
        return None
    prev = _previous_positions(territori, setmana)
    prev_pos = prev.get(top1.canco_id)
    if prev_pos is not None and prev_pos < 5:
        return None
    if prev_pos is None:
        severity, prev_str = 10, "fora del top"
    elif prev_pos >= 10:
        severity, prev_str = 8, f"al {ordinal_ca(prev_pos)}"
    else:
        severity, prev_str = 6, f"al {ordinal_ca(prev_pos)}"
    artista, canco = _row_data(top1, territori)
    data = _base_data(artista, canco, territori)
    data["posicio_anterior_str"] = prev_str
    return Scenario("a1_outside_to_top1", severity, data)


def detect_a2_streak(territori: str, setmana: datetime.date) -> Optional[Scenario]:
    """Cançó al #1 N setmanes seguides (N >= 2). Severity = min(N, 10)."""
    rows = list(_load_week(territori, setmana)[:1])
    if not rows or rows[0].posicio != 1 or not rows[0].canco_id:
        return None
    top1 = rows[0]
    from ranking.models import TopSetmanal

    streak = 1
    cursor = _previous_monday(setmana)
    while True:
        prev = (
            TopSetmanal.objects.filter(
                territori=territori, setmana=cursor, canco_id=top1.canco_id
            )
            .values_list("posicio", flat=True)
            .first()
        )
        if prev != 1:
            break
        streak += 1
        cursor = _previous_monday(cursor)
    if streak < 2:
        return None
    artista, canco = _row_data(top1, territori)
    data = _base_data(artista, canco, territori)
    data["streak"] = streak
    return Scenario("a2_streak", min(streak, 10), data)


def detect_a3_fall_from_top1(
    territori: str, setmana: datetime.date
) -> Optional[Scenario]:
    """Cançó que la setmana anterior era #1 i aquesta no ho és.
    Severity 7 si surt del top, 4 si baixa dins del top."""
    from ranking.models import TopSetmanal

    prev_setmana = _previous_monday(setmana)
    prev_top1 = (
        TopSetmanal.objects.filter(territori=territori, setmana=prev_setmana, posicio=1)
        .select_related("canco", "canco__artista")
        .first()
    )
    if not prev_top1 or not prev_top1.canco_id:
        return None
    this_pos = (
        TopSetmanal.objects.filter(
            territori=territori, setmana=setmana, canco_id=prev_top1.canco_id
        )
        .values_list("posicio", flat=True)
        .first()
    )
    if this_pos == 1:
        return None
    artista, canco = _row_data(prev_top1, territori)
    data = _base_data(artista, canco, territori)
    if this_pos is None:
        severity = 7
        data["posicio_nova_str"] = "fora del top"
    else:
        severity = 4
        data["posicio_nova_str"] = f"al {ordinal_ca(this_pos)}"
    return Scenario("a3_fall_from_top1", severity, data)


def detect_a4_debut_alt(territori: str, setmana: datetime.date) -> Optional[Scenario]:
    """Cançó nova al top que debuta a #<=3. Severity = 10 - posicio."""
    rows = list(_load_week(territori, setmana))
    if not rows:
        return None
    prev = _previous_positions(territori, setmana)
    candidate = None
    for r in rows:
        if not r.canco_id or r.posicio > 3:
            continue
        if r.canco_id in prev:
            continue
        if candidate is None or r.posicio < candidate.posicio:
            candidate = r
    if not candidate:
        return None
    artista, canco = _row_data(candidate, territori)
    data = _base_data(artista, canco, territori)
    data["posicio"] = candidate.posicio
    data["posicio_ordinal"] = ordinal_ca(int(candidate.posicio))
    return Scenario("a4_debut_alt", 10 - candidate.posicio, data)


def detect_a5_artista_multiple(
    territori: str, setmana: datetime.date
) -> Optional[Scenario]:
    """Artista amb 3+ cançons al top. Severity = nombre de cançons."""
    rows = list(_load_week(territori, setmana))
    if not rows:
        return None
    by_artist: dict[int, list] = {}
    for r in rows:
        if not r.canco_id or not r.canco or not r.canco.artista_id:
            continue
        by_artist.setdefault(r.canco.artista_id, []).append(r)
    best_aid = None
    best_rows: list = []
    for aid, lst in by_artist.items():
        if len(lst) >= 3 and len(lst) > len(best_rows):
            best_aid = aid
            best_rows = lst
    if not best_aid:
        return None
    artista, _ = _row_data(best_rows[0], territori)
    data = _base_data(artista, "", territori)
    data["n_cancons"] = len(best_rows)
    data["posicions"] = sorted(r.posicio for r in best_rows)
    return Scenario("a5_artista_multiple", len(best_rows), data)


def detect_a6_canco_recent(
    territori: str, setmana: datetime.date
) -> Optional[Scenario]:
    """Cançó publicada fa <=30 dies actualment al top 10.
    Severity = 11 - posicio."""
    rows = list(_load_week(territori, setmana)[:10])
    cutoff = setmana - datetime.timedelta(days=30)
    best = None
    for r in rows:
        if not r.canco or not r.canco.data_llancament:
            continue
        if r.canco.data_llancament < cutoff:
            continue
        if best is None or r.posicio < best.posicio:
            best = r
    if not best:
        return None
    artista, canco = _row_data(best, territori)
    dies = max(1, (setmana - best.canco.data_llancament).days)
    data = _base_data(artista, canco, territori)
    data["posicio"] = best.posicio
    data["posicio_ordinal"] = ordinal_ca(int(best.posicio))
    data["dies"] = dies
    return Scenario("a6_canco_recent", 11 - best.posicio, data)


def detect_a7_long_runner(territori: str, setmana: datetime.date) -> Optional[Scenario]:
    """Cançó publicada fa >=180 dies actualment al top 10. Severity
    fixa 5 (context, no notícia forta)."""
    rows = list(_load_week(territori, setmana)[:10])
    threshold = setmana - datetime.timedelta(days=180)
    best = None
    for r in rows:
        if not r.canco or not r.canco.data_llancament:
            continue
        if r.canco.data_llancament > threshold:
            continue
        if best is None or r.canco.data_llancament < best.canco.data_llancament:
            best = r
    if not best:
        return None
    artista, canco = _row_data(best, territori)
    dies = max(180, (setmana - best.canco.data_llancament).days)
    mesos = max(6, dies // 30)
    data = _base_data(artista, canco, territori)
    data["mesos"] = mesos
    return Scenario("a7_long_runner", 5, data)


def detect_a8_pujada_forta(
    territori: str, setmana: datetime.date
) -> Optional[Scenario]:
    """Cançó que puja >=10 posicions vs setmana anterior i ara és
    al top 10. Severity = pujada // 2."""
    rows = list(_load_week(territori, setmana)[:10])
    prev = _previous_positions(territori, setmana)
    best = None
    best_climb = 0
    for r in rows:
        if not r.canco_id:
            continue
        prev_pos = prev.get(r.canco_id)
        if prev_pos is None:
            continue
        climb = prev_pos - r.posicio
        if climb < 10:
            continue
        if climb > best_climb:
            best_climb = climb
            best = r
    if not best:
        return None
    artista, canco = _row_data(best, territori)
    data = _base_data(artista, canco, territori)
    data["posicio"] = best.posicio
    data["posicio_ordinal"] = ordinal_ca(int(best.posicio))
    data["pujada"] = best_climb
    return Scenario("a8_pujada_forta", best_climb // 2, data)


def detect_a9_debut_anywhere(
    territori: str, setmana: datetime.date
) -> Optional[Scenario]:
    """ADR-0008: Cançó nova al top que NO és top 3 (això ja és A4).
    Coberta posicions 4–40. Severity = max(1, (41 - posicio) // 8) per
    quedar entre 1 i 5: una entrada al #4 val 4, una al #40 val 1.
    Volem una severitat moderada perquè ho fem servir com a notícia
    secundària/terciària, no com a headline (A4 és el headline per
    debuts forts)."""
    rows = list(_load_week(territori, setmana))
    if not rows:
        return None
    prev = _previous_positions(territori, setmana)
    candidate = None
    for r in rows:
        if not r.canco_id:
            continue
        if r.posicio <= 3:
            continue  # A4's job
        if r.canco_id in prev:
            continue
        if candidate is None or r.posicio < candidate.posicio:
            candidate = r
    if not candidate:
        return None
    artista, canco = _row_data(candidate, territori)
    data = _base_data(artista, canco, territori)
    data["posicio"] = candidate.posicio
    data["posicio_ordinal"] = ordinal_ca(int(candidate.posicio))
    severity = max(1, (41 - candidate.posicio) // 8)
    return Scenario("a9_debut_anywhere", severity, data)


def detect_a10_artista_first_ever(
    territori: str, setmana: datetime.date
) -> Optional[Scenario]:
    """ADR-0008: Un artista apareix al top per primera vegada en tota
    la història del territori. Severity 8 — és una notícia rotunda
    («estrena absoluta») que aspira a hero quan el cim no aporta més
    que continuïtat. Si hi ha múltiples first-ever, escollim el de
    posició més alta (millor entrada)."""
    from ranking.models import TopSetmanal

    rows = list(_load_week(territori, setmana))
    if not rows:
        return None
    candidate = None
    for r in rows:
        if not r.canco_id or not r.canco or not r.canco.artista_id:
            continue
        aid = r.canco.artista_id
        # Was this artist in any TopSetmanal row of this territori
        # at any week BEFORE this one?
        seen = TopSetmanal.objects.filter(
            territori=territori,
            setmana__lt=setmana,
            canco__artista_id=aid,
        ).exists()
        if seen:
            continue
        if candidate is None or r.posicio < candidate.posicio:
            candidate = r
    if not candidate:
        return None
    artista, canco = _row_data(candidate, territori)
    data = _base_data(artista, canco, territori)
    data["posicio"] = candidate.posicio
    data["posicio_ordinal"] = ordinal_ca(int(candidate.posicio))
    return Scenario("a10_artista_first_ever", 8, data)


def detect_a11_top5_drop_generic(
    territori: str, setmana: datetime.date
) -> Optional[Scenario]:
    """ADR-0008: Cançó que la setmana anterior era al top 5 (però NO
    #1, això ja és A3) i ara està fora del top 10 o fora del top.
    Severity = 4 + (1 si era al #2 la setmana passada). A3 prima per
    severity, però A11 cobreix les caigudes des de #2..#5 que abans
    no tenien narrativa."""
    from ranking.models import TopSetmanal

    prev_setmana = _previous_monday(setmana)
    prev_top5 = list(
        TopSetmanal.objects.filter(
            territori=territori, setmana=prev_setmana, posicio__in=range(2, 6)
        )
        .select_related("canco", "canco__artista")
        .order_by("posicio")
    )
    if not prev_top5:
        return None
    this_positions = {
        cid: pos
        for cid, pos in TopSetmanal.objects.filter(
            territori=territori, setmana=setmana
        ).values_list("canco_id", "posicio")
        if cid is not None
    }
    candidate = None
    for r in prev_top5:
        if not r.canco_id:
            continue
        this_pos = this_positions.get(r.canco_id)
        if this_pos is not None and this_pos <= 10:
            continue  # didn't drop hard enough
        if candidate is None or r.posicio < candidate.posicio:
            candidate = (r, this_pos)
    if not candidate:
        return None
    row, this_pos = candidate
    artista, canco = _row_data(row, territori)
    data = _base_data(artista, canco, territori)
    data["posicio_anterior"] = row.posicio
    data["posicio_anterior_ordinal"] = ordinal_ca(int(row.posicio))
    if this_pos is None:
        data["posicio_nova_str"] = "fora del top"
    else:
        data["posicio_nova_str"] = f"al {ordinal_ca(this_pos)}"
    severity = 4 + (1 if row.posicio == 2 else 0)
    return Scenario("a11_top5_drop_generic", severity, data)


def detect_a12_artista_emerging(
    territori: str, setmana: datetime.date
) -> Optional[Scenario]:
    """ADR-0008: Artista que té cançons al top aquesta setmana però
    no en tenia cap la setmana anterior (sigui per debut sigui per
    reentrada). Different from A10 (first-ever): A12 cobreix
    reaparicions. Severity 3 — context, no headline. Pren l'artista
    amb la millor posició entrant."""
    from ranking.models import TopSetmanal

    rows = list(_load_week(territori, setmana))
    if not rows:
        return None
    artists_now: dict[int, list] = {}
    for r in rows:
        if not r.canco_id or not r.canco or not r.canco.artista_id:
            continue
        artists_now.setdefault(r.canco.artista_id, []).append(r)
    if not artists_now:
        return None
    prev_setmana = _previous_monday(setmana)
    artists_prev = set(
        TopSetmanal.objects.filter(territori=territori, setmana=prev_setmana)
        .values_list("canco__artista_id", flat=True)
        .distinct()
    )
    artists_prev.discard(None)
    candidate_row = None
    for aid, lst in artists_now.items():
        if aid in artists_prev:
            continue
        # A10 supersedes A12 for first-ever — skip if no historical
        # presence at all (the cron for A10 will catch it).
        if not TopSetmanal.objects.filter(
            territori=territori, setmana__lt=setmana, canco__artista_id=aid
        ).exists():
            continue
        best = min(lst, key=lambda r: r.posicio)
        if candidate_row is None or best.posicio < candidate_row.posicio:
            candidate_row = best
    if not candidate_row:
        return None
    artista, canco = _row_data(candidate_row, territori)
    data = _base_data(artista, canco, territori)
    data["posicio"] = candidate_row.posicio
    data["posicio_ordinal"] = ordinal_ca(int(candidate_row.posicio))
    return Scenario("a12_artista_emerging", 3, data)


def fallback_scenario(territori: str) -> Scenario:
    """Catch-all when no detector fires."""
    return Scenario(
        "fallback_no_event",
        0,
        {
            "territori_label": territori_label(territori),
            "territori_ordinal": territori_ordinal(territori),
        },
    )


# ── Public entrypoint ─────────────────────────────────────────────


_DETECTORS = (
    detect_a1_outside_to_top1,
    detect_a2_streak,
    detect_a3_fall_from_top1,
    detect_a4_debut_alt,
    detect_a5_artista_multiple,
    detect_a6_canco_recent,
    detect_a7_long_runner,
    detect_a8_pujada_forta,
    detect_a9_debut_anywhere,
    detect_a10_artista_first_ever,
    detect_a11_top5_drop_generic,
    detect_a12_artista_emerging,
)


def detect_all(territori: str, setmana: datetime.date) -> list[Scenario]:
    """Run every detector and return the scenarios sorted by severity
    desc. The composer treats `[]` as the cue to use `fallback_scenario`."""
    out: list[Scenario] = []
    for det in _DETECTORS:
        try:
            s = det(territori, setmana)
        except Exception:
            # A detector bug must not poison the publication. The
            # composer will fall back to fallback_scenario; the
            # outer captions.compose_for_channel try/except catches
            # everything else.
            continue
        if s is not None:
            out.append(s)
    out.sort(key=lambda s: -s.severity)
    return out
