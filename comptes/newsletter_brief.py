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
from django.db.models import Count, Min, Prefetch

from music.models import HistorialRevisio
from ranking.models import TopSetmanal

logger = logging.getLogger(__name__)

TIPUS = "top_ppcc"
TERRITORI = "PPCC"

# How many distinct-subject detector scenarios to surface in
# `fets_destacats`. Generous on purpose: the newsletter now writes the
# whole top 40, so the voice gets more candidate stories to pick from.
# `select_slots` already caps at the number of distinct subjects, so a
# week with fewer real beats simply yields a shorter list.
FETS_DESTACATS_K = 8


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


def _localitats_queryset():
    """`localitats` queryset ordered by pk with `municipi` joined. The pk
    ordering makes the prefetched `localitats.all()[0]` identical to the
    legacy `localitats.first()` (which auto-orders by pk), so
    `_artista_origen` reads the prefetch cache instead of issuing one
    query per artista (the 11-40 N+1 risk)."""
    from music.models import ArtistaLocalitat

    return ArtistaLocalitat.objects.select_related("municipi").order_by("pk")


def _artista_origen(artista) -> dict | None:
    """First known origin for an artista: municipi (→ comarca +
    territori) when present, else free-text, else None. Read-only.

    Reads from the prefetched `localitats` cache (see
    `_localitats_queryset`); falls back to a query only if the caller
    did not prefetch. Output is identical to the legacy `.first()`."""
    if artista is None:
        return None
    locs = list(artista.localitats.all())
    if not locs:
        return None
    loc = locs[0]
    if loc.municipi:
        return {
            "municipi": loc.municipi.nom,
            "comarca": loc.municipi.comarca,
            "territori": loc.municipi.territori_id,
        }
    if loc.localitat_manual:
        return {"municipi": None, "comarca": None, "manual": loc.localitat_manual}
    return None


def _collaborators_by_canco(cancons) -> dict[int, list]:
    """`{canco_id: [Artista, ...]}` collaborators, ordered exactly like
    `Canco.artistes_col_ordered()` (by the M2M through-table insertion
    id), but batched: three queries total regardless of how many cançons
    (through rows, the collaborator Artistes, their localitats) instead
    of the per-canco N+1 that `artistes_col_ordered()` does. Read-only."""
    from music.models import Artista, Canco

    canco_ids = [c.pk for c in cancons if c is not None]
    if not canco_ids:
        return {}
    through = Canco.artistes_col.through
    pairs = list(
        through.objects.filter(canco_id__in=canco_ids)
        .order_by("id")
        .values_list("canco_id", "artista_id")
    )
    if not pairs:
        return {}
    collab_ids = {aid for _, aid in pairs}
    artistes = {
        a.id: a
        for a in Artista.objects.filter(pk__in=collab_ids).prefetch_related(
            Prefetch("localitats", queryset=_localitats_queryset())
        )
    }
    out: dict[int, list] = {}
    for cid, aid in pairs:
        a = artistes.get(aid)
        if a is not None:
            out.setdefault(cid, []).append(a)
    return out


def _llengua_signal(noms: list[str]) -> dict[str, int]:
    """Per-name count of `desvincular_canco` rejections — a proxy for
    "this artist has non-Catalan work in our ingest" (a song we unlinked
    as not-Catalan). The code is ~99.7% the legacy `no_catala` + a few
    `no_musica` (migration 0083), so it is a reliable-but-fuzzy signal,
    NOT a verified fact: joined by `artista_nom` (a HistorialRevisio
    snapshot string, not an FK), so homonyms can blur it. ADVISORY: the
    voice reads it to calibrate how much to honour an artist as a
    Catalan-music flag-bearer; absence is weaker evidence than presence."""
    from collections import Counter

    if not noms:
        return {}
    rows = HistorialRevisio.objects.filter(
        decisio="rebutjada", motiu="desvincular_canco", artista_nom__in=noms
    ).values_list("artista_nom", flat=True)
    return dict(Counter(rows))


def _fetch_vilaweb(limit: int = 8) -> list[dict]:
    """The most recent VilaWeb headlines (title, source, date) — up to 8
    by default so the voice can pick by weight, not decoration.
    Best-effort: any network/parse failure yields an empty list, never
    raises (the brief still builds without an actualitat section)."""
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
        .prefetch_related(
            Prefetch("canco__artista__localitats", queryset=_localitats_queryset())
        )
        .order_by("posicio")
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

    # Per-artista top history, one grouped query for every artista in the
    # top (the full 40, not just the top 10 — the extra keys are inert for
    # the top-10 alias, whose values are unchanged).
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
    # Collaborators for every canço in one batched lookup, ordered exactly
    # like `artistes_col_ordered()` — avoids the per-row N+1 across 40 rows.
    collab_map = _collaborators_by_canco([r.canco for r in rows])

    def _top_entry(r) -> dict:
        canco = r.canco
        artista = canco.artista if canco else None
        h = hist.get(artista.id) if artista else None
        primera = h["primera"] if h else None
        cols = collab_map.get(r.canco_id, []) if r.canco_id else []
        return {
            "posicio": r.posicio,
            "canco": canco.nom if canco else "—",
            "artistes": (
                [artista.nom, *[a.nom for a in cols]] if (canco and artista) else ["—"]
            ),
            "moviment": _moviment(r.posicio, prev_pos.get(r.canco_id)),
            "can_call_new": (
                is_verified_recent_release(canco, ref_date=saturday) if canco else False
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

    # `top40` is the full list; `top10` is a byte-identical alias of its
    # first ten (back-compat: the routine + tests still read `top10`).
    top40 = [_top_entry(r) for r in rows]
    top10 = top40[:10]

    # Group facts for the WHOLE top: origin + collaborators (+ their
    # origin, only when we have it) + release date + language-commitment
    # proxy. The language signal is one grouped query over every artista
    # name; the per-name count is identical whatever the IN list, so the
    # top-5 alias is byte-identical to the legacy top-5-only query.
    noms_all = [r.canco.artista.nom for r in rows if r.canco and r.canco.artista]
    lleng = _llengua_signal(noms_all)

    def _fet_grup(r) -> dict:
        canco = r.canco
        artista = canco.artista if canco else None
        cols = collab_map.get(r.canco_id, []) if r.canco_id else []
        collabs = [{"nom": col.nom, "origen": _artista_origen(col)} for col in cols]
        n_desv = lleng.get(artista.nom, 0) if artista else 0
        return {
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
            # Catalan-music rootedness proxy (advisory; see brief.notes).
            "compromis_llengua": {
                "te_obra_no_catala": bool(n_desv),
                "n_cancons_desvinculades": n_desv,
            },
        }

    # `fets_grup` covers all 40; `fets_grup_top5` is the identical alias of
    # its first five (back-compat).
    fets_grup = [_fet_grup(r) for r in rows]
    fets_grup_top5 = fets_grup[:5]

    # Detector layer. `detect_all` runs every detector (some already scan
    # the full 40); `select_slots` greedily picks distinct-subject beats.
    # Both are pure reads: they query TopSetmanal only and NEVER touch the
    # anti-repetition registry (its `mark_used` fires solely on a real
    # publish), so surfacing them keeps build_brief side-effect-free.
    #
    # `fet_lider` = the single strongest scenario (unchanged shape and
    # content). `fets_destacats` = up to K distinct-subject scenarios so
    # the longer newsletter has more candidate stories from across the
    # list; its first element equals `fet_lider`.
    fet_lider = None
    fets_destacats: list[dict] = []
    try:
        from social.narrative import detect_all
        from social.narrative.scenarios import select_slots

        def _as_fet(s) -> dict:
            return {
                "code": s.code,
                "severity": s.severity,
                "data": s.data,
                "freshness_blocked": bool(s.data.get("freshness_blocked")),
            }

        scenarios = detect_all(TERRITORI, setmana)
        if scenarios:
            fet_lider = _as_fet(scenarios[0])
        fets_destacats = [_as_fet(s) for s in select_slots(scenarios, FETS_DESTACATS_K)]
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
        "top40": top40,
        "fets_grup_top5": fets_grup_top5,
        "fets_grup": fets_grup,
        "fet_lider": fet_lider,
        "fets_destacats": fets_destacats,
        "actualitat": _fetch_vilaweb(),
        "baixa_confianca": {
            "_avis": "Senyal sorollós (tags crowd-sourced de Last.fm); NO és un fet verificat.",
            "lastfm_tags_top5": tags_top5,
        },
        "notes": {
            "compromis_llengua": (
                "ADVISORY, no és un fet verificat. `te_obra_no_catala` ve de "
                "rebuigs `desvincular_canco` (≈ cançó no-catalana al nostre "
                "ingest; barreja no_catala + uns pocs no_musica). Join per nom "
                "d'artista (possibles homònims). Presència = té obra no-catalana; "
                "absència = cap cançó no-catalana rebutjada (evidència més feble). "
                "Usa'l per calibrar quant honores l'artista com a abanderat del "
                "català, no per afirmar res categòric."
            )
        },
    }


# Imported late to keep the module import graph shallow at settings load.
from social.narrative.freshness import is_verified_recent_release  # noqa: E402
