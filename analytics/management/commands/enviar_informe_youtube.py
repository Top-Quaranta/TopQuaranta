"""Daily report for the YouTube integration — active phase.

YouTube counts in the top since 2026-08-26, so the bootstrap questions
this mail was built around — can the two signals be merged, what is the
conversion factor — are answered and gone: the weight is editorial
(`youtube_pes_escolta`), not measured. What the mail answers now, every
morning: what does YouTube decide in today's top, what manual work is
left (the 10 recerques), and is the signal still flowing.

**Still temporary.** The off switch is one line in
`deploy/cron.topquaranta` — delete it when the recerques queue drains
and the mail is reduced to status nobody reads.

Shares the Setmanari's visual language and its `_kpi.html` partial, and
reuses `_delta` so the movement arrows behave identically (absolute
moves under 1% or on small bases, no phantom "0%").

    python manage.py enviar_informe_youtube [--dry-run] [--html-out PATH]

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime
import logging
from collections import defaultdict
from urllib.parse import quote_plus

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils import timezone

from analytics.management.commands.enviar_digest_setmanal import _delta, _mov
from ingesta.clients import youtube as yt
from ingesta.management.commands.descobrir_youtube import DEFAULT_BUDGET
from music.constants import DIES_CADUCITAT
from music.models import Artista, Canco, CancoYouTubeVideo
from ranking.models import SenyalDiari, SenyalYouTube

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://www.topquaranta.cat/staff/estat"


# Marge al voltant de «fa set dies» per a buscar la foto de referència,
# el mateix que fa `ranking.algorisme` amb SenyalDiari. Exigir la data
# exacta és fràgil: un sol dia de cron perdut buidaria la comparació
# sencera, i el correu diria «cap cançó» quan el que passa és que falta
# una foto.
_MARGE_DIES = 3


def _increments(model, camp, fi, *, dies=7):
    """`{canco_id: delta setmanal}` reescalat a set dies.

    Agafa la foto més pròxima a `fi - dies` dins de `±_MARGE_DIES` i
    divideix pel nombre real de dies transcorreguts, així una referència
    de fa 5 o de fa 9 dies continua donant una xifra setmanal comparable.

    Només serveix la sèrie de Last.fm: la de YouTube demana el detall per
    vídeo i viu a `ranking.senyal_youtube.visualitzacions_setmanals`, que
    és qui llig `SenyalYouTube` per al rànquing i per a este correu — dues
    implementacions del mateix delta és com es desvien.
    """
    objectiu = fi - datetime.timedelta(days=dies)
    des_de = objectiu - datetime.timedelta(days=_MARGE_DIES)
    fins_a = objectiu + datetime.timedelta(days=_MARGE_DIES)

    per = defaultdict(dict)
    for s in model.objects.filter(error=False, data__gte=des_de, data__lte=fi):
        v = getattr(s, camp)
        if v is not None:
            per[s.canco_id][s.data] = v

    out = {}
    for canco_id, fotos in per.items():
        if fi not in fotos:
            continue
        candidates = [d for d in fotos if des_de <= d <= fins_a]
        if not candidates:
            continue
        base = min(candidates, key=lambda d: abs((d - objectiu).days))
        span = (fi - base).days
        if span <= 0 or fotos[fi] < fotos[base]:
            continue
        out[canco_id] = (fotos[fi] - fotos[base]) * dies / span
    return out


def _efecte_al_top(today):
    """Què decideix YouTube al top d'avui: quantes files i qui les mana.

    Activa des del 2026-08-26, la pregunta ja no és «es poden juntar?»
    sinó si la segona font continua fent el que es va decidir que fera:
    omplir els buits que Last.fm no veu sense reordenar el que sí que
    veu. Es calcula amb la configuració real, així que si el Miquel mou
    el pes o el terra al panell, l'endemà el correu li conta l'efecte
    del número nou.

    Recalcula sense tocar res: llegeix els mateixos senyals que el
    rànquing i compara el conjunt de candidates amb i sense la segona
    font.
    """
    from ranking import senyal_youtube
    from ranking.models import ConfiguracioGlobal
    from ranking.senyal_youtube import visualitzacions_setmanals

    cfg = ConfiguracioGlobal.load()
    pes = int(getattr(cfg, "youtube_pes_escolta", 1000) or 1000)
    terra_lfm = int(cfg.min_escoltes_top or 0)
    terra_comb = int(getattr(cfg, "min_senyal_combinat", 200) or 0)

    vives = Canco.objects.filter(
        verificada=True,
        activa=True,
        data_llancament__gte=today - datetime.timedelta(days=DIES_CADUCITAT),
    )
    lfm = _increments(SenyalDiari, "lastfm_playcount", today)
    yt = visualitzacions_setmanals(list(vives.values_list("id", flat=True)), today)

    files = []
    for codi in ("CAT", "VAL", "BAL", "ALT"):
        ids = set(
            vives.filter(
                Q(artista__territoris__codi=codi)
                | Q(artistes_col__territoris__codi=codi)
            )
            .distinct()
            .values_list("id", flat=True)
        )
        ara = sorted(
            (c for c in ids if lfm.get(c, 0) >= terra_lfm),
            key=lambda c: -lfm.get(c, 0),
        )[:40]
        combinat = sorted(
            (c for c in ids if lfm.get(c, 0) * pes + yt.get(c, 0) >= terra_comb),
            key=lambda c: -(lfm.get(c, 0) * pes + yt.get(c, 0)),
        )[:40]
        # Per què entra cada fila nova. Sense separar-ho, «+11 noves»
        # es llig com «YouTube n'ha portat onze», i pot no haver-ne
        # portat cap: el terra combinat també deixa entrar cançons que
        # el terra en escoltes deixava fora. Són tres causes distintes
        # i excloents, i només la primera és mèrit de la segona font.
        noves = set(combinat) - set(ara)
        per_yt = sum(1 for c in noves if lfm.get(c, 0) * pes < terra_comb)
        per_terra = sum(
            1
            for c in noves
            if lfm.get(c, 0) * pes >= terra_comb and lfm.get(c, 0) < terra_lfm
        )
        files.append(
            {
                "codi": codi,
                "ara": len(ara),
                "amb_yt": len(combinat),
                # Files que entren al top 40 i abans no hi eren.
                "noves": len(noves),
                # …que no hi entrarien sense les visualitzacions.
                "noves_yt": per_yt,
                # …que hi entren perquè el terra combinat és més baix.
                "noves_terra": per_terra,
                # …i la resta, que ja passaven els dos terres i pugen
                # per reordenació.
                "noves_ordre": len(noves) - per_yt - per_terra,
                # …i en quantes mana YouTube per damunt de Last.fm.
                "mana_yt": sum(
                    1 for c in combinat if yt.get(c, 0) > lfm.get(c, 0) * pes
                ),
            }
        )
    # `actiu` hauria de ser sempre cert des del 26/08: si un dia no ho
    # és, la història per vídeo s'ha perdut i el correu ho ha de dir en
    # roig, no amagar el bloc.
    dies_minims = int(getattr(cfg, "youtube_dies_minims", 7) or 0)
    return {
        "actiu": senyal_youtube.actiu(today, dies_minims),
        "pes": pes,
        "terra": terra_comb,
        "territoris": files,
    }


def _sense_video(qs):
    """Cançons que el mesurador no pot fotografiar: cap carril, cap dels dos.

    `obtenir_senyal_youtube` fotografia una cançó si té Art Track **o**
    vídeo del canal propi. Comptar només l'Art Track ací donava una
    cobertura pessimista i, pitjor, ficava a la llista de recerques
    cançons que ja s'estan mesurant per l'altre carril.
    """
    return qs.filter(youtube_video_id="").exclude(
        pk__in=CancoYouTubeVideo.objects.values("canco_id")
    )


def _cobertura(qs_cancons) -> dict:
    total = qs_cancons.count()
    fetes = total - _sense_video(qs_cancons).count()
    return {
        "total": total,
        "fetes": fetes,
        "pct": round(fetes / total * 100) if total else 0,
    }


# Quantes recerques caben en un matí. El límit no és tècnic —ací el
# sistema no fa res— sinó humà: una llista de quaranta tasques no es fa,
# s'ignora, i el correu passa a ser soroll.
_ACCIONS_DIA = 10

# Repartiment per tipus. Sense reserva, les cançons cegues ocuparien els
# deu llocs cada matí durant setmanes i la cua de canals no avançaria
# mai. Els números no són sagrats; el que han de garantir és que cada
# dia isca alguna cosa de cada tipus mentre en quede.
_QUOTA_INVISIBLES = 3
_QUOTA_CEGUES = 5
_QUOTA_CANALS = 3


def _cerca_yt(*parts) -> str:
    """L'enllaç de cerca a YouTube ja escrit, perquè siga un clic i no tres."""
    return "https://www.youtube.com/results?search_query=" + quote_plus(
        " ".join(p for p in parts if p)
    )


def _accions(en_finestra, cegues, n=_ACCIONS_DIA):
    """Les recerques del dia: què buscar, per què, i on es desa la resposta.

    Tot el que hi ha ací és feina que **només** pot fer una persona: el
    codi no endevina mai un canal (el cas «Malalts» torna un canal de
    pàdel) i no aparella un vídeo que no case pel títol. La resta de
    l'informe conta com va la part automàtica; això conta la manual.

    L'ordre no és una opinió, són tres graus de ceguesa:

    1. **Artista sense cap canal** — ni Topic ni propi, i ningú ho ha
       mirat. Cap cançó seua es pot mesurar per YouTube. Un sol canal
       en desbloqueja totes de colp.
    2. **Cançó del punt cec sense vídeo** — Last.fm no la veu i YouTube
       tampoc: avui no pot entrar al top per cap via. Enganxar un
       enllaç la connecta eixa mateixa nit.
    3. **Canal propi de l'artista** — ja el mesurem per l'Art Track,
       però el videoclip té molt més públic. Primer els que ja surten
       al top, que és on el senyal que falta pesa més.

    Cada fila porta la cerca escrita i el lloc on desar-ho. La llista
    es buida sola: una cançó amb vídeo o marcada «revisada» no torna, i
    un artista amb canal o revisat tampoc. Mentre no es toquen,
    reapareixen — segueixen sent la prioritat.
    """
    accions: list[dict] = []
    sense_video = _sense_video(en_finestra).filter(youtube_revisat=False)
    cegues_ids = set(
        _sense_video(cegues).filter(youtube_revisat=False).values_list("id", flat=True)
    )

    # ── 1. Artistes totalment invisibles ────────────────────────────
    # Només aprovats. Una cançó pot ser vàlida amb l'artista principal
    # encara pendent —«Hores Extres» de Sr. À hi és pels col·laboradors
    # aprovats—, però demanar-ne el canal és feina morta: la cua de
    # `/staff/artistes/sense-youtube` filtra `aprovat=1` i l'artista no
    # hi apareix. Primer es decideix l'artista, després el canal.
    invisibles = (
        Artista.objects.public()
        .filter(
            youtube_channel_id="",
            youtube_canal_revisat=False,
            cancons__in=en_finestra,
        )
        .annotate(n_vives=Count("cancons", distinct=True))
        .order_by("-n_vives", "nom")
        .distinct()[:_QUOTA_INVISIBLES]
    )
    for a in invisibles:
        accions.append(
            {
                "tipus": "artista",
                "titol": a.nom,
                "sub": "cap canal de YouTube",
                "motiu": (
                    f"{a.n_vives} cançó que ara mateix no es pot mesurar"
                    if a.n_vives == 1
                    else f"{a.n_vives} cançons que ara mateix no es poden mesurar"
                ),
                "cerca": _cerca_yt(a.nom),
                "on": "/staff/artistes/sense-youtube",
            }
        )

    # ── 2. Cançons del punt cec sense cap carril ────────────────────
    # Les més recents primer: una novetat sense senyal és una absència
    # que es nota esta setmana, no d'ací a un any.
    cegues_files = (
        sense_video.filter(id__in=cegues_ids)
        .select_related("artista")
        .order_by("-data_llancament", "pk")[:_QUOTA_CEGUES]
    )
    for c in cegues_files:
        accions.append(
            {
                "tipus": "canco",
                "titol": c.nom,
                "sub": c.artista.nom if c.artista else "",
                "motiu": "Last.fm no la veu i no té vídeo: avui no pot "
                "entrar al top per cap via",
                "cerca": _cerca_yt(c.artista.nom if c.artista else "", c.nom),
                "on": f"/staff/cancons/{c.pk}",
            }
        )

    # ── 3. Canal propi: primer els que ja surten al top ─────────────
    # Ordenat per aparicions al top, **no filtrat** per elles. El
    # 2026-08-19 els 172 artistes que han estat al top ja tenien el
    # canal revisat —la cua de `/staff/artistes/sense-youtube` s'ordena
    # per `-n_top` i s'havia treballat per dalt—, així que exigir
    # `n_top > 0` deixava aquest calaix mort per sempre i el correu no
    # tornava a demanar un canal propi mai més. Amb l'ordre sol, quan
    # n'hi ha de destacats ixen davant, i quan no, ix el que més cançons
    # vives té.
    canals = (
        Artista.objects.public()
        .filter(youtube_canal_revisat=False, cancons__in=en_finestra)
        .exclude(youtube_channel_id="")
        .annotate(
            n_top=Count("cancons__rankings", distinct=True),
            n_vives=Count("cancons", distinct=True),
        )
        .order_by("-n_top", "-n_vives", "nom")
        .distinct()[:_QUOTA_CANALS]
    )
    for a in canals:
        accions.append(
            {
                "tipus": "artista",
                "titol": a.nom,
                "sub": "sense canal propi revisat",
                "motiu": (
                    f"{a.n_top} aparicions al top · només el mesurem per "
                    "l'Art Track, i el videoclip té molt més públic"
                    if a.n_top
                    else f"{a.n_vives} cançons mesurades només per l'Art "
                    "Track; el videoclip té molt més públic"
                ),
                "cerca": _cerca_yt(a.nom),
                "on": "/staff/artistes/sense-youtube",
            }
        )

    # ── Farciment: la resta de cançons sense vídeo ──────────────────
    # Quan els calaixos anteriors no omplin els deu llocs, la llista es
    # completa amb el que queda sense connectar, del més recent al més
    # vell. **Sense excloure les cegues**: si totes les pendents ho són,
    # la quota de dalt ja els ha donat prioritat i la resta continua sent
    # la millor feina que hi ha. Excloure-les ací deixava el correu amb
    # cinc files i dos-centes cançons pendents.
    if len(accions) < n:
        llistades = {a["on"] for a in accions}
        resta = sense_video.select_related("artista").order_by(
            "-data_llancament", "pk"
        )[: n * 2]
        for c in resta:
            if len(accions) >= n:
                break
            if f"/staff/cancons/{c.pk}" in llistades:
                continue
            accions.append(
                {
                    "tipus": "canco",
                    "titol": c.nom,
                    "sub": c.artista.nom if c.artista else "",
                    "motiu": (
                        "Last.fm no la veu i no té vídeo"
                        if c.pk in cegues_ids
                        else "sense vídeo: només la veu Last.fm"
                    ),
                    "cerca": _cerca_yt(c.artista.nom if c.artista else "", c.nom),
                    "on": f"/staff/cancons/{c.pk}",
                }
            )

    return {
        "files": accions[:n],
        # El que queda per fer de cada tipus, perquè deu files no diguen
        # «ja estem» quan en queden dos-cents.
        "resten_cancons": sense_video.count(),
        "resten_artistes": Artista.objects.public()
        .filter(youtube_canal_revisat=False, cancons__in=en_finestra)
        .distinct()
        .count(),
    }


def build_context(today: datetime.date) -> dict:
    ahir = today - datetime.timedelta(days=1)
    cutoff = today - datetime.timedelta(days=DIES_CADUCITAT)
    en_finestra = Canco.objects.filter(
        verificada=True, activa=True, data_llancament__gte=cutoff
    )

    # ── Descobriment ────────────────────────────────────────────────
    artistes = Artista.objects.filter(cancons__in=en_finestra).distinct()
    tot_art = artistes.count()
    amb_canal = artistes.exclude(youtube_channel_id="").count()
    provats = artistes.filter(youtube_checked_at__isnull=False).count()
    sense_canal = provats - amb_canal
    ahir_provats = artistes.filter(youtube_checked_at__date=ahir).count()
    # Canals trobats AVUI: l'única base de comparació honesta que tenim,
    # perquè `youtube_checked_at` sí que porta data.
    canals_avui = (
        artistes.exclude(youtube_channel_id="")
        .filter(youtube_checked_at__date=today)
        .count()
    )

    # ETA. Els primers dies el ritme observat és mentida: el dia u només
    # ha corregut una execució (i potser amb pressupost retallat), així que
    # dividir per la mitjana de 7 dies dona «145 dies» quan la capacitat
    # real són ~90 artistes/dia. Fins que hi haja història de debò,
    # projectem amb la capacitat del pressupost i ho diem.
    fa7 = today - datetime.timedelta(days=7)
    dies_amb_dades = (
        artistes.filter(youtube_checked_at__date__gte=fa7)
        .dates("youtube_checked_at", "day")
        .count()
    )
    queden = tot_art - provats
    capacitat = DEFAULT_BUDGET // yt.COST_SEARCH
    if dies_amb_dades >= 3:
        ritme = artistes.filter(youtube_checked_at__date__gte=fa7).count() / 7
        eta_base = "ritme actual"
    else:
        ritme = capacitat
        eta_base = "capacitat diària"
    # max(1, …): si el que queda cap en una execució, «~1 dia» informa
    # més que un 0 que el template tracta com a «sense ETA» i amaga.
    eta = max(1, round(queden / ritme)) if ritme >= 1 and queden > 0 else None

    # ── Aparellament ────────────────────────────────────────────────
    per_territori = []
    for codi in ("CAT", "VAL", "BAL"):
        qs = en_finestra.filter(
            Q(artista__territoris__codi=codi) | Q(artistes_col__territoris__codi=codi)
        ).distinct()
        per_territori.append({"codi": codi, **_cobertura(qs)})

    # ── El punt cec: cançons sense senyal de Last.fm ─────────────────
    amb_lastfm = set(
        SenyalDiari.objects.filter(
            canco__in=en_finestra,
            data__gte=today - datetime.timedelta(days=14),
            error=False,
            lastfm_playcount__isnull=False,
        ).values_list("canco_id", flat=True)
    )
    cegues = en_finestra.exclude(id__in=amb_lastfm)
    punt_cec = _cobertura(cegues)

    # ── Senyal recollit ─────────────────────────────────────────────
    snap_avui = SenyalYouTube.objects.filter(data=today)
    # Amb quantes n'hi ha prou per a produir un increment setmanal: cal
    # una línia base d'almenys 4 dies enrere, igual que a Last.fm.
    base = today - datetime.timedelta(days=4)
    amb_historial = (
        SenyalYouTube.objects.filter(data__lte=base, error=False)
        .values("canco_id")
        .distinct()
        .count()
    )

    total_ap = en_finestra.exclude(youtube_video_id="").count()
    ap_avui = en_finestra.filter(youtube_matched_at__date=today).count()
    return {
        "subject": f"[TopQuaranta] YouTube · dia {today:%d/%m} · "
        f"{total_ap} cançons connectades",
        "avui": today,
        "descobriment": {
            "total": tot_art,
            "amb_canal": _delta(amb_canal, amb_canal - canals_avui),
            "amb_canal_n": amb_canal,
            "sense_canal": sense_canal,
            "provats": provats,
            "pct": round(amb_canal / tot_art * 100) if tot_art else 0,
            "queden": queden,
            "eta_dies": eta,
            "eta_base": eta_base,
            "ahir": ahir_provats,
            # El descobriment automàtic ja ha passat per tot el catàleg.
            # Amb la cua a zero i cap prova ahir, el bloc només repetiria
            # els mateixos números cada matí: el template l'amaga i el
            # que queda per fer passa a ser feina de mà (vegeu `accions`).
            "tancat": queden == 0 and ahir_provats == 0,
        },
        "aparellament": {
            "total": _delta(total_ap, total_ap - ap_avui),
            "total_n": total_ap,
            "elegibles": en_finestra.count(),
            "territoris": per_territori,
        },
        "punt_cec": punt_cec,
        "accions": _accions(en_finestra, cegues),
        "efecte_top": _efecte_al_top(today),
        "senyal": {
            "avui": snap_avui.filter(error=False).count(),
            "errors": snap_avui.filter(error=True).count(),
            "amb_historial": amb_historial,
            "cost_estimat": max(1, (total_ap + 49) // 50),
            "quota": yt.DAILY_QUOTA,
        },
        "incidencies": [
            {
                "label": s.canco.nom if s.canco else "(cançó esborrada)",
                "msg": s.error_msg[:120],
            }
            for s in snap_avui.filter(error=True).select_related("canco")[:8]
        ],
        "dashboard_url": DASHBOARD_URL,
        "site_url": getattr(settings, "SITE_URL", "https://www.topquaranta.cat").rstrip(
            "/"
        ),
    }


def render_text(ctx: dict) -> str:
    d = ctx["descobriment"]
    a = ctx["aparellament"]
    s = ctx["senyal"]
    ac = ctx["accions"]
    e = ctx["efecte_top"]
    lines = [
        f"YOUTUBE · INFORME DIARI · {ctx['avui']}",
        "",
        f"EL TOP AMB YOUTUBE · {'actiu' if e['actiu'] else 'INACTIU!'} · "
        f"pes {e['pes']} · terra {e['terra']}",
    ]
    lines += [
        f"  {t['codi']:<5} {t['ara']}/40 → {t['amb_yt']}/40 · "
        f"+{t['noves']} noves ({t['noves_yt']} per YT, {t['noves_terra']} "
        f"pel terra, {t['noves_ordre']} per ordre) · mana YT: {t['mana_yt']}"
        for t in e["territoris"]
    ]
    lines += [
        "",
        f"LES {len(ac['files'])} RECERQUES D'AVUI",
    ]
    for i, f in enumerate(ac["files"], 1):
        lines += [
            f"  {i:>2}. {f['titol']}" + (f" — {f['sub']}" if f["sub"] else ""),
            f"      {f['motiu']}",
            f"      cerca: {f['cerca']}",
            f"      desa-ho a: {ctx['site_url']}{f['on']}",
        ]
    lines += [
        f"  Queden {ac['resten_cancons']} cançons sense vídeo i "
        f"{ac['resten_artistes']} artistes sense canal revisat.",
        "",
        "DESCOBRIMENT",
        f"  Artistes amb canal Topic  {d['amb_canal_n']}/{d['total']} ({d['pct']}%)"
        f"  {_mov(d['amb_canal'])}",
        f"  Provats sense trobar-ne   {d['sense_canal']}",
        f"  Ahir se'n van provar      {d['ahir']}",
        f"  Queden                    {d['queden']}"
        + (f"  (~{d['eta_dies']} dies · {d['eta_base']})" if d["eta_dies"] else ""),
        "",
        "APARELLAMENT",
        f"  Cançons connectades       {a['total_n']}/{a['elegibles']}",
    ]
    lines += [
        f"    {t['codi']:<5} {t['fetes']:>4}/{t['total']:<5} ({t['pct']}%)"
        for t in a["territoris"]
    ]
    lines += [
        "",
        "PUNT CEC (cançons sense senyal de Last.fm)",
        f"  Ja tenen YouTube          {ctx['punt_cec']['fetes']}/"
        f"{ctx['punt_cec']['total']} ({ctx['punt_cec']['pct']}%)",
        "",
        "SENYAL",
        f"  Snapshots d'avui          {s['avui']} correctes, {s['errors']} amb error",
        f"  Ja poden puntuar          {s['amb_historial']}"
        "  (calen 4 dies de línia base)",
        f"  Cost                      ~{s['cost_estimat']} unitats de {s['quota']}",
    ]
    if ctx["incidencies"]:
        lines += ["", "INCIDÈNCIES"]
        lines += [f"  {i['label']} — {i['msg']}" for i in ctx["incidencies"]]
    lines += ["", f"Dashboard: {ctx['dashboard_url']}"]
    return "\n".join(lines)


class Command(BaseCommand):
    help = "Envia l'informe diari de progrés de la integració amb YouTube."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--html-out", metavar="PATH")

    def handle(self, *args, **opts) -> None:
        ctx = build_context(timezone.localdate())
        text_body = render_text(ctx)
        html_body = render_to_string("analytics/informe_youtube.html", ctx)

        if opts.get("html_out"):
            with open(opts["html_out"], "w", encoding="utf-8") as fh:
                fh.write(html_body)
            self.stdout.write(self.style.SUCCESS(f"HTML escrit a {opts['html_out']}"))
            return

        if opts.get("dry_run"):
            self.stdout.write(ctx["subject"])
            self.stdout.write("=" * 60)
            self.stdout.write(text_body)
            return

        recipients = [a if isinstance(a, str) else a[1] for a in settings.ADMINS]
        if not recipients:
            self.stdout.write(self.style.WARNING("Cap ADMIN configurat; no s'envia."))
            return

        msg = EmailMultiAlternatives(
            subject=ctx["subject"],
            body=text_body,
            from_email=settings.SERVER_EMAIL,
            to=recipients,
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        self.stdout.write(self.style.SUCCESS(f"Informe enviat: {ctx['subject']}"))
