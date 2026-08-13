"""Selector + avaluador de les sondes «la cançó del dia».

# Spec: docs/architecture/social-stories.md

Implements the §5ter spec of the 2026-08-13 investigation: an
eligibility WHERE, a three-tier priority ladder (mai contactat →
re-sonda 12m → invitació caducada 90d) and the diversity machinery
(soft territorial quota, genre round-robin, recent-activity boost,
deterministic tiebreak). The reaction detector is REACH-ONLY:
`avaluar_sondes_pendents` flags a probe whose reach is an outlier over
the rolling probe baseline (mediana + 3·MAD) — replies is zeroed by
Meta for EU accounts and shares/impressions don't exist for stories.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import statistics
from dataclasses import dataclass

from django.db.models import Max

from music.models import Artista, Canco
from ranking.models import TopSetmanal

from .models import InvitacioColaboracioIG, SondaStoryIG

logger = logging.getLogger(__name__)

COOLDOWN_RESONDA_DIES = 365
COOLDOWN_CADUCADA_DIES = 90
LLANCAMENT_RECENT_DIES = 90
# 1 de cada QUOTA_NO_CAT sondes reserva el torn per a un artista no-CAT,
# perquè els pocs VAL/BAL no s'esgoten el primer mes (§5.3).
QUOTA_NO_CAT = 6
# Outlier rule: reach > mediana + OUTLIER_K * MAD over the last
# BASELINE_N evaluated probes; below MIN_BASELINE prior probes we
# never flag (cold start — no baseline to trust).
BASELINE_N = 30
MIN_BASELINE = 5
OUTLIER_K = 3.0


@dataclass
class Candidat:
    artista: Artista
    esglao: int
    ultima_sonda: datetime.date | None
    ultima_caducada: datetime.date | None


def _mai_top_ids(artista_ids: list[int]) -> set[int]:
    """Subset of `artista_ids` with NO main-artist song ever ranked."""
    topats = set(
        TopSetmanal.objects.filter(canco__artista_id__in=artista_ids)
        .values_list("canco__artista_id", flat=True)
        .distinct()
    )
    return set(artista_ids) - topats


def elegibles(avui: datetime.date) -> list[Candidat]:
    """The §5ter WHERE, materialised as `Candidat`s with their tier."""
    base = Artista.objects.filter(aprovat=True).exclude(instagram_url="")
    ids = list(base.values_list("id", flat=True))
    if not ids:
        return []

    inv = InvitacioColaboracioIG.objects.filter(artista_id__in=ids)
    bloquejats = set(
        inv.filter(
            estat__in=[
                InvitacioColaboracioIG.ESTAT_PENDENT,
                InvitacioColaboracioIG.ESTAT_ACCEPTADA,
                InvitacioColaboracioIG.ESTAT_REBUTJADA,
            ]
        ).values_list("artista_id", flat=True)
    )
    caducades = dict(
        inv.filter(estat=InvitacioColaboracioIG.ESTAT_CADUCADA)
        .values("artista_id")
        .annotate(m=Max("data_resolucio"))
        .values_list("artista_id", "m")
    )

    sondes = SondaStoryIG.objects.filter(artista_id__in=ids)
    receptius = set(
        sondes.filter(reaccio_auto=True).values_list("artista_id", flat=True)
    )
    ultima_sonda = dict(
        sondes.values("artista_id")
        .annotate(m=Max("data"))
        .values_list("artista_id", "m")
    )

    mai_top = _mai_top_ids(ids)

    # Artists with at least one publishable never-topped song.
    amb_material = set(
        Canco.objects.filter(
            artista_id__in=ids,
            verificada=True,
            activa=True,
            rankings__isnull=True,
            album__isnull=False,
            album__deezer_id__isnull=False,
        ).values_list("artista_id", flat=True)
    )

    out: list[Candidat] = []
    for a in base.filter(id__in=amb_material).prefetch_related("territoris"):
        if a.id in bloquejats or a.id in receptius:
            continue
        s_data = ultima_sonda.get(a.id)
        if s_data and (avui - s_data).days < COOLDOWN_RESONDA_DIES:
            continue
        c_dt = caducades.get(a.id)
        c_data = c_dt.date() if c_dt else None
        if c_data:
            if (avui - c_data).days < COOLDOWN_CADUCADA_DIES:
                continue
            esglao = 3
        elif a.id not in mai_top:
            continue  # topats sense caducada: fora del funnel (§5quater)
        elif s_data:
            esglao = 2
        else:
            esglao = 1
        out.append(Candidat(a, esglao, s_data, c_data))
    return out


def _torn_no_cat() -> bool:
    """Every QUOTA_NO_CAT-th probe reserves the turn for non-CAT."""
    return SondaStoryIG.objects.count() % QUOTA_NO_CAT == 0


def _es_no_cat(a: Artista) -> bool:
    codis = {t.codi for t in a.territoris.all()}
    return bool(codis) and "CAT" not in codis


def _ultima_sonda_per_genere() -> dict[str, datetime.date]:
    return dict(
        SondaStoryIG.objects.values("artista__genere")
        .annotate(m=Max("data"))
        .values_list("artista__genere", "m")
    )


def _te_llancament_since(a: Artista, since: datetime.date) -> bool:
    return a.albums.filter(
        descartat=False, data_llancament__isnull=False, data_llancament__gte=since
    ).exists()


def tria_artista(avui: datetime.date, franja: str) -> Candidat | None:
    """The §5ter ORDER BY ... LIMIT 1."""
    cands = elegibles(avui)
    if not cands:
        return None
    torn_no_cat = _torn_no_cat()
    per_genere = _ultima_sonda_per_genere()
    recent_tall = avui - datetime.timedelta(days=LLANCAMENT_RECENT_DIES)
    epoca = datetime.date(1970, 1, 1)

    def _key(c: Candidat):
        genere_data = per_genere.get(c.artista.genere or "")
        contacte = max(filter(None, [c.ultima_sonda, c.ultima_caducada]), default=None)
        return (
            c.esglao,
            # quota: al torn no-CAT, els no-CAT primer (False < True).
            not (torn_no_cat and _es_no_cat(c.artista)),
            # round-robin de gènere: mai sondejat primer, després el
            # que fa més temps (date asc; None → epoch = primer).
            genere_data or epoca,
            not _te_llancament_since(c.artista, recent_tall),
            not (contacte and _te_llancament_since(c.artista, contacte)),
            contacte or epoca,
            hashlib.md5(f"{avui}{franja}{c.artista.id}".encode()).hexdigest(),
        )

    return min(cands, key=_key)


def tria_canco(cand: Candidat, avui: datetime.date) -> Canco | None:
    """The song-level WHERE + ORDER BY of §5ter."""
    ja_sondejades = set(
        SondaStoryIG.objects.filter(
            artista=cand.artista, canco__isnull=False
        ).values_list("canco_id", flat=True)
    )
    qs = (
        Canco.objects.filter(
            artista=cand.artista,
            verificada=True,
            activa=True,
            rankings__isnull=True,
            album__isnull=False,
            album__deezer_id__isnull=False,
        )
        .exclude(id__in=ja_sondejades)
        .select_related("album")
        .distinct()
    )
    cancons = list(qs)
    if not cancons:
        return None
    contacte = max(
        filter(None, [cand.ultima_sonda, cand.ultima_caducada]), default=None
    )
    playcounts = {
        c.id: (
            c.senyals.order_by("-data")
            .values_list("lastfm_playcount", flat=True)
            .first()
        )
        for c in cancons
    }
    epoca = datetime.date(1970, 1, 1)

    def _key(c: Canco):
        llanc = c.album.data_llancament if c.album else None
        return (
            not (cand.esglao in (2, 3) and contacte and llanc and llanc > contacte),
            -(playcounts.get(c.id) or 0),
            -(llanc or epoca).toordinal(),
        )

    return min(cancons, key=_key)


def avaluar_sondes_pendents(avui: datetime.date) -> int:
    """Snapshot reach + flag outliers for probes past their window.

    Reads `MetricaSocialPost` (already collected nightly) — no API
    calls, so timing is flexible. Returns the number evaluated.
    """
    from analytics.models import MetricaSocialPost

    tall = avui - datetime.timedelta(days=SondaStoryIG.REACCIO_FINESTRA_DIES)
    pendents = SondaStoryIG.objects.filter(reaccio_auto__isnull=True, data__lte=tall)
    n = 0
    for s in pendents:
        reach = (
            MetricaSocialPost.objects.filter(
                socialpost=s.socialpost, reach__gt=0
            ).aggregate(m=Max("reach"))["m"]
            if s.socialpost_id
            else None
        )
        previes = list(
            SondaStoryIG.objects.filter(
                reaccio_auto__isnull=False, reach__isnull=False, data__lt=s.data
            )
            .order_by("-data")
            .values_list("reach", flat=True)[:BASELINE_N]
        )
        s.reach = reach or 0
        if len(previes) >= MIN_BASELINE:
            mediana = statistics.median(previes)
            mad = statistics.median(abs(x - mediana) for x in previes) or 1.0
            s.baseline_mediana = mediana
            s.baseline_mad = mad
            s.reaccio_auto = s.reach > mediana + OUTLIER_K * mad
        else:
            # Cold start: record without flagging (no baseline to trust).
            s.reaccio_auto = False
        s.save(
            update_fields=["reach", "baseline_mediana", "baseline_mad", "reaccio_auto"]
        )
        if s.reaccio_auto:
            logger.info(
                "sonda REACTIVA: %s (reach=%s vs mediana=%s mad=%s)",
                s.artista,
                s.reach,
                s.baseline_mediana,
                s.baseline_mad,
            )
        n += 1
    return n
