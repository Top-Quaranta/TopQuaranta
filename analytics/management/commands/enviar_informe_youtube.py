"""Daily progress report for the YouTube integration — bootstrap phase.

Discovery is rationed to ~90 artists a day by the quota, so the build-out
runs for weeks. This mail is the instrument panel for that stretch: every
morning it answers "what came in yesterday, and how much of the catalogue
can we actually connect?" without anyone opening a shell.

**Temporary by design.** When the bootstrap finishes, delete the cron
line — there is deliberately no config toggle for a thing whose off
switch is one line in `deploy/cron.topquaranta`.

Shares the Setmanari's visual language and its `_kpi.html` partial, and
reuses `_delta` so the movement arrows behave identically (absolute
moves under 1% or on small bases, no phantom "0%").

    python manage.py enviar_informe_youtube [--dry-run] [--html-out PATH]

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime
import logging
import statistics
from collections import defaultdict

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
from music.models import Artista, Canco
from ranking.models import SenyalDiari, SenyalYouTube

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://www.topquaranta.cat/staff/estat"


# Quantes parelles calen abans de fiar-se de la mediana. Per davall de 30
# el rang interquartílic es mou massa d'un dia a l'altre per a dir res;
# per damunt de 100 ja es pot mirar si convergeix. Són llindars de sentit
# comú, no d'estadística formal: la decisió que han d'alimentar és
# editorial, no un contrast d'hipòtesis.
_MOSTRA_INDICI = 30
_MOSTRA_PROU = 100

# Moviment mínim setmanal perquè una cançó entre a la comparativa. Amb
# menys, la divisió amplifica el soroll: 1 escolta i 300 visualitzacions
# dona un factor de 300 que no significa res.
_MOVIMENT_MIN = 5


# Marge al voltant de «fa set dies» per a buscar la foto de referència,
# el mateix que fa `ranking.algorisme` amb SenyalDiari. Exigir la data
# exacta és fràgil: un sol dia de cron perdut buidaria la comparativa
# sencera, i el correu diria «cap cançó comparable» quan el que passa és
# que falta una foto.
_MARGE_DIES = 3


def _increments(model, camp, fi, *, dies=7):
    """`{canco_id: delta setmanal}` reescalat a set dies.

    Agafa la foto més pròxima a `fi - dies` dins de `±_MARGE_DIES` i
    divideix pel nombre real de dies transcorreguts, així una referència
    de fa 5 o de fa 9 dies continua donant una xifra setmanal comparable.
    """
    objectiu = fi - datetime.timedelta(days=dies)
    des_de = objectiu - datetime.timedelta(days=_MARGE_DIES)
    fins_a = objectiu + datetime.timedelta(days=_MARGE_DIES)

    per = defaultdict(dict)
    for s in model.objects.filter(error=False, data__gte=des_de, data__lte=fi).only(
        "canco_id", "data", camp
    ):
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


# Dies enrere que es recalculen per a vore si el factor s'assenta. La
# mida de la mostra sola no ho diu: el 18/08 hi havia 179 parelles —
# «prou» pel llindar— i la mediana havia anat 1 → 23 → 9 en tres dies.
# El que decideix és que pare de moure's.
_DIES_HISTORIAL = 5

# Marge dins del qual dues medianes consecutives compten com a «la
# mateixa». Un ±25 % és ample a posta: buscem que deixe de saltar per
# múltiples, no precisió decimal.
_ESTABLE_MARGE = 0.25


def _ratios(en_finestra_ids, today):
    """`{canco_id: visualitzacions per escolta}` d'una setmana."""
    lfm = _increments(SenyalDiari, "lastfm_playcount", today)
    yt_inc = _increments(SenyalYouTube, "views", today)
    return {
        c: yt_inc[c] / lfm[c]
        for c in set(lfm) & set(yt_inc)
        if c in en_finestra_ids
        and lfm[c] >= _MOVIMENT_MIN
        and yt_inc[c] >= _MOVIMENT_MIN
    }


def _historial(en_finestra_ids, today):
    """La mediana de cada un dels últims dies, i si s'ha assentat.

    Es recalcula en lloc de desar-se: són poques consultes i evita una
    taula nova per a un informe que és temporal.
    """
    files = []
    for enrere in range(_DIES_HISTORIAL - 1, -1, -1):
        dia = today - datetime.timedelta(days=enrere)
        r = sorted(_ratios(en_finestra_ids, dia).values())
        files.append(
            {
                "data": dia,
                "n": len(r),
                "mediana": round(statistics.median(r)) if r else None,
            }
        )
    darreres = [f["mediana"] for f in files[-3:] if f["mediana"]]
    estable = False
    if len(darreres) == 3:
        centre = statistics.median(darreres)
        estable = centre > 0 and all(
            abs(m - centre) / centre <= _ESTABLE_MARGE for m in darreres
        )
    return files, estable


def _per_carril(ratios, en_finestra):
    """La proporció separada segons d'on venen les visualitzacions.

    Un videoclip del canal propi té un ordre de magnitud més de públic
    que una Art Track (mediana de 3.392 visualitzacions contra 92,
    mesurat el 17/08), així que barrejar els dos carrils en una sola
    proporció n'infla la dispersió. Mesurat el 18/08: 4 de mediana amb
    Art Track sol i 36 amb videoclip — nou vegades.

    Ho va assenyalar el Miquel: «té en compte si tenim canal oficial?».
    No ho tenia, i era una variable de primer ordre.
    """
    if len(ratios) < 10:
        return None
    amb_clip = set(
        en_finestra.filter(
            id__in=ratios,
            youtube_videos__isnull=False,
        ).values_list("id", flat=True)
    )
    fora = [r for c, r in ratios.items() if c not in amb_clip]
    dins = [r for c, r in ratios.items() if c in amb_clip]
    if not fora or not dins:
        return None
    return {
        "art_track": {"n": len(fora), "mediana": round(statistics.median(fora))},
        "videoclip": {"n": len(dins), "mediana": round(statistics.median(dins))},
    }


def _per_artista(ratios, en_finestra):
    """Compara la dispersió global amb la de dins de cada artista.

    La hipòtesi que això contrasta: la proporció entre visualitzacions i
    escoltes no és una constant del catàleg sinó una propietat del públic
    de cada artista — qui té públic de YouTube en té a totes les seues
    cançons. Si es confirma, la conversió ha de ser per artista i un
    factor global seria fals per a quasi tothom.
    """
    if len(ratios) < 10:
        return None
    artista_de = dict(en_finestra.filter(id__in=ratios).values_list("id", "artista_id"))
    per_art = defaultdict(list)
    for canco_id, r in ratios.items():
        aid = artista_de.get(canco_id)
        if aid:
            per_art[aid].append(r)
    grups = [v for v in per_art.values() if len(v) >= 3]
    if not grups:
        return None

    def _cv(vals):
        mitjana = statistics.mean(vals)
        return statistics.pstdev(vals) / mitjana if mitjana else 0

    tots = list(ratios.values())
    cv_global = _cv(tots)
    cvs = [_cv(v) for v in grups if statistics.mean(v)]
    cv_artista = statistics.median(cvs) if cvs else 0
    return {
        "cv_global": round(cv_global, 2),
        "cv_artista": round(cv_artista, 2),
        "n_artistes": len(grups),
        # Un terç més estret ja no és soroll: vol dir que el número
        # pertany a l'artista, no al catàleg.
        "millor_per_artista": cv_artista and cv_artista < cv_global * 0.7,
    }


def _comparativa(en_finestra, today):
    """Es poden juntar les dues fonts, i què guanyaríem.

    La pregunta que aquest informe existeix per a respondre des del
    2026-08-17: el descobriment ja ha acabat el catàleg, així que el que
    queda per saber és si el senyal de YouTube es pot convertir a
    escoltes i quantes cançons rescataria.
    """
    lfm = _increments(SenyalDiari, "lastfm_playcount", today)
    yt_inc = _increments(SenyalYouTube, "views", today)
    vius = set(en_finestra.values_list("id", flat=True))
    ratios_avui = _ratios(vius, today)
    historial, estable = _historial(vius, today)

    mou_lfm = {c for c, v in lfm.items() if c in vius and v >= _MOVIMENT_MIN}
    mou_yt = {c for c, v in yt_inc.items() if c in vius and v >= _MOVIMENT_MIN}
    parelles = sorted(yt_inc[c] / lfm[c] for c in (mou_lfm & mou_yt) if lfm[c])

    factor = None
    if parelles:
        n = len(parelles)
        factor = {
            "n": n,
            "mediana": round(statistics.median(parelles)),
            "p25": round(parelles[n // 4]),
            "p75": round(parelles[3 * n // 4]),
            "prou": n >= _MOSTRA_PROU,
            "indici": _MOSTRA_INDICI <= n < _MOSTRA_PROU,
            # La mida de la mostra és condició necessària, no suficient.
            "estable": estable,
        }

    # Quantes cançons tenen ja set dies de fotos: sense això no hi ha
    # increment setmanal possible, i és el que encara està creixent.
    amb_setmana = (
        SenyalYouTube.objects.filter(
            error=False,
            data__gte=today - datetime.timedelta(days=7 + _MARGE_DIES),
            data__lte=today - datetime.timedelta(days=7 - _MARGE_DIES),
        )
        .values("canco_id")
        .distinct()
        .count()
    )
    amb_avui = (
        SenyalYouTube.objects.filter(data=today, error=False)
        .values("canco_id")
        .distinct()
        .count()
    )

    guany = []
    for codi in ("CAT", "VAL", "BAL"):
        ids = set(
            en_finestra.filter(
                Q(artista__territoris__codi=codi)
                | Q(artistes_col__territoris__codi=codi)
            )
            .distinct()
            .values_list("id", flat=True)
        )
        guany.append(
            {
                "codi": codi,
                "lastfm": len(ids & mou_lfm),
                "noves": len(ids & mou_yt - mou_lfm),
            }
        )

    return {
        "comparables": len(mou_lfm & mou_yt),
        "mou_lfm": len(mou_lfm),
        "mou_yt": len(mou_yt),
        "noves": len(mou_yt - mou_lfm),
        "factor": factor,
        "amb_setmana": amb_setmana,
        "amb_avui": amb_avui,
        "pct_setmana": round(amb_setmana / amb_avui * 100) if amb_avui else 0,
        "guany": guany,
        "moviment_min": _MOVIMENT_MIN,
        "historial": historial,
        "per_artista": _per_artista(ratios_avui, en_finestra),
        "per_carril": _per_carril(ratios_avui, en_finestra),
    }


def _cobertura(qs_cancons) -> dict:
    total = qs_cancons.count()
    fetes = qs_cancons.exclude(youtube_video_id="").count()
    return {
        "total": total,
        "fetes": fetes,
        "pct": round(fetes / total * 100) if total else 0,
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
        },
        "aparellament": {
            "total": _delta(total_ap, total_ap - ap_avui),
            "total_n": total_ap,
            "elegibles": en_finestra.count(),
            "territoris": per_territori,
        },
        "punt_cec": punt_cec,
        "comparativa": _comparativa(en_finestra, today),
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
    lines = [
        f"YOUTUBE · INFORME DIARI · {ctx['avui']}",
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
