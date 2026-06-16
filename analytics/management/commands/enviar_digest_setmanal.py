"""Weekly admin email digest — "Setmanari TopQuaranta".

Runs every Monday at 08:00 UTC. Sends the `ADMINS` recipients a
brand-coherent HTML summary (yellow-on-ink, Playfair/Roboto) of the
prior 7 days vs the 7 before, plus a plain-text fallback. The whole
point is that the inbox becomes the trigger to open the panel — so the
sections mirror what actually matters for *this* project, not generic
web vanity metrics.

Sections (see `analytics/templates/analytics/digest_setmanal.html`):
  1. Audiència humana — human pageviews (bots filtered out of the
     headline), registres, newsletter, top human pages.
  2. D'on venen — acquisition buckets from the `referrer` event.
  3. Pipeline del catàleg — catalog gauges + W-o-W deltas, moderation
     decisions (StaffAuditLog), Whisper/MB coverage, backlog alert.
  4. Ranking per territori — TopSetmanal entries generated per territory.
  5. SEO i enllaços externs — GSC impressions/clicks/position, Bing
     inbound links, Core Web Vitals.
  6. Distribució social — publications, followers per platform, top post.

Self-contained: composes subject + HTML + text, ships via
`EmailMultiAlternatives` from `SERVER_EMAIL` (the "Josep Quaranta"
display name) through the configured Brevo SMTP backend.

`--dry-run` prints the text body; `--html-out PATH` writes the rendered
HTML to a file so the design can be previewed locally without sending.
"""

from __future__ import annotations

import datetime
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Sum
from django.template.loader import render_to_string
from django.utils import timezone

from analytics.models import (
    MetricaBingLinks,
    MetricaCWV,
    MetricaEsdeveniment,
    MetricaPipeline,
    MetricaSEOQuery,
    MetricaSocialPlatform,
    MetricaSocialPost,
)
from music.constants import TERRITORI_NOMS
from music.dates import project_week_number
from music.models import StaffAuditLog
from ranking.models import TopSetmanal

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://www.topquaranta.cat/staff/analytics"

# Canonical territory order for the ranking section.
_TERR_ORDER = ["PPCC", "CAT", "VAL", "BAL", "CNO", "AND", "FRA", "ALG", "CAR", "ALT"]

# Acquisition buckets emitted by the `referrer` event (Fase 1).
_REFERRER_LABELS = {
    "cerca_organica": "Cerca orgànica",
    "social": "Xarxes socials",
    "directe": "Directe",
    "referral": "Altres webs",
}

# StaffAuditLog actions that count as a moderation decision, grouped.
_DECISION_GROUPS = {
    "cancons": ["canco_aprovar", "canco_rebutjar", "canco_rebutjar_album"],
    "artistes": [
        "artista_aprovar",
        "artista_rebutjar",
        "pendent_aprovar",
        "pendent_descartar",
    ],
    "propostes": ["proposta_aprovar", "proposta_rebutjar"],
    "sollicituds": ["sollicitud_aprovar", "sollicitud_rebutjar"],
}


# ── small query helpers ────────────────────────────────────────────────
def _sum_events(clau: str, since, until, *, dim2: str | None = None) -> int:
    qs = MetricaEsdeveniment.objects.filter(clau=clau, data__gte=since, data__lte=until)
    if dim2 is not None:
        qs = qs.filter(dimensio_2=dim2)
    return qs.aggregate(t=Sum("comptador"))["t"] or 0


def _gauge_on_or_before(clau: str, date, *, is_float: bool = False):
    row = (
        MetricaPipeline.objects.filter(clau=clau, dimensio_1="", data__lte=date)
        .order_by("-data")
        .first()
    )
    if row is None:
        return None
    if is_float:
        return row.valor_float
    return row.valor_int if row.valor_int is not None else int(row.valor_float or 0)


def _delta(now, prev, *, increase_is_bad: bool = False) -> dict:
    """Compare two numbers into a template-friendly delta dict.

    `moved` drives the arrow (up/down/flat); `tone` drives the colour
    (good/bad), so a metric where growth is bad (pendents, bots) can show
    a red up-arrow.
    """
    d = {"now": now, "prev": prev, "pct": None, "moved": "none", "tone": "none"}
    if now is not None:
        if prev:
            change = round((now - prev) / prev * 100)
            d["pct"] = abs(change)
            if change > 0:
                d["moved"] = "up"
                d["tone"] = "bad" if increase_is_bad else "good"
            elif change < 0:
                d["moved"] = "down"
                d["tone"] = "good" if increase_is_bad else "bad"
            else:
                d["moved"] = "flat"
                d["tone"] = "flat"
        elif now:
            d["moved"] = "up"
            d["tone"] = "new"
    # Precompute presentation so templates stay branch-free.
    d["arrow"] = {"up": "▲", "down": "▼", "flat": "=", "none": ""}[d["moved"]]
    d["color"] = {
        "good": "#4ade80",
        "new": "#4ade80",
        "bad": "#f87171",
        "flat": "#a8a29e",
        "none": "#a8a29e",
    }[d["tone"]]
    return d


def _seo_window(since, until):
    agg = MetricaSEOQuery.objects.filter(data__gte=since, data__lte=until).aggregate(
        imp=Sum("impressions"), clk=Sum("clicks")
    )
    imp = agg["imp"] or 0
    clk = agg["clk"] or 0
    rows = list(
        MetricaSEOQuery.objects.filter(data__gte=since, data__lte=until).values_list(
            "position", "impressions"
        )
    )
    total_imp = sum(i or 0 for _, i in rows) or 1
    pos = sum((p or 0) * (i or 0) for p, i in rows) / total_imp
    return imp, clk, round(pos, 1)


# ── context builder ────────────────────────────────────────────────────
def build_context(today: datetime.date) -> dict:
    since_now = today - datetime.timedelta(days=6)
    until_now = today
    until_prev = since_now - datetime.timedelta(days=1)
    since_prev = until_prev - datetime.timedelta(days=6)

    # ── A. Audiència humana ─────────────────────────────────────────
    humans = _delta(
        _sum_events("pageview", since_now, until_now, dim2="human"),
        _sum_events("pageview", since_prev, until_prev, dim2="human"),
    )
    bots = _sum_events("pageview", since_now, until_now, dim2="bot")
    total_pv = _sum_events("pageview", since_now, until_now)
    bot_share = round(bots / total_pv * 100) if total_pv else 0

    nl_now = _gauge_on_or_before("newsletter_subscriptors", today)
    nl_prev = _gauge_on_or_before("newsletter_subscriptors", until_prev)

    top_pages = [
        {"path": (r["dimensio_1"] or "/")[:42], "total": r["t"]}
        for r in MetricaEsdeveniment.objects.filter(
            clau="pageview",
            dimensio_2="human",
            data__gte=since_now,
            data__lte=until_now,
        )
        .values("dimensio_1")
        .annotate(t=Sum("comptador"))
        .order_by("-t")[:5]
    ]

    audiencia = {
        "humans": humans,
        "bots": bots,
        "bot_share": bot_share,
        "total": total_pv,
        "registres": _delta(
            _sum_events("registre_complet", since_now, until_now),
            _sum_events("registre_complet", since_prev, until_prev),
        ),
        "newsletter": _delta(nl_now, nl_prev),
        "top_pages": top_pages,
    }

    # ── B. D'on venen (referrer) ────────────────────────────────────
    ref_rows = {
        r["dimensio_1"]: r["t"]
        for r in MetricaEsdeveniment.objects.filter(
            clau="referrer", data__gte=since_now, data__lte=until_now
        )
        .values("dimensio_1")
        .annotate(t=Sum("comptador"))
    }
    ref_total = sum(ref_rows.values())
    referrer_buckets = [
        {
            "key": key,
            "label": _REFERRER_LABELS[key],
            "total": ref_rows.get(key, 0),
            "pct": round(ref_rows.get(key, 0) / ref_total * 100) if ref_total else 0,
        }
        for key in _REFERRER_LABELS
        if ref_rows.get(key)
    ]
    referrer_buckets.sort(key=lambda b: b["total"], reverse=True)

    # ── C. Pipeline del catàleg ─────────────────────────────────────
    pendents = _delta(
        _gauge_on_or_before("cancons_pendents", today),
        _gauge_on_or_before("cancons_pendents", until_prev),
        increase_is_bad=True,
    )
    decision_counts = {
        r["action"]: r["c"]
        for r in StaffAuditLog.objects.filter(
            created_at__date__gte=since_now, created_at__date__lte=until_now
        )
        .values("action")
        .annotate(c=Count("id"))
    }
    decisions = {
        grp: sum(decision_counts.get(a, 0) for a in actions)
        for grp, actions in _DECISION_GROUPS.items()
    }
    decisions["total"] = sum(decisions.values())

    pipeline = {
        "verificades": _delta(
            _gauge_on_or_before("cancons_verificades", today),
            _gauge_on_or_before("cancons_verificades", until_prev),
        ),
        "pendents": pendents,
        "aprovats": _delta(
            _gauge_on_or_before("artistes_aprovats", today),
            _gauge_on_or_before("artistes_aprovats", until_prev),
        ),
        "whisper": _gauge_on_or_before("cobertura_whisper", today, is_float=True),
        "mb": _gauge_on_or_before("cobertura_mb", today, is_float=True),
        "decisions": decisions,
        "backlog_alert": pendents["moved"] == "up",
    }

    # ── D. Ranking per territori ────────────────────────────────────
    last_week = TopSetmanal.objects.aggregate(m=Max("setmana"))["m"]
    terr_counts = {
        r["territori"]: r["c"]
        for r in TopSetmanal.objects.filter(setmana=last_week)
        .values("territori")
        .annotate(c=Count("id"))
    }
    ranking = {
        "setmana": last_week,
        "total": sum(terr_counts.values()),
        "territoris": [
            {
                "codi": codi,
                "nom": TERRITORI_NOMS.get(codi, codi),
                "count": terr_counts[codi],
            }
            for codi in _TERR_ORDER
            if terr_counts.get(codi)
        ],
    }

    # ── E. SEO i enllaços externs ───────────────────────────────────
    imp_now, clk_now, pos_now = _seo_window(since_now, until_now)
    imp_prev, clk_prev, pos_prev = _seo_window(since_prev, until_prev)
    seo_queries = [
        {
            "query": r["query"][:48],
            "clicks": r["clicks"],
            "impressions": r["impressions"],
        }
        for r in MetricaSEOQuery.objects.filter(
            data__gte=since_now, data__lte=until_now
        )
        .values("query")
        .annotate(clicks=Sum("clicks"), impressions=Sum("impressions"))
        .order_by("-clicks", "-impressions")[:5]
    ]
    bing_links_row = MetricaBingLinks.objects.order_by("-data").first()
    cwv_row = MetricaCWV.objects.filter(category="mobile").order_by("-data").first()
    seo = {
        "has_data": imp_now > 0 or clk_now > 0,
        "impressions": _delta(imp_now, imp_prev),
        "clicks": _delta(clk_now, clk_prev),
        "position": _delta(pos_now, pos_prev, increase_is_bad=True),
        "top_queries": seo_queries,
        "bing_links": (
            {
                "inbound": bing_links_row.inbound_links,
                "domains": bing_links_row.linking_domains,
            }
            if bing_links_row
            else None
        ),
        "cwv": (
            {
                "score": cwv_row.score,
                "lcp": cwv_row.lcp_ms,
                "inp": cwv_row.inp_ms,
                "cls": cwv_row.cls,
            }
            if cwv_row
            else None
        ),
    }

    # ── F. Distribució social ───────────────────────────────────────
    followers = []
    for platform in ("instagram", "mastodon", "bluesky", "telegram"):
        cur = (
            MetricaSocialPlatform.objects.filter(
                platform=platform, metric__in=("followers", "members")
            )
            .order_by("-data")
            .first()
        )
        if cur is None:
            continue
        old = (
            MetricaSocialPlatform.objects.filter(
                platform=platform,
                metric__in=("followers", "members"),
                data__lte=until_prev,
            )
            .order_by("-data")
            .first()
        )
        followers.append(
            {
                "platform": platform,
                "valor": cur.valor,
                "delta": cur.valor - old.valor if old else None,
            }
        )

    per_post: dict[int, MetricaSocialPost] = {}
    for m in (
        MetricaSocialPost.objects.filter(data__gte=since_now, data__lte=until_now)
        .select_related("socialpost")
        .order_by("-data")
    ):
        per_post.setdefault(m.socialpost_id, m)
    top_post = None
    if per_post:
        best = max(per_post.values(), key=lambda m: m.likes + m.replies + m.shares)
        sp = best.socialpost
        top_post = {
            "label": f"{sp.platform}/{sp.tipus}"
            + (f"/{sp.territori}" if sp.territori else ""),
            "likes": best.likes,
            "replies": best.replies,
            "shares": best.shares,
            "reach": best.reach,
        }

    social = {
        "publicacions": _sum_events("social_publicat", since_now, until_now),
        "followers": followers,
        "top_post": top_post,
    }

    # ── Frescor de dades (early-warning on a stuck cron) ─────────────
    last_snapshot = MetricaPipeline.objects.aggregate(m=Max("data"))["m"]
    frescor = {
        "last_snapshot": last_snapshot,
        "stale": bool(
            last_snapshot and last_snapshot < today - datetime.timedelta(days=1)
        ),
    }

    return {
        "subject": f"[TopQuaranta] Setmanari · Setmana {project_week_number(today)}"
        f" · {since_now:%d/%m} – {until_now:%d/%m}",
        "week_number": project_week_number(today),
        "period": {"since": since_now, "until": until_now},
        "compare": {"since": since_prev, "until": until_prev},
        "audiencia": audiencia,
        "referrer": {"buckets": referrer_buckets, "total": ref_total},
        "pipeline": pipeline,
        "ranking": ranking,
        "seo": seo,
        "social": social,
        "frescor": frescor,
        "dashboard_url": DASHBOARD_URL,
    }


def _arrow(delta: dict) -> str:
    return delta["arrow"]


def render_text(ctx: dict) -> str:
    """Plain-text fallback — mirrors the HTML sections, scannable."""
    p = ctx["period"]
    a = ctx["audiencia"]
    lines = [
        f"SETMANARI TOPQUARANTA · Setmana {ctx['week_number']}",
        f"Període: {p['since']} → {p['until']}",
        "",
        "AUDIÈNCIA HUMANA",
        f"  Visites humanes   {a['humans']['now']} {_arrow(a['humans'])}"
        f"  ({a['bot_share']}% del brut eren bots, filtrats)",
        f"  Registres         {a['registres']['now']} {_arrow(a['registres'])}",
        f"  Newsletter        {a['newsletter']['now']} {_arrow(a['newsletter'])}",
    ]
    if ctx["referrer"]["buckets"]:
        lines += ["", "D'ON VENEN"]
        lines += [
            f"  {b['label'].ljust(16)} {b['pct']:>3}%  ({b['total']})"
            for b in ctx["referrer"]["buckets"]
        ]
    pl = ctx["pipeline"]
    lines += [
        "",
        "PIPELINE DEL CATÀLEG",
        f"  Cançons verificades {pl['verificades']['now']} {_arrow(pl['verificades'])}",
        f"  Cançons pendents    {pl['pendents']['now']} {_arrow(pl['pendents'])}"
        + ("  ⚠ creixent" if pl["backlog_alert"] else ""),
        f"  Artistes aprovats   {pl['aprovats']['now']} {_arrow(pl['aprovats'])}",
        f"  Decisions moderació {pl['decisions']['total']}"
        f"  (cançons {pl['decisions']['cancons']}, artistes {pl['decisions']['artistes']})",
    ]
    r = ctx["ranking"]
    if r["territoris"]:
        lines += ["", f"RANKING ({r['setmana']}) — {r['total']} entrades"]
        lines += [
            f"  {t['codi'].ljust(5)} {t['count']:>3}  {t['nom']}"
            for t in r["territoris"]
        ]
    s = ctx["seo"]
    if s["has_data"]:
        lines += [
            "",
            "SEO",
            f"  Impressions {s['impressions']['now']} {_arrow(s['impressions'])}"
            f"  ·  Clics {s['clicks']['now']} {_arrow(s['clicks'])}"
            f"  ·  Posició {s['position']['now']} {_arrow(s['position'])}",
        ]
    if s["bing_links"]:
        lines.append(
            f"  Enllaços entrants {s['bing_links']['inbound']}"
            f" ({s['bing_links']['domains']} dominis)"
        )
    soc = ctx["social"]
    lines += ["", "SOCIAL", f"  Publicacions {soc['publicacions']}"]
    for f in soc["followers"]:
        d = (
            f" ({'+' if f['delta'] and f['delta'] >= 0 else ''}{f['delta']})"
            if f["delta"] is not None
            else ""
        )
        lines.append(f"  {f['platform'].ljust(12)} {f['valor']}{d}")
    lines += ["", f"Dashboard: {ctx['dashboard_url']}"]
    if ctx["frescor"]["stale"]:
        lines.append(
            f"⚠ Dades possiblement estancades — últim snapshot {ctx['frescor']['last_snapshot']}"
        )
    lines += [
        "",
        "Aggregate-only (RGPD): cap dada personal, cap IP, cap fingerprint.",
    ]
    return "\n".join(lines)


class Command(BaseCommand):
    help = "Envia el Setmanari (digest setmanal d'analytics) a l'administrador."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Imprimeix el cos de text en lloc d'enviar-lo.",
        )
        parser.add_argument(
            "--html-out",
            metavar="PATH",
            help="Escriu l'HTML renderitzat a un fitxer (per previsualitzar en local).",
        )

    def handle(self, *args, **opts) -> None:
        ctx = build_context(timezone.localdate())
        text_body = render_text(ctx)
        html_body = render_to_string("analytics/digest_setmanal.html", ctx)

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
        self.stdout.write(self.style.SUCCESS(f"Setmanari enviat: {ctx['subject']}"))
