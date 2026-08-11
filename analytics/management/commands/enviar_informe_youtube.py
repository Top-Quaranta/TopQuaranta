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

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils import timezone

from analytics.management.commands.enviar_digest_setmanal import _delta, _mov
from ingesta.clients import youtube as yt
from music.constants import DIES_CADUCITAT
from music.models import Artista, Canco
from ranking.models import SenyalDiari, SenyalYouTube

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://www.topquaranta.cat/staff/estat"


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

    # Ritme dels últims 7 dies → ETA. Un ritme de 0 no dona ETA en lloc
    # de dividir per zero o inventar-se una data.
    fa7 = today - datetime.timedelta(days=7)
    ritme = artistes.filter(youtube_checked_at__date__gte=fa7).count() / 7
    queden = tot_art - provats
    eta = round(queden / ritme) if ritme >= 1 and queden > 0 else None

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
            "ahir": ahir_provats,
        },
        "aparellament": {
            "total": _delta(total_ap, total_ap - ap_avui),
            "total_n": total_ap,
            "elegibles": en_finestra.count(),
            "territoris": per_territori,
        },
        "punt_cec": punt_cec,
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
        + (f"  (~{d['eta_dies']} dies al ritme actual)" if d["eta_dies"] else ""),
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
