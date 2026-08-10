"""Weekly admin email digest — "Setmanari TopQuaranta".

Runs every Monday at 08:00 UTC and reports the last COMPLETE calendar
week (Monday → Sunday) against the week before it. Sends the `ADMINS`
recipients a brand-coherent HTML summary (yellow-on-ink,
Playfair/Roboto) plus a plain-text fallback. The whole
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
  6. Distribució social — publications, followers per platform, top post,
     plus a channel × day-of-week grid of what actually went out.
  7. Incidències — publication failures, crons in a bad state and the
     week's Django ERROR records. The section that answers "did
     anything break?" without opening a terminal.

Self-contained: composes subject + HTML + text, ships via
`EmailMultiAlternatives` from `SERVER_EMAIL` (the "Josep Quaranta"
display name) through the configured Brevo SMTP backend.

`--dry-run` prints the text body; `--html-out PATH` writes the rendered
HTML to a file so the design can be previewed locally without sending.
"""

from __future__ import annotations

import datetime
import logging
import time

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Q, Sum
from django.template.loader import render_to_string
from django.utils import timezone

from analytics import incidents
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
from social.models import SocialPost

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


# Below this base, a percentage is noise: 1 → 2 subscribers is "+1",
# not "▲ 100%". Report the absolute move instead.
_PCT_MIN_BASE = 10


def _fmt_num(value) -> str:
    """`4` / `0.3` — drop the decimal noise floats pick up on the way."""
    return f"{value:g}" if isinstance(value, float) else str(value)


def _delta(now, prev, *, increase_is_bad: bool = False) -> dict:
    """Compare two numbers into a template-friendly delta dict.

    `moved` drives the arrow (up/down/flat); `tone` drives the colour
    (good/bad), so a metric where growth is bad (pendents, bots) can show
    a red up-arrow. `text` is what actually gets printed next to the
    arrow, and it is deliberately NOT always a percentage:

      * no movement at all → empty, so the KPI reads "3.912 =" instead
        of the meaningless "3.912 = 0%";
      * a base under `_PCT_MIN_BASE`, or a change that rounds to 0% →
        the absolute move ("+7", "−4"), which is honest at any scale.
        The old code rounded a real change down to "0%" and then took
        that 0 as "flat", reporting a metric as unmoved when it wasn't.
    """
    d = {
        "now": now,
        "prev": prev,
        "pct": None,
        "diff": None,
        "moved": "none",
        "tone": "none",
        "text": "",
    }
    if now is not None:
        if prev:
            diff = now - prev
            pct = round(abs(diff) / prev * 100)
            d["diff"] = diff
            d["pct"] = pct
            if diff > 0:
                d["moved"] = "up"
                d["tone"] = "bad" if increase_is_bad else "good"
            elif diff < 0:
                d["moved"] = "down"
                d["tone"] = "good" if increase_is_bad else "bad"
            else:
                d["moved"] = "flat"
                d["tone"] = "flat"
            if diff and (pct < 1 or abs(prev) < _PCT_MIN_BASE):
                d["text"] = f"{'+' if diff > 0 else '−'}{_fmt_num(abs(diff))}"
            elif diff:
                d["text"] = f"{pct}%"
        elif now:
            d["moved"] = "up"
            d["tone"] = "new"
            d["text"] = "nou"
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


# ── calendari de publicacions ──────────────────────────────────────────
# Day-of-week grid: one row per channel, one column per day of the
# reported window — dilluns → diumenge, since `build_context` reports
# the last complete calendar week. Each column carries its weekday
# name, which is what makes the grid readable at a glance.
_DIES_CURT = ["dl", "dt", "dc", "dj", "dv", "ds", "dg"]
_DIES_NOM = [
    "dilluns",
    "dimarts",
    "dimecres",
    "dijous",
    "divendres",
    "dissabte",
    "diumenge",
]

# Row order = the publishing chain, IG first (it drives the calendar).
_CANALS = [
    ("instagram_feed", "IG feed"),
    ("instagram_story", "IG stories"),
    ("mastodon", "Mastodon"),
    ("bluesky", "Bluesky"),
    ("telegram", "Telegram"),
    ("newsletter", "Newsletter"),
]

# Cell labels — a 7-column table has ~62 px per cell at 640 px and ~45
# on a phone (the wrapper reflows to 100%), so the content type is
# abbreviated hard and explained by the legend under the grid.
_TIPUS_CURT = {
    "top_ppcc": "Top",
    "top_territorial": "Terr",
    "nous_albums": "Àlb",
    "nous_singles": "Sing",
    "moviment": "Mov",
}


def _calendari_social(since: datetime.date, until: datetime.date) -> dict:
    """Grid of what went out on which day, per channel.

    Source is `SocialPost`, the canonical idempotent one-row-per-slot
    ledger (the `social_publicat` counter is append-only and depends on
    every call site remembering to `register()` — see the "Social
    counter source = SocialPost" decision). A slot is placed on the day
    it was actually published; a slot that failed or was skipped never
    got a `published_at`, so it lands on the day the attempt was
    recorded, which is where the operator will look for it.
    """
    dies = [since + datetime.timedelta(days=i) for i in range((until - since).days + 1)]
    posts = SocialPost.objects.filter(
        Q(published_at__date__gte=since, published_at__date__lte=until)
        | Q(
            published_at__isnull=True,
            updated_at__date__gte=since,
            updated_at__date__lte=until,
        )
    )

    # (platform, dia) → list of posts.
    cel_les: dict[tuple[str, datetime.date], list] = {}
    for p in posts:
        moment = p.published_at or p.updated_at
        cel_les.setdefault((p.platform, timezone.localdate(moment)), []).append(p)

    files = []
    publicats = 0
    for platform, label in _CANALS:
        cel_files = []
        total_fila = 0
        for dia in dies:
            grup = cel_les.get((platform, dia), [])
            fets = [p for p in grup if p.status == SocialPost.STATUS_PUBLICAT]
            fallats = [p for p in grup if p.status == SocialPost.STATUS_ERROR]
            total_fila += len(fets)
            publicats += len(fets)
            # A day where 4 stories went out and 1 failed must show both:
            # collapsing the cell to the failure alone would hide the work
            # that did happen, and collapsing it to the success would hide
            # the incident.
            if fets:
                estat, mostra = "publicat", fets
            elif fallats:
                estat, mostra = "error", fallats
            elif grup:
                estat, mostra = "omes", grup
            else:
                cel_files.append(
                    {"estat": "buit", "text": "·", "count": 0, "fallats": 0}
                )
                continue
            tipus = {_TIPUS_CURT.get(p.tipus, p.tipus) for p in mostra}
            text = tipus.pop() if len(tipus) == 1 else "Diversos"
            if len(mostra) > 1:
                text = f"{text}×{len(mostra)}"
            cel_files.append(
                {
                    "estat": estat,
                    "text": text,
                    "count": len(mostra),
                    # Only set when the cell is showing successes too; a
                    # pure-failure cell is already red.
                    "fallats": len(fallats) if fets else 0,
                }
            )
        files.append(
            {
                "platform": platform,
                "label": label,
                "cel_les": cel_files,
                "total": total_fila,
            }
        )

    return {
        "dies": [
            {
                "curt": _DIES_CURT[d.weekday()],
                "nom": _DIES_NOM[d.weekday()],
                "num": f"{d.day:02d}",
                "data": d,
            }
            for d in dies
        ],
        "files": files,
        "publicats": publicats,
        "cap": publicats == 0,
    }


# ── incidències ────────────────────────────────────────────────────────
def _incidencies(since: datetime.date, until: datetime.date, now_ts: int) -> dict:
    """Everything that went wrong this week, from three sources.

    Publication failures come from `SocialPost` (dated by `updated_at`,
    i.e. when the attempt was recorded, since a failed slot has no
    `published_at`); stuck crons and Django ERROR records come off the
    box via `analytics.incidents`.
    """
    fallades = [
        {
            "label": f"{p.get_platform_display()} · {_TIPUS_CURT.get(p.tipus, p.tipus)}"
            + (f" · {p.territori}" if p.territori else ""),
            "error": (
                (p.error_msg or "").strip().splitlines()[0][:120]
                if p.error_msg
                else "sense detall"
            ),
            "quan": timezone.localdate(p.updated_at),
        }
        for p in SocialPost.objects.filter(
            status=SocialPost.STATUS_ERROR,
            updated_at__date__gte=since,
            updated_at__date__lte=until,
        ).order_by("updated_at")[:8]
    ]
    omesos = SocialPost.objects.filter(
        status=SocialPost.STATUS_OMES,
        updated_at__date__gte=since,
        updated_at__date__lte=until,
    ).count()

    crons = incidents.cron_anomalies(now_ts)
    errors_log = incidents.django_errors(since, until)

    return {
        "social_fallades": fallades,
        "social_omesos": omesos,
        "crons": crons,
        "errors_log": errors_log,
        "total": len(fallades) + len(crons) + errors_log["total"],
        # `omesos` is intentionally out of the total: an omitted slot is
        # usually the calendar saying "no content for this phase", not a
        # failure. It is reported, not counted as an incident.
    }


# ── context builder ────────────────────────────────────────────────────
def build_context(today: datetime.date) -> dict:
    # The last COMPLETE calendar week, Monday → Sunday. The mail goes
    # out Monday morning, so a rolling "last 7 days" window would end on
    # a few hours of the current Monday and start mid-week — reporting a
    # partial day as if it were a whole one and cutting the weekend
    # publishing block in half. Monday-to-Sunday also makes the social
    # calendar's columns line up with the week the reader has in mind.
    since_now = today - datetime.timedelta(days=today.weekday() + 7)
    until_now = since_now + datetime.timedelta(days=6)
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

    nl_now = _gauge_on_or_before("newsletter_subscriptors", until_now)
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
    referrer_buckets = []
    for key, label in _REFERRER_LABELS.items():
        total = ref_rows.get(key, 0)
        if not total:
            continue
        pct = round(total / ref_total * 100) if ref_total else 0
        referrer_buckets.append(
            {
                "key": key,
                "label": label,
                "total": total,
                "pct": pct,
                # Explicit remainder: a lone `width:N%` cell in a
                # one-cell row still stretches to the full table width,
                # so every bucket drew a full-width bar whatever its
                # share. The empty second cell makes the bar honest.
                "rest": 100 - pct,
            }
        )
    referrer_buckets.sort(key=lambda b: b["total"], reverse=True)

    # ── C. Pipeline del catàleg ─────────────────────────────────────
    pendents = _delta(
        _gauge_on_or_before("cancons_pendents", until_now),
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
            _gauge_on_or_before("cancons_verificades", until_now),
            _gauge_on_or_before("cancons_verificades", until_prev),
        ),
        "pendents": pendents,
        "aprovats": _delta(
            _gauge_on_or_before("artistes_aprovats", until_now),
            _gauge_on_or_before("artistes_aprovats", until_prev),
        ),
        "whisper": _gauge_on_or_before("cobertura_whisper", until_now, is_float=True),
        "mb": _gauge_on_or_before("cobertura_mb", until_now, is_float=True),
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

    calendari = _calendari_social(since_now, until_now)
    social = {
        # Counted off the calendar grid, i.e. off `SocialPost`, so the
        # headline and the table can't tell two different stories.
        "publicacions": calendari["publicats"],
        "calendari": calendari,
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
        "subject": f"[TopQuaranta] Setmanari · Setmana {project_week_number(since_now)}"
        f" · {since_now:%d/%m} – {until_now:%d/%m}",
        "week_number": project_week_number(since_now),
        "period": {"since": since_now, "until": until_now},
        "compare": {"since": since_prev, "until": until_prev},
        "audiencia": audiencia,
        "referrer": {"buckets": referrer_buckets, "total": ref_total},
        "pipeline": pipeline,
        "ranking": ranking,
        "seo": seo,
        "social": social,
        "incidencies": _incidencies(since_now, until_now, int(time.time())),
        "frescor": frescor,
        "dashboard_url": DASHBOARD_URL,
        "site_url": getattr(settings, "SITE_URL", "https://www.topquaranta.cat").rstrip(
            "/"
        ),
    }


def _mov(delta: dict) -> str:
    """Arrow + the movement text, e.g. "▲ 12%" / "▼ −4" / "=" / ""."""
    return f"{delta['arrow']} {delta['text']}".strip()


def render_text(ctx: dict) -> str:
    """Plain-text fallback — mirrors the HTML sections, scannable."""
    p = ctx["period"]
    a = ctx["audiencia"]
    lines = [
        f"SETMANARI TOPQUARANTA · Setmana {ctx['week_number']}",
        f"Període: {p['since']} → {p['until']}",
        "",
        "AUDIÈNCIA HUMANA",
        f"  Visites humanes   {a['humans']['now']} {_mov(a['humans'])}"
        f"  ({a['bot_share']}% del brut eren bots, filtrats)",
        f"  Registres         {a['registres']['now']} {_mov(a['registres'])}",
        f"  Newsletter        {a['newsletter']['now']} {_mov(a['newsletter'])}",
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
        f"  Cançons verificades {pl['verificades']['now']} {_mov(pl['verificades'])}",
        f"  Cançons pendents    {pl['pendents']['now']} {_mov(pl['pendents'])}"
        + ("  ⚠ creixent" if pl["backlog_alert"] else ""),
        f"  Artistes aprovats   {pl['aprovats']['now']} {_mov(pl['aprovats'])}",
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
            f"  Impressions {s['impressions']['now']} {_mov(s['impressions'])}"
            f"  ·  Clics {s['clicks']['now']} {_mov(s['clicks'])}"
            f"  ·  Posició {s['position']['now']} {_mov(s['position'])}",
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

    cal = soc["calendari"]
    lines += ["", "CALENDARI DE PUBLICACIONS"]
    lines.append(
        "  "
        + "".ljust(12)
        + "".join(f"{d['curt']}{d['num']}".rjust(9) for d in cal["dies"])
    )
    marca = {"error": "✕{}", "omes": "({})"}
    for fila in cal["files"]:
        cel_les = "".join(
            (
                marca.get(c["estat"], "{}").format(c["text"])
                + (f"✕{c['fallats']}" if c["fallats"] else "")
            ).rjust(11)
            for c in fila["cel_les"]
        )
        lines.append(f"  {fila['label'].ljust(12)}{cel_les}")
    if cal["cap"]:
        lines.append("  ⚠ Cap publicació aquesta setmana.")

    inc = ctx["incidencies"]
    lines += ["", "INCIDÈNCIES"]
    if not inc["total"]:
        lines.append("  Cap incidència registrada. ✓")
    for c in inc["crons"]:
        lines.append(
            f"  [cron] {c['name']} — {c['display']}"
            + ("  (silenciat)" if c.get("silenced") else "")
        )
    for fallada in inc["social_fallades"]:
        lines.append(
            f"  [social] {fallada['quan']} {fallada['label']} — {fallada['error']}"
        )
    el = inc["errors_log"]
    if el["total"]:
        lines.append(f"  [errors.log] {el['total']} errors Django:")
        lines += [f"      {t['count']}× {t['logger']}: {t['msg']}" for t in el["top"]]
        if el["altres"]:
            lines.append(f"      (+{el['altres']} tipus més)")
    elif not el["disponible"]:
        lines.append("  [errors.log] sense accés al fitxer de registre.")
    if inc["social_omesos"]:
        lines.append(
            f"  Slots omesos: {inc['social_omesos']}"
            " (fase sense contingut, no compta com a error)."
        )

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
