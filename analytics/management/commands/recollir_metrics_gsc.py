"""Daily Google Search Console snapshot.

Pulls the previous full UTC day's `searchanalytics.query` for the
verified domain property `sc-domain:topquaranta.cat`. Writes one
row per (date, query, page) into `MetricaSEOQuery`.

Why "yesterday" not "today": GSC data is delayed ~2 days. Pulling
T-2 gives us a complete day; today's row would be empty/partial.

The cron is idempotent — `update_or_create` on the unique
(data, query, page) key — so re-runs on the same day overwrite
that day's slice without duplicating.

Per-call cost: 1 search-analytics request, returns ≤ 25 000 rows
of (query, page) pairs. Way more than we ever generate.

Settings:
  GSC_SERVICE_ACCOUNT_FILE — path to the SA JSON key.
  GSC_SITE_URL             — `sc-domain:topquaranta.cat` for a
                             DNS-TXT-verified domain property.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from analytics.models import MetricaSEOQuery

logger = logging.getLogger(__name__)

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class Command(BaseCommand):
    help = "Recull el snapshot diari de Google Search Console."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Specific YYYY-MM-DD to fetch (default: T-2 UTC).",
        )
        parser.add_argument(
            "--max-rows",
            type=int,
            default=25_000,
            help="Cap rows per call (GSC max is 25 000).",
        )

    def handle(self, *args, **opts):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        sa_file = getattr(settings, "GSC_SERVICE_ACCOUNT_FILE", None)
        site_url = getattr(settings, "GSC_SITE_URL", None)
        if not sa_file or not Path(sa_file).exists():
            self.stdout.write(
                self.style.WARNING(
                    "GSC_SERVICE_ACCOUNT_FILE no configurat o inexistent. "
                    "Ometent la passada."
                )
            )
            return
        if not site_url:
            self.stdout.write(self.style.WARNING("GSC_SITE_URL no configurat."))
            return

        creds = service_account.Credentials.from_service_account_file(
            sa_file, scopes=GSC_SCOPES
        )
        svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

        target_date = opts.get("date")
        if target_date:
            day = datetime.date.fromisoformat(target_date)
        else:
            day = datetime.date.today() - datetime.timedelta(days=2)

        body = {
            "startDate": day.isoformat(),
            "endDate": day.isoformat(),
            "dimensions": ["query", "page"],
            "rowLimit": int(opts["max_rows"]),
            "dataState": "all",
        }
        try:
            resp = svc.searchanalytics().query(siteUrl=site_url, body=body).execute()
        except Exception as exc:  # noqa: BLE001
            # Most common: SA not yet added as a property user.
            self.stdout.write(
                self.style.ERROR(f"GSC searchanalytics call failed: {exc}")
            )
            logger.exception("GSC fetch failed")
            return

        rows = resp.get("rows") or []
        ok = 0
        with transaction.atomic():
            for r in rows:
                keys = r.get("keys") or []
                if len(keys) != 2:
                    continue
                query, page = keys
                MetricaSEOQuery.objects.update_or_create(
                    data=day,
                    query=(query or "")[:200],
                    page=(page or "")[:400],
                    defaults={
                        "impressions": int(r.get("impressions") or 0),
                        "clicks": int(r.get("clicks") or 0),
                        "ctr": float(r.get("ctr") or 0.0),
                        "position": float(r.get("position") or 0.0),
                    },
                )
                ok += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"GSC snapshot {day}: {ok} (query, page) rows persisted."
            )
        )
