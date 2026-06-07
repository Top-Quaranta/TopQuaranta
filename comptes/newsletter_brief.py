"""Weekly newsletter brief for the cloud routine (read-only facts).

`build_brief()` assembles a structured, source-grounded snapshot of the
week's Global (PPCC) top so a cloud routine (or the engine fallback) can
write the editorial text. It NEVER writes anything.

Design notes:
  - The week is THIS week's Monday (`date.today() - weekday`), the same
    anchor `calcular_top` / `generar_esborrany_newsletter` use. If the
    TopSetmanal for that week is not consolidated yet, returns
    `{"status": "not_ready"}` (the anti-stale guard) so the routine never
    builds from a stale top.
  - `can_call_new` reuses the freshness gate
    (`social.narrative.freshness.is_verified_recent_release`), NOT a bare
    date window: it also rejects version-marker titles + posthumous
    reissues.
  - Low-confidence Last.fm tags live in their own section, explicitly
    separated from the grounded facts.

# Spec: docs/architecture/comptes.md
"""

from __future__ import annotations

import datetime
import logging
import urllib.request
import xml.etree.ElementTree as ET

from django.conf import settings
from django.db.models import Count, Min

from ranking.models import TopSetmanal

logger = logging.getLogger(__name__)

TIPUS = "top_ppcc"
TERRITORI = "PPCC"


def current_monday(today: datetime.date | None = None) -> datetime.date:
    today = today or datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def _top_age_weeks() -> int:
    return TopSetmanal.objects.values("setmana").distinct().count()


def _global_first_setmana() -> datetime.date | None:
    return TopSetmanal.objects.aggregate(m=Min("setmana"))["m"]


def _moviment(posicio: int, anterior: int | None) -> str:
    if anterior is None:
        return "debut"
    delta = anterior - posicio
    if delta > 0:
        return f"+{delta}"
    if delta < 0:
        return f"-{abs(delta)}"
    return "="


def _artista_origen(artista) -> dict | None:
    """First known origin for an artista: municipi (→ comarca +
    territori) when present, else free-text, else None. Read-only."""
    if artista is None:
        return None
    loc = artista.localitats.select_related("municipi__territori").first()
    if loc is None:
        return None
    if loc.municipi:
        return {
            "municipi": loc.municipi.nom,
            "comarca": loc.municipi.comarca,
            "territori": loc.municipi.territori_id,
        }
    if loc.localitat_manual:
        return {"municipi": None, "comarca": None, "manual": loc.localitat_manual}
    return None


def _fetch_vilaweb(limit: int = 5) -> list[dict]:
    """Recent VilaWeb headlines (title, source, date). Best-effort: any
    network/parse failure yields an empty list, never raises."""
    url = getattr(settings, "VILAWEB_RSS_URL", "")
    if not url:
        return []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TopQuaranta/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        items = root.findall(".//channel/item")[:limit]
        out = []
        for it in items:
            title = (it.findtext("title") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            if title:
                out.append({"titol": title, "font": "VilaWeb", "data": pub})
        return out
    except Exception:  # noqa: BLE001
        logger.warning("newsletter_brief: VilaWeb RSS fetch failed", exc_info=True)
        return []


def build_brief(setmana: datetime.date | None = None) -> dict:
    """Assemble the weekly brief. Returns `{"status": "not_ready"}` when
    this week's PPCC top isn't consolidated yet."""
    setmana = setmana or current_monday()
    saturday = setmana + datetime.timedelta(days=5)

    rows = list(
        TopSetmanal.objects.filter(territori=TERRITORI, setmana=setmana)
        .select_related("canco", "canco__artista", "canco__album")
        .order_by("posicio")[:10]
    )
    if not rows:
        return {
            "status": "not_ready",
            "motiu": f"TopSetmanal {TERRITORI} de la setmana {setmana} no consolidat",
            "setmana": setmana.isoformat(),
        }

    # Previous-week positions for movement.
    from social.payload import _prev_setmana

    prev = _prev_setmana(setmana, TERRITORI)
    prev_pos = {}
    if prev is not None:
        prev_pos = dict(
            TopSetmanal.objects.filter(territori=TERRITORI, setmana=prev).values_list(
                "canco_id", "posicio"
            )
        )

    # Per-artista top history, one grouped query for the top-10 artistes.
    artista_ids = [
        r.canco.artista_id for r in rows if r.canco_id and r.canco.artista_id
    ]
    hist = {
        h["canco__artista_id"]: h
        for h in TopSetmanal.objects.filter(canco__artista_id__in=artista_ids)
        .values("canco__artista_id")
        .annotate(
            setmanes=Count("setmana", distinct=True),
            millor=Min("posicio"),
            primera=Min("setmana"),
        )
    }
    global_first = _global_first_setmana()

    top10 = []
    for r in rows:
        canco = r.canco
        artista = canco.artista if canco else None
        h = hist.get(artista.id) if artista else None
        primera = h["primera"] if h else None
        top10.append(
            {
                "posicio": r.posicio,
                "canco": canco.nom if canco else "—",
                "artistes": (
                    [artista.nom, *[a.nom for a in canco.artistes_col_ordered()]]
                    if (canco and artista)
                    else ["—"]
                ),
                "moviment": _moviment(r.posicio, prev_pos.get(r.canco_id)),
                "can_call_new": (
                    is_verified_recent_release(canco, ref_date=saturday)
                    if canco
                    else False
                ),
                "primera_aparicio": {
                    "setmana": primera.isoformat() if primera else None,
                    # week-1-birth: the artist's first appearance is the
                    # very first top week → "first ever" only because the
                    # top was born then, NOT a genuine debut.
                    "es_naixement_top": bool(
                        primera and global_first and primera == global_first
                    ),
                    "debut_genui": bool(
                        primera
                        and primera == setmana
                        and (not global_first or setmana != global_first)
                    ),
                },
                "historial": {
                    "setmanes_al_top": h["setmanes"] if h else None,
                    "millor_posicio": h["millor"] if h else None,
                },
            }
        )

    # Group facts for the top 5: origin + collaborators (+ their origin,
    # only when we actually have it) + release date.
    fets_grup = []
    for r in rows[:5]:
        canco = r.canco
        artista = canco.artista if canco else None
        collabs = []
        if canco:
            for col in canco.artistes_col_ordered():
                collabs.append({"nom": col.nom, "origen": _artista_origen(col)})
        fets_grup.append(
            {
                "posicio": r.posicio,
                "canco": canco.nom if canco else "—",
                "artista": artista.nom if artista else "—",
                "origen": _artista_origen(artista),
                "data_llancament": (
                    canco.data_llancament.isoformat()
                    if (canco and canco.data_llancament)
                    else None
                ),
                "collaboradors": collabs,
            }
        )

    # Leader fact: the strongest detected scenario, gated (we surface its
    # freshness_blocked flag so the routine never asserts false novelty).
    fet_lider = None
    try:
        from social.narrative import detect_all

        scenarios = detect_all(TERRITORI, setmana)
        if scenarios:
            s = scenarios[0]
            fet_lider = {
                "code": s.code,
                "severity": s.severity,
                "data": s.data,
                "freshness_blocked": bool(s.data.get("freshness_blocked")),
            }
    except Exception:  # noqa: BLE001
        logger.warning("newsletter_brief: detect_all failed", exc_info=True)

    # Low-confidence scene hint: Last.fm tags for the top 5, in their own
    # section, explicitly NOT a grounded fact.
    tags_top5 = []
    for r in rows[:5]:
        artista = r.canco.artista if r.canco else None
        if artista is None:
            continue
        raw_tags = artista.lastfm_tags or []
        noms = [
            t.get("name") for t in raw_tags if isinstance(t, dict) and t.get("name")
        ]
        if noms:
            tags_top5.append({"artista": artista.nom, "tags": noms[:6]})

    from music.dates import project_week_number

    return {
        "status": "ready",
        "context": {
            "setmana": setmana.isoformat(),
            "edicio": "Global",
            "antiguitat_top_setmanes": _top_age_weeks(),
            "setmana_projecte": project_week_number(saturday),
        },
        "top10": top10,
        "fets_grup_top5": fets_grup,
        "fet_lider": fet_lider,
        "actualitat": _fetch_vilaweb(),
        "baixa_confianca": {
            "_avis": "Senyal sorollós (tags crowd-sourced de Last.fm); NO és un fet verificat.",
            "lastfm_tags_top5": tags_top5,
        },
    }


# Imported late to keep the module import graph shallow at settings load.
from social.narrative.freshness import is_verified_recent_release  # noqa: E402
