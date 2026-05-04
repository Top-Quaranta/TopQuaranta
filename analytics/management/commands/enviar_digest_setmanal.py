"""Weekly admin email digest.

Runs every Monday at 08:00 UTC. Sends `admin@topquaranta.cat` (the
single recipient on the `ADMINS` list) a one-page text summary of
the prior 7 days vs the 7 before that. Same metrics the staff
dashboard shows, condensed into a scannable email so the inbox is
the trigger to open the panel — not the other way around.

Self-contained: composes the subject + plain-text body, ships via
`mail_admins()` so it goes through the same Brevo SMTP path the
rest of the project uses (no extra credential surface).

Sections:
  1. Header with the period dates.
  2. Top KPIs with W-o-W deltas.
  3. Top 5 pages.
  4. Top 5 UTM sources.
  5. Top 3 social posts by engagement.
  6. Catalog snapshot (verificades / pendents / cobertura whisper+MB).
  7. Footer with the dashboard URL.
"""

from __future__ import annotations

import datetime
import logging

from django.core.mail import mail_admins
from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from analytics.models import (
    MetricaEsdeveniment,
    MetricaPipeline,
    MetricaSocialPlatform,
    MetricaSocialPost,
)

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://www.topquaranta.cat/staff/analytics"


def _sum_events(clau: str, since, until) -> int:
    return (
        MetricaEsdeveniment.objects.filter(
            clau=clau, data__gte=since, data__lte=until
        ).aggregate(t=Sum("comptador"))["t"]
        or 0
    )


def _delta_line(label: str, now: int, prev: int, *, width: int = 22) -> str:
    pct = ""
    if prev > 0:
        change = round((now - prev) / prev * 100)
        if change > 0:
            pct = f" (+{change} %)"
        elif change < 0:
            pct = f" ({change} %)"
        else:
            pct = " (=)"
    elif now > 0:
        pct = " (nou)"
    return f"  {label.ljust(width)} {now:>6}{pct}"


def _gauge_latest(clau: str) -> int | None:
    row = (
        MetricaPipeline.objects.filter(clau=clau, dimensio_1="")
        .order_by("-data")
        .first()
    )
    if row is None:
        return None
    return row.valor_int if row.valor_int is not None else int(row.valor_float or 0)


def _format_pct(v: float | None) -> str:
    return f"{v:.1f} %" if v is not None else "—"


def _gauge_latest_float(clau: str) -> float | None:
    row = (
        MetricaPipeline.objects.filter(clau=clau, dimensio_1="")
        .order_by("-data")
        .first()
    )
    if row is None:
        return None
    return row.valor_float


class Command(BaseCommand):
    help = "Envia el digest setmanal d'analytics a l'administrador."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Imprimeix el cos del correu en lloc d'enviar-lo.",
        )

    def handle(self, *args, **opts) -> None:
        today = timezone.localdate()
        # Window 1 = last 7 days (today inclusive). Window 0 = the 7
        # days before. Mon→Sun if cron fires on Monday.
        since_now = today - datetime.timedelta(days=6)
        until_now = today
        until_prev = since_now - datetime.timedelta(days=1)
        since_prev = until_prev - datetime.timedelta(days=6)

        kpis = []
        for label, clau in [
            ("Pageviews", "pageview"),
            ("Registres", "registre_complet"),
            ("Propostes", "proposta_crear"),
            ("Sol·licituds", "solicitud_gestor_crear"),
            ("Feedback", "feedback_crear"),
            ("UTM landings", "utm_landing"),
            ("Publicacions", "social_publicat"),
        ]:
            now = _sum_events(clau, since_now, until_now)
            prev = _sum_events(clau, since_prev, until_prev)
            kpis.append(_delta_line(label, now, prev))

        top_pages = list(
            MetricaEsdeveniment.objects.filter(
                clau="pageview", data__gte=since_now, data__lte=until_now
            )
            .values("dimensio_1")
            .annotate(t=Sum("comptador"))
            .order_by("-t")[:5]
        )
        top_utm = list(
            MetricaEsdeveniment.objects.filter(
                clau="utm_landing", data__gte=since_now, data__lte=until_now
            )
            .values("dimensio_1", "dimensio_2")
            .annotate(t=Sum("comptador"))
            .order_by("-t")[:5]
        )
        # One row per socialpost: keep the latest snapshot in the
        # window. We dedup Python-side so this works on both Postgres
        # (production) and SQLite (test backend), which doesn't have
        # `DISTINCT ON`.
        per_post: dict[int, MetricaSocialPost] = {}
        for m in (
            MetricaSocialPost.objects.filter(data__gte=since_now, data__lte=until_now)
            .select_related("socialpost")
            .order_by("-data")
        ):
            per_post.setdefault(m.socialpost_id, m)
        top_posts = sorted(
            per_post.values(),
            key=lambda m: m.likes + m.replies + m.shares,
            reverse=True,
        )[:3]

        followers_now = {}
        for row in MetricaSocialPlatform.objects.filter(
            metric__in=("followers", "members")
        ).order_by("platform", "-data"):
            followers_now.setdefault(row.platform, row.valor)

        # Compose body.
        lines: list[str] = []
        lines.append(f"DIGEST SETMANAL · TopQuaranta")
        lines.append(f"Període: {since_now} → {until_now}")
        lines.append(f"Comparatiu: {since_prev} → {until_prev}")
        lines.append("")
        lines.append("KPIs (vs setmana anterior)")
        lines.append("─" * 44)
        lines.extend(kpis)
        lines.append("")
        lines.append("Catàleg (snapshot més recent)")
        lines.append("─" * 44)
        verif = _gauge_latest("cancons_verificades")
        pend = _gauge_latest("cancons_pendents")
        artap = _gauge_latest("artistes_aprovats")
        cob_w = _gauge_latest_float("cobertura_whisper")
        cob_m = _gauge_latest_float("cobertura_mb")
        lines.append(f"  Cançons verificades   {verif if verif is not None else '—'}")
        lines.append(f"  Cançons pendents      {pend if pend is not None else '—'}")
        lines.append(f"  Artistes aprovats     {artap if artap is not None else '—'}")
        lines.append(f"  Cobertura Whisper     {_format_pct(cob_w)}")
        lines.append(f"  Cobertura MusicBrainz {_format_pct(cob_m)}")
        lines.append("")
        lines.append("Top 5 pàgines")
        lines.append("─" * 44)
        if not top_pages:
            lines.append("  (sense dades)")
        for p in top_pages:
            path = (p["dimensio_1"] or "/")[:40]
            lines.append(f"  {path.ljust(40)} {p['t']:>6}")
        lines.append("")
        lines.append("Top 5 fonts UTM")
        lines.append("─" * 44)
        if not top_utm:
            lines.append("  (sense dades)")
        for u in top_utm:
            src = (u["dimensio_1"] or "—")[:18]
            cmp_ = (u["dimensio_2"] or "—")[:20]
            lines.append(f"  {src.ljust(18)} {cmp_.ljust(20)} {u['t']:>5}")
        lines.append("")
        lines.append("Top 3 posts per engagement")
        lines.append("─" * 44)
        if not top_posts:
            lines.append("  (sense dades)")
        for m in top_posts:
            sp = m.socialpost
            label = f"{sp.platform}/{sp.tipus}{('/' + sp.territori) if sp.territori else ''}"
            label = label[:32]
            lines.append(
                f"  {label.ljust(32)} L={m.likes:<3} R={m.replies:<3} S={m.shares:<3} reach={m.reach}"
            )
        lines.append("")
        lines.append("Seguidors actuals")
        lines.append("─" * 44)
        if not followers_now:
            lines.append("  (sense dades)")
        for platform, valor in sorted(followers_now.items()):
            unit = "membres" if platform == "telegram" else "seguidors"
            lines.append(f"  {platform.ljust(16)} {valor:>6}  {unit}")
        lines.append("")
        lines.append("─" * 44)
        lines.append(f"Dashboard complet: {DASHBOARD_URL}")
        lines.append("")
        lines.append(
            "Aquest digest és aggregate-only (RGPD): cap dada personal,"
            " cap IP, cap fingerprint."
        )

        body = "\n".join(lines)
        subject = f"[TopQuaranta] Digest setmanal · {since_now} → {until_now}"

        if opts.get("dry_run"):
            self.stdout.write(subject)
            self.stdout.write("=" * 44)
            self.stdout.write(body)
            return

        # `mail_admins` ships through the configured EMAIL_BACKEND,
        # which in production is Brevo SMTP via Stalwart smarthost.
        mail_admins(subject, body, fail_silently=False)
        self.stdout.write(self.style.SUCCESS(f"Digest enviat: {subject}"))
