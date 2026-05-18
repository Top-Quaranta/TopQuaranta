"""Staff analytics summary endpoint — aggregate dashboards.

GET /api/v1/staff/analytics/summary/?days=30

Returns a self-contained JSON payload the SPA can chart without
follow-up queries. Sections:

  * `pipeline`    — daily series for each `MetricaPipeline` clau
                    (cançons verificades, pendents, rebutjades,
                     cobertura whisper/MB, artistes aprovats…)
  * `events`      — daily totals per top-level `clau` from
                    `MetricaEsdeveniment` (pageview, registre, propostes,
                     feedback, social_publicat, utm_landing).
  * `pageviews`   — top 20 paths over the window (dim1 of `pageview`).
  * `utm`         — top 20 (source, campaign) pairs.
  * `social`      — counts grouped by channel (dim1 of social_publicat).
  * `feedback`    — counts grouped by target_type (dim1 of feedback_crear).
  * `territoris`  — latest snapshot of cancons_per_territori.

Only numeric aggregates leave the server — no per-user fields, no IPs,
no session keys. Cheap query: each section is one GROUP BY scan over
the per-day partition.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from pathlib import Path

from django.db.models import Max, Sum
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from analytics.models import (
    MetricaCWV,
    MetricaEsdeveniment,
    MetricaPipeline,
    MetricaSEOQuery,
    MetricaSocialPlatform,
    MetricaSocialPost,
)
from web.api.staff._common import IsStaff

# GoAccess writes here from `generar_goaccess`. Served back via
# the staff-only proxy below — never a public Caddy handle, so the
# report stays gated by session + 2FA.
GOACCESS_REPORT = Path("/var/cache/topquaranta/goaccess/report.html")


def _parse_days(request: Request, default: int = 30, cap: int = 365) -> int:
    try:
        n = int(request.GET.get("days") or default)
    except ValueError:
        n = default
    return max(1, min(n, cap))


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsStaff])
def analytics_summary(request: Request) -> Response:
    """Aggregate analytics summary over the last N days (default 30)."""
    days = _parse_days(request)
    today = timezone.localdate()
    since = today - datetime.timedelta(days=days - 1)

    # ── pipeline gauges (daily series) ─────────────────────────────
    pipeline: dict[str, list[dict]] = defaultdict(list)
    qs_pipeline = (
        MetricaPipeline.objects.filter(data__gte=since)
        .order_by("clau", "data")
        .values("data", "clau", "dimensio_1", "valor_int", "valor_float")
    )
    for row in qs_pipeline:
        # Skip per-territori rows here (they get their own section below).
        if row["clau"] == "cancons_per_territori":
            continue
        v = row["valor_int"] if row["valor_int"] is not None else row["valor_float"]
        pipeline[row["clau"]].append({"data": row["data"].isoformat(), "valor": v})

    # ── event totals (daily series, summed across dimensions) ─────
    events: dict[str, list[dict]] = defaultdict(list)
    qs_events = (
        MetricaEsdeveniment.objects.filter(data__gte=since)
        .values("data", "clau")
        .annotate(total=Sum("comptador"))
        .order_by("clau", "data")
    )
    for row in qs_events:
        events[row["clau"]].append(
            {"data": row["data"].isoformat(), "valor": row["total"]}
        )

    # ── top pageview paths ────────────────────────────────────────
    pageviews = list(
        MetricaEsdeveniment.objects.filter(data__gte=since, clau="pageview")
        .values("dimensio_1")
        .annotate(total=Sum("comptador"))
        .order_by("-total")[:20]
    )
    pageviews = [
        {"path": r["dimensio_1"] or "/", "total": r["total"]} for r in pageviews
    ]

    # ── UTM landings (source × campaign) ──────────────────────────
    utm = list(
        MetricaEsdeveniment.objects.filter(data__gte=since, clau="utm_landing")
        .values("dimensio_1", "dimensio_2")
        .annotate(total=Sum("comptador"))
        .order_by("-total")[:20]
    )
    utm = [
        {
            "source": r["dimensio_1"],
            "campaign": r["dimensio_2"] or "—",
            "total": r["total"],
        }
        for r in utm
    ]

    # ── social publications by channel ────────────────────────────
    # Bug 1 of Fase 3 (2026-05-18): the counter now derives from
    # `SocialPost.objects.filter(status=publicat)` instead of the
    # append-only `MetricaEsdeveniment(clau="social_publicat")` row,
    # which depended on every call site remembering to invoke
    # `register()`. Filter by `setmana` because that's the natural
    # grouping unit (one row per slot); we take the Monday of `since`.
    from django.db.models import Count

    from social.models import SocialPost

    since_week = since - datetime.timedelta(days=since.weekday())
    social_rows = list(
        SocialPost.objects.filter(
            status=SocialPost.STATUS_PUBLICAT,
            setmana__gte=since_week,
        )
        .values("platform", "tipus")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    social = [
        {"channel": r["platform"], "tipus": r["tipus"], "total": r["total"]}
        for r in social_rows
    ]

    # ── Publicacions OMESES per canal (Fase 3 problem 6, 2026-05-18) ──
    # Staff should see how much the `fase_distribucio` gate is filtering;
    # otherwise the omès queue is invisible. Same shape as `social`.
    social_omes_rows = list(
        SocialPost.objects.filter(
            status=SocialPost.STATUS_OMES,
            setmana__gte=since_week,
        )
        .values("platform", "tipus")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    social_omes = [
        {"channel": r["platform"], "tipus": r["tipus"], "total": r["total"]}
        for r in social_omes_rows
    ]

    # ── Newsletter audience (Fase 3 problem 4, 2026-05-18) ────────
    # Newsletter is a real channel with the most direct conversion,
    # but it wasn't surfacing in the followers strip because it
    # lacks a `MetricaSocialPlatform(metric=followers)` row. The
    # canonical count is `Usuari.vol_newsletter=True, is_active=True`.
    from django.contrib.auth import get_user_model

    _User = get_user_model()
    newsletter_audience = _User.objects.filter(
        vol_newsletter=True, is_active=True
    ).count()

    # ── feedback by target ────────────────────────────────────────
    feedback_rows = list(
        MetricaEsdeveniment.objects.filter(data__gte=since, clau="feedback_crear")
        .values("dimensio_1")
        .annotate(total=Sum("comptador"))
        .order_by("-total")
    )
    feedback = [
        {"target": r["dimensio_1"] or "altres", "total": r["total"]}
        for r in feedback_rows
    ]

    # ── territoris: latest snapshot only (gauge, not series) ──────
    # Python-side dedup because `DISTINCT ON` is Postgres-only and
    # the test backend is SQLite. Same pattern as `latest_per_pm`
    # below. N is small (≤ 10 territoris) so the full scan is fine.
    latest_per_codi: dict[str, dict] = {}
    for r in (
        MetricaPipeline.objects.filter(clau="cancons_per_territori")
        .order_by("-data")
        .values("dimensio_1", "valor_int", "data")
    ):
        latest_per_codi.setdefault(r["dimensio_1"], r)
    territoris = [
        {
            "codi": r["dimensio_1"],
            "valor": r["valor_int"],
            "data": r["data"].isoformat(),
        }
        for r in latest_per_codi.values()
    ]

    # ── social engagement ── (K2) ─────────────────────────────────
    # Per-platform follower history (daily series so the UI can chart
    # growth) and the latest engagement totals across recent posts.
    followers_qs = (
        MetricaSocialPlatform.objects.filter(data__gte=since, metric="followers")
        .order_by("platform", "data")
        .values("platform", "data", "valor")
    )
    followers_series: dict[str, list[dict]] = defaultdict(list)
    for row in followers_qs:
        followers_series[row["platform"]].append(
            {"data": row["data"].isoformat(), "valor": row["valor"]}
        )

    # Latest snapshot per (platform, metric). Python-side dedup so
    # the query works on both Postgres (production) and SQLite (the
    # test backend lacks `DISTINCT ON`). N is small (≤ 4 platforms ×
    # ≤ 4 metrics = 16 rows) so a full scan + dict.setdefault is
    # fine.
    latest_per_pm: dict[tuple, dict] = {}
    for r in MetricaSocialPlatform.objects.order_by("-data").values(
        "platform", "metric", "valor", "data"
    ):
        latest_per_pm.setdefault((r["platform"], r["metric"]), r)
    latest_platform = [
        {
            "platform": r["platform"],
            "metric": r["metric"],
            "valor": r["valor"],
            "data": r["data"].isoformat(),
        }
        for r in latest_per_pm.values()
    ]

    # Top 10 best-performing posts in the window (by total
    # engagement = likes + replies + shares of the most recent
    # snapshot per post). Same Python-side dedup rationale.
    per_post: dict[int, MetricaSocialPost] = {}
    for m in (
        MetricaSocialPost.objects.filter(data__gte=since)
        .select_related("socialpost")
        .order_by("-data")
    ):
        per_post.setdefault(m.socialpost_id, m)
    top_posts = sorted(
        per_post.values(),
        key=lambda m: m.likes + m.replies + m.shares,
        reverse=True,
    )[:10]
    top_posts = [
        {
            "platform": m.socialpost.platform,
            "tipus": m.socialpost.tipus,
            "territori": m.socialpost.territori,
            "setmana": m.socialpost.setmana.isoformat(),
            "likes": m.likes,
            "replies": m.replies,
            "shares": m.shares,
            "reach": m.reach,
            "data": m.data.isoformat(),
        }
        for m in top_posts
    ]

    # ── Last-updated timestamps per source (so the UI can show
    #    when the dashboard data was last refreshed). Three sources
    #    write into these tables on different cadences:
    #      - snapshot_pipeline (23:00 UTC daily) → MetricaPipeline
    #      - recollir_metrics_social (22:30 UTC daily) → MetricaSocial*
    #      - middleware + register() → MetricaEsdeveniment (live)
    #    We surface the max(updated_at) per source so a stale snapshot
    #    cron is visible at a glance — same panel where the data
    #    already lives.
    pipeline_latest = MetricaPipeline.objects.aggregate(m=Max("data"))["m"]
    events_latest = MetricaEsdeveniment.objects.aggregate(m=Max("data"))["m"]
    social_post_latest = MetricaSocialPost.objects.aggregate(m=Max("fetched_at"))["m"]
    social_platform_latest = MetricaSocialPlatform.objects.aggregate(m=Max("data"))["m"]

    def _iso(v):
        return v.isoformat() if v else None

    return Response(
        {
            "window": {
                "days": days,
                "since": since.isoformat(),
                "until": today.isoformat(),
            },
            "last_updated": {
                # Server clock at response time — trivially the freshest
                # signal available to the UI without an extra round-trip.
                "now": timezone.now().isoformat(),
                "pipeline_snapshot": _iso(pipeline_latest),
                "events": _iso(events_latest),
                "social_post": _iso(social_post_latest),
                "social_platform": _iso(social_platform_latest),
            },
            "pipeline": dict(pipeline),
            "events": dict(events),
            "pageviews": pageviews,
            "utm": utm,
            "social": social,
            "social_omes": social_omes,
            "newsletter_audience": newsletter_audience,
            "feedback": feedback,
            "territoris": territoris,
            "social_metrics": {
                "followers_series": dict(followers_series),
                "latest_platform": latest_platform,
                "top_posts": top_posts,
            },
        }
    )


# Per-response CSP override for the GoAccess HTML. The default
# project-wide CSP set by Caddy is too tight for GoAccess's
# self-contained report:
#   - GoAccess inlines its icon font as `data:application/font-woff…`
#     URIs — needs `font-src data:`.
#   - GoAccess's D3 chart code uses `new Function(...)` internally —
#     needs `'unsafe-eval'` on `script-src`.
#   - The whole bundle is self-contained (no CDN calls), so we don't
#     need to allow any external origin.
# We DON'T relax the project CSP globally; we override on this single
# response, which Caddy's directive replaces (Django emits the header,
# Caddy passes it through). This keeps the rest of the site at the
# strict baseline.
GOACCESS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'"
)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsStaff])
def goaccess_report(request: Request) -> HttpResponse:
    """Proxy the GoAccess HTML report behind staff session + 2FA.

    GoAccess writes the report to `/var/cache/topquaranta/goaccess/
    report.html` (cron `generar_goaccess`, runs nightly). Caddy never
    serves that path directly — the only way in is through this
    endpoint, so only OTP-verified staff see Caddy access analytics.

    Returns 503 with a friendly hint if the report hasn't been
    generated yet (first-boot, or the cron has been silenced for
    a while). Otherwise streams the file with the right MIME so the
    browser renders it inline, with a relaxed CSP scoped to this
    response only (see `GOACCESS_CSP`).
    """
    if not GOACCESS_REPORT.exists():
        return HttpResponse(
            "<p>L'informe GoAccess encara no s'ha generat. Executa "
            "<code>manage.py generar_goaccess</code> o espera al "
            "següent tic del cron (cada nit a les 23:30).</p>",
            content_type="text/html; charset=utf-8",
            status=503,
        )
    try:
        resp = FileResponse(
            open(GOACCESS_REPORT, "rb"),
            content_type="text/html; charset=utf-8",
        )
    except FileNotFoundError as exc:  # race against a fresh regen
        raise Http404("report missing") from exc
    resp["Content-Security-Policy"] = GOACCESS_CSP
    # Belt-and-braces: prevent the report being framed elsewhere
    # (we already set frame-ancestors above; X-Frame-Options is the
    # legacy fallback).
    resp["X-Frame-Options"] = "DENY"
    return resp


# ── SEO dashboard endpoint (Sprint S Bloc D) ────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsStaff])
def analytics_seo(request: Request) -> Response:
    """Aggregate SEO snapshot for the `/staff/analytics` SEO tab.

    Returns:
      - top_queries: the 30 queries with most clicks in the window
      - top_pages: the 30 URLs with most clicks in the window
      - daily_kpis: per-day total impressions + clicks + avg CTR/position
      - cwv: latest Core Web Vitals row per (URL, mobile|desktop)
    """
    days = _parse_days(request, default=28, cap=90)
    today = timezone.localdate()
    since = today - datetime.timedelta(days=days - 1)

    # ── Daily KPI series ────────────────────────────────────────────
    daily = list(
        MetricaSEOQuery.objects.filter(data__gte=since)
        .values("data")
        .annotate(
            impressions=Sum("impressions"),
            clicks=Sum("clicks"),
        )
        .order_by("data")
    )
    for row in daily:
        row["data"] = row["data"].isoformat()
        # Avg CTR computed correctly = clicks/impressions (not avg of CTRs).
        i = row["impressions"] or 0
        c = row["clicks"] or 0
        row["ctr"] = round(c / i, 4) if i else 0.0

    # ── Top queries by clicks ───────────────────────────────────────
    # Avg position weighted by impressions: Σ(position × imp) / Σ(imp).
    # Computed in Python after the aggregate-only query because
    # mixing ORM aggregation with division-by-aggregate requires
    # NULLIF + Coalesce wrappers that get ugly fast. N is small
    # (≤ 30 queries × ≤ days of history) so the follow-up scans
    # are cheap.
    top_queries_raw = list(
        MetricaSEOQuery.objects.filter(data__gte=since)
        .values("query")
        .annotate(
            impressions=Sum("impressions"),
            clicks=Sum("clicks"),
        )
        .order_by("-clicks", "-impressions")[:30]
    )
    top_queries = []
    for row in top_queries_raw:
        rows = list(
            MetricaSEOQuery.objects.filter(
                data__gte=since, query=row["query"]
            ).values_list("position", "impressions")
        )
        total_imp = sum(i or 0 for _, i in rows) or 1
        weighted = sum((p or 0) * (i or 0) for p, i in rows) / total_imp
        row["avg_position"] = round(weighted, 2)
        top_queries.append(row)

    # ── Top pages by clicks ─────────────────────────────────────────
    top_pages = list(
        MetricaSEOQuery.objects.filter(data__gte=since)
        .values("page")
        .annotate(
            impressions=Sum("impressions"),
            clicks=Sum("clicks"),
        )
        .order_by("-clicks", "-impressions")[:30]
    )

    # ── Latest CWV per (url, category) ──────────────────────────────
    # Python-side dedup so it works on Postgres + SQLite.
    latest_cwv: dict[tuple, dict] = {}
    for r in MetricaCWV.objects.order_by("-data").values(
        "url",
        "category",
        "data",
        "score",
        "lcp_ms",
        "inp_ms",
        "cls",
        "fcp_ms",
        "ttfb_ms",
    ):
        key = (r["url"], r["category"])
        latest_cwv.setdefault(key, r)
    cwv = list(latest_cwv.values())
    for r in cwv:
        r["data"] = r["data"].isoformat()

    # ── Last update timestamp per source ───────────────────────────
    last_gsc = MetricaSEOQuery.objects.aggregate(m=Max("data"))["m"]
    last_psi = MetricaCWV.objects.aggregate(m=Max("data"))["m"]

    return Response(
        {
            "window": {
                "days": days,
                "since": since.isoformat(),
                "until": today.isoformat(),
            },
            "last_updated": {
                "now": timezone.now().isoformat(),
                "gsc": last_gsc.isoformat() if last_gsc else None,
                "psi": last_psi.isoformat() if last_psi else None,
            },
            "daily_kpis": daily,
            "top_queries": top_queries,
            "top_pages": top_pages,
            "cwv": cwv,
        }
    )
