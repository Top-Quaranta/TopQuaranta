"""Pull Bing Webmaster metrics (mirror of `recollir_metrics_gsc`).

Bing surfaces signals GSC does not, above all INBOUND LINK COUNTS
(authority). The Bing Webmaster API is a thin JSON REST surface:

    https://ssl.bing.com/webmaster/api.svc/json/<Method>?apikey=<key>&siteUrl=<siteUrl>

Quirks the parser handles:
  * Every response wraps its payload in a top-level `"d"` key.
  * Dates arrive as Microsoft `/Date(ms)/` strings.
  * `AvgClickPosition` / `AvgImpressionPosition` are returned ×10
    (integers), so we divide by 10.

Auth: a single `BING_WEBMASTER_API_KEY`, read from settings exactly like
the GSC credentials. Missing key -> log + clean skip (so CI and local
runs without the secret stay green). The apikey and the full request URL
are NEVER logged (they would leak the secret); only the method name is.

If the configured site is not a verified property, the command STOPS
with a clear error rather than inventing data.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime
import logging
import re

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from analytics.models import (
    MetricaBingCrawl,
    MetricaBingLinks,
    MetricaBingPage,
    MetricaBingQuery,
    MetricaBingTraffic,
)

logger = logging.getLogger(__name__)

_BASE = "https://ssl.bing.com/webmaster/api.svc/json"
_TIMEOUT = 30
_DATE_RE = re.compile(r"/Date\((\d+)")


def _parse_bing_date(value) -> datetime.date | None:
    """`/Date(1700000000000)/` (UTC ms) -> date. None if unparseable."""
    if not value or not isinstance(value, str):
        return None
    m = _DATE_RE.search(value)
    if not m:
        return None
    try:
        ms = int(m.group(1))
        return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).date()
    except (ValueError, OverflowError, OSError):
        return None


def _pos(value) -> float:
    """Bing returns Avg*Position multiplied by 10."""
    try:
        return float(value or 0) / 10.0
    except (TypeError, ValueError):
        return 0.0


def _envelope(payload):
    """Unwrap the `"d"` envelope. Bing returns either a bare list under
    `d` or a dict whose values include the list; normalise to a list."""
    d = payload.get("d") if isinstance(payload, dict) else None
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        # Some methods nest the array one level deeper.
        for v in d.values():
            if isinstance(v, list):
                return v
        return [d]
    return []


class Command(BaseCommand):
    help = (
        "Recull mètriques de Bing Webmaster (tràfic, queries, pàgines, "
        "crawl, enllaços entrants). Skip net sense BING_WEBMASTER_API_KEY."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--submit-sitemap",
            action="store_true",
            help="(opcional) Submission única del sitemap-index. Dry-run "
            "per defecte; només informa.",
        )

    # ── HTTP ────────────────────────────────────────────────────────
    def _call(self, method: str, key: str, site_url: str, **extra):
        """GET one Bing method. Returns the unwrapped list, or None on
        failure (fail-open). Logs ONLY the method name on error, never
        the apikey or the URL."""
        params = {"apikey": key, "siteUrl": site_url, **extra}
        try:
            resp = requests.get(f"{_BASE}/{method}", params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            return _envelope(resp.json())
        except Exception:  # noqa: BLE001
            # Do NOT include the exception URL/params: requests embeds the
            # full query string (with apikey) in some error messages.
            self.stdout.write(self.style.ERROR(f"Bing call failed: method={method}"))
            logger.warning("Bing API call failed (method=%s)", method)
            return None

    def _resolve_site(self, key: str, configured: str) -> str:
        """Validate the configured site against GetUserSites. STOP if it
        is not a verified property (don't invent data). The live API
        exposes the property list under `GetUserSites` (not `GetSites`,
        which 404s); confirmed against the real endpoint 2026-06-14."""
        sites = self._call("GetUserSites", key, configured)
        if sites is None:
            raise CommandError("Bing GetUserSites failed; no es pot validar el lloc.")

        def _norm(u: str) -> str:
            return (u or "").rstrip("/").lower()

        target = _norm(configured)
        for s in sites:
            url = s.get("Url") or s.get("url") or ""
            verified = s.get("IsVerified", s.get("isVerified", False))
            if _norm(url) == target and verified:
                return url
        raise CommandError(
            f"Cap propietat verificada de Bing coincideix amb {configured!r}. "
            "Verifica el lloc a Bing Webmaster Tools abans d'executar."
        )

    # ── handle ──────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        key = getattr(settings, "BING_WEBMASTER_API_KEY", "") or ""
        if not key:
            self.stdout.write(
                self.style.WARNING(
                    "BING_WEBMASTER_API_KEY no configurada. Ometent (skip net)."
                )
            )
            return

        configured = getattr(settings, "BING_WEBMASTER_SITE_URL", "") or getattr(
            settings, "SITE_URL", ""
        )
        if not configured:
            self.stdout.write(self.style.WARNING("Cap siteUrl de Bing. Ometent."))
            return

        site_url = self._resolve_site(key, configured)
        today = datetime.date.today()

        n = 0
        n += self._traffic(key, site_url)
        n += self._queries(key, site_url, today)
        n += self._pages(key, site_url, today)
        n += self._crawl(key, site_url)
        n += self._links(key, site_url, today)

        if opts.get("submit_sitemap"):
            self.stdout.write(
                self.style.NOTICE(
                    "DRY-RUN submit-sitemap: NO s'envia. IndexNow ja cobreix "
                    "Bing; submission manual només si cal."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(f"Bing: {n} files escrites/actualitzades.")
        )

    # ── per-method writers ────────────────────────────────────────────
    def _traffic(self, key, site_url) -> int:
        rows = self._call("GetRankAndTrafficStats", key, site_url)
        if not rows:
            return 0
        ok = 0
        with transaction.atomic():
            for r in rows:
                day = _parse_bing_date(r.get("Date"))
                if day is None:
                    continue
                MetricaBingTraffic.objects.update_or_create(
                    data=day,
                    defaults={
                        "clicks": int(r.get("Clicks") or 0),
                        "impressions": int(r.get("Impressions") or 0),
                    },
                )
                ok += 1
        return ok

    def _queries(self, key, site_url, day) -> int:
        rows = self._call("GetQueryStats", key, site_url)
        if not rows:
            return 0
        ok = 0
        with transaction.atomic():
            for r in rows:
                q = (r.get("Query") or "").strip()
                if not q:
                    continue
                MetricaBingQuery.objects.update_or_create(
                    data=day,
                    query=q[:200],
                    defaults={
                        "clicks": int(r.get("Clicks") or 0),
                        "impressions": int(r.get("Impressions") or 0),
                        "avg_click_position": _pos(r.get("AvgClickPosition")),
                        "avg_impression_position": _pos(r.get("AvgImpressionPosition")),
                    },
                )
                ok += 1
        return ok

    def _pages(self, key, site_url, day) -> int:
        rows = self._call("GetPageStats", key, site_url)
        if not rows:
            return 0
        ok = 0
        with transaction.atomic():
            for r in rows:
                page = (r.get("Query") or r.get("Page") or "").strip()
                if not page:
                    continue
                MetricaBingPage.objects.update_or_create(
                    data=day,
                    page=page[:400],
                    defaults={
                        "clicks": int(r.get("Clicks") or 0),
                        "impressions": int(r.get("Impressions") or 0),
                        "avg_click_position": _pos(r.get("AvgClickPosition")),
                        "avg_impression_position": _pos(r.get("AvgImpressionPosition")),
                    },
                )
                ok += 1
        return ok

    def _crawl(self, key, site_url) -> int:
        rows = self._call("GetCrawlStats", key, site_url)
        if not rows:
            return 0
        ok = 0
        with transaction.atomic():
            for r in rows:
                day = _parse_bing_date(r.get("Date"))
                if day is None:
                    continue
                MetricaBingCrawl.objects.update_or_create(
                    data=day,
                    defaults={
                        "crawled_pages": int(r.get("CrawledPages") or 0),
                        "in_links": int(r.get("InLinks") or 0),
                        "crawl_errors": int(r.get("CrawlErrors") or 0),
                        "blocked_by_robots": int(r.get("BlockedByRobotsTxtPages") or 0),
                    },
                )
                ok += 1
        return ok

    def _links(self, key, site_url, day) -> int:
        """Inbound-link count (authority). `GetUrlLinks` REQUIRES a
        `link` param (the URL whose inbound links we want; we pass the
        site root) and returns `{"d": {"Details": [...], "TotalPages":
        N}}` — `_envelope` unwraps `Details`. Without `link` the API
        400s (confirmed live 2026-06-14)."""
        rows = self._call("GetUrlLinks", key, site_url, link=site_url)
        if rows is None:
            return 0
        domains = set()
        for r in rows:
            host = r.get("Url") or r.get("AnchorText") or ""  # fallback; never crashes
            if isinstance(host, str) and "//" in host:
                domains.add(host.split("//", 1)[1].split("/", 1)[0].lower())
        MetricaBingLinks.objects.update_or_create(
            data=day,
            defaults={
                "inbound_links": len(rows),
                "linking_domains": len(domains),
            },
        )
        return 1
