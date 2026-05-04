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

from django.db.models import Sum
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from analytics.models import MetricaEsdeveniment, MetricaPipeline
from web.api.staff._common import IsStaff


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
    social_rows = list(
        MetricaEsdeveniment.objects.filter(data__gte=since, clau="social_publicat")
        .values("dimensio_1", "dimensio_2")
        .annotate(total=Sum("comptador"))
        .order_by("-total")
    )
    social = [
        {"channel": r["dimensio_1"], "tipus": r["dimensio_2"], "total": r["total"]}
        for r in social_rows
    ]

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
    territoris_rows = (
        MetricaPipeline.objects.filter(clau="cancons_per_territori")
        .order_by("dimensio_1", "-data")
        .distinct("dimensio_1")
        .values("dimensio_1", "valor_int", "data")
    )
    territoris = [
        {
            "codi": r["dimensio_1"],
            "valor": r["valor_int"],
            "data": r["data"].isoformat(),
        }
        for r in territoris_rows
    ]

    return Response(
        {
            "window": {
                "days": days,
                "since": since.isoformat(),
                "until": today.isoformat(),
            },
            "pipeline": dict(pipeline),
            "events": dict(events),
            "pageviews": pageviews,
            "utm": utm,
            "social": social,
            "feedback": feedback,
            "territoris": territoris,
        }
    )
