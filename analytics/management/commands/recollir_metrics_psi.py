"""Daily PageSpeed Insights snapshot.

Polls PSI's `runPagespeed` once per (URL × strategy) for a curated
list of representative public pages, both Mobile and Desktop. Writes
one row per (date, url, category) into `MetricaCWV`.

PSI's free tier: 25 000 queries/day. We use ~12/day (6 URLs × 2
strategies). Plenty of headroom.

Settings:
  PSI_API_KEY — Google Cloud API key restricted to PSI API.

URLs tracked (representative SPA pages — keeping the surface narrow
so a budget regression in any one of them is visible):
  /, /top, /artistes, /mapa,
  /artista/<top-1-by-cancons>, /canco/<top-1-trending>
"""

from __future__ import annotations

import datetime
import logging
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from analytics.models import MetricaCWV
from music.models import Artista, Canco

logger = logging.getLogger(__name__)

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
TIMEOUT = 90


def _representative_urls() -> list[str]:
    """Pick the URLs that matter most. Hardcoded entry points + one
    'live' representative artiste/cançó so a regression on the
    detail-page templates is visible.

    Choice rationale: the most-followed artiste tends to attract the
    most search traffic, so its detail page is the highest-leverage
    target for CWV regressions. Same for the most recent verified
    cançó (likely the one being indexed today)."""
    from django.conf import settings
    from django.db.models import Count, Q

    base = settings.SITE_URL
    urls = [
        f"{base}/",
        f"{base}/top",
        f"{base}/artistes",
        f"{base}/mapa",
    ]
    a = (
        Artista.objects.public()
        .annotate(
            n_c=Count(
                "cancons",
                filter=Q(cancons__verificada=True, cancons__activa=True),
                distinct=True,
            )
        )
        .order_by("-n_c", "nom")
        .first()
    )
    if a:
        urls.append(f"{base}/artista/{a.slug}")
    c = (
        Canco.objects.filter(verificada=True, activa=True)
        .order_by("-data_llancament")
        .first()
    )
    if c:
        urls.append(f"{base}/canco/{c.slug}")
    return urls


def _fetch_psi(url: str, strategy: str, api_key: str) -> dict | None:
    params = {
        "url": url,
        "strategy": strategy,  # "mobile" | "desktop"
        "category": "performance",
        "key": api_key,
    }
    try:
        r = requests.get(PSI_ENDPOINT, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("psi: %s %s failed: %s", strategy, url, exc)
        return None
    if not r.ok:
        logger.warning(
            "psi: %s %s HTTP %s: %s", strategy, url, r.status_code, r.text[:200]
        )
        return None
    return r.json()


def _extract(data: dict) -> dict:
    """Pull the metrics we care about from PSI's response."""
    out: dict = {"raw": data.get("loadingExperience") or {}}
    lh = data.get("lighthouseResult") or {}
    cats = lh.get("categories") or {}
    audits = lh.get("audits") or {}
    perf = cats.get("performance") or {}
    out["score"] = (
        round(float(perf.get("score") or 0) * 100)
        if perf.get("score") is not None
        else None
    )

    def _ms(audit_name: str) -> int | None:
        a = audits.get(audit_name) or {}
        v = a.get("numericValue")
        return int(round(v)) if v is not None else None

    out["lcp_ms"] = _ms("largest-contentful-paint")
    out["inp_ms"] = _ms("interaction-to-next-paint")
    out["fcp_ms"] = _ms("first-contentful-paint")
    out["ttfb_ms"] = _ms("server-response-time")
    cls = audits.get("cumulative-layout-shift") or {}
    cls_v = cls.get("numericValue")
    out["cls"] = float(cls_v) if cls_v is not None else None
    return out


class Command(BaseCommand):
    help = "Recull les Core Web Vitals via PSI per a les URLs principals."

    def handle(self, *args, **opts):
        api_key = getattr(settings, "PSI_API_KEY", None)
        if not api_key:
            self.stdout.write(self.style.WARNING("PSI_API_KEY no configurat."))
            return

        today = datetime.date.today()
        urls = _representative_urls()
        ok = 0
        for url in urls:
            for strategy in ("mobile", "desktop"):
                data = _fetch_psi(url, strategy, api_key)
                if not data:
                    continue
                fields = _extract(data)
                with transaction.atomic():
                    MetricaCWV.objects.update_or_create(
                        data=today,
                        url=url[:400],
                        category=strategy,
                        defaults=fields,
                    )
                ok += 1
                self.stdout.write(
                    f"  {strategy:8s} {url} → score={fields.get('score')}"
                )
                # PSI limit is 400 req/100s; we use 12 calls total
                # so this is mostly courtesy.
                time.sleep(0.5)

        self.stdout.write(
            self.style.SUCCESS(f"PSI snapshot {today}: {ok} rows persisted.")
        )
