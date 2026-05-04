"""Daily ingest of engagement metrics from each social platform.

Runs at 22:30 UTC (a touch before `snapshot_pipeline` at 23:00) so
the staff analytics dashboard sees fresh numbers each morning.

Two passes:

1. **Per-post engagement**: walks every `SocialPost` published in
   the last `LOOKBACK_DAYS` (30 by default — the engagement curve
   is essentially flat after that on our scale), and asks the
   matching client for `get_post_metrics()`. Results upserted into
   `MetricaSocialPost(socialpost, data=today)` so we keep one row
   per (post, day) — the time series shows the engagement curve.

2. **Per-platform account stats**: one call per platform via
   `get_account_stats()` to capture followers / posts / members.
   Stored in `MetricaSocialPlatform(data, platform, metric)`,
   one row per metric so new KPIs ship without a schema change.

Failure mode: every external call is wrapped in `try/except`.
Analytics MUST NOT break a deploy or a publish, and the cron is
idempotent — a transient network hiccup is forgotten on the next
night's run. We use the shared `SingletonLock` so two parallel
crons can't double-spend rate-limit budgets on the IG API.
"""

from __future__ import annotations

import datetime
import logging
from typing import Callable

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from analytics.models import MetricaSocialPlatform, MetricaSocialPost
from music.locks import SingletonLock
from social import (
    bluesky_client,
    instagram_client,
    mastodon_client,
    telegram_client,
)
from social.models import SocialPost

logger = logging.getLogger(__name__)

# How far back we keep refreshing per-post counters. Anything older
# is essentially frozen — recomputing it daily wastes API budget.
LOOKBACK_DAYS = 30

# How we extract the platform-side identifier needed by the metric
# call. Keys mirror `SocialPost.PLATFORM_*`. Returning `None` from
# an extractor signals "no usable id, skip this row" so the cron
# doesn't blow up on legacy rows from before we started saving the
# external id consistently.
ExtractorFn = Callable[[SocialPost], str | None]
MetricFn = Callable[[str], dict]


def _ig_id(post: SocialPost) -> str | None:
    return post.instagram_media_id or None


def _mastodon_id(post: SocialPost) -> str | None:
    meta = post.metadata or {}
    return meta.get("external_id") or post.instagram_media_id or None


def _bluesky_uri(post: SocialPost) -> str | None:
    meta = post.metadata or {}
    return meta.get("external_id") or None


def _telegram_id(post: SocialPost) -> str | None:
    meta = post.metadata or {}
    msg_ids = meta.get("message_ids") or []
    return str(msg_ids[0]) if msg_ids else None


# Map: platform value → (extractor, metric_fn). The metric_fn is
# called via a thin lambda so `patch("social.X.get_post_metrics",
# …)` in tests bites — we look up the attribute on the module at
# call time, not at import time.
PLATFORM_HANDLERS: dict[str, tuple[ExtractorFn, MetricFn]] = {
    SocialPost.PLATFORM_INSTAGRAM_FEED: (
        _ig_id,
        lambda mid: instagram_client.get_post_metrics(mid),
    ),
    SocialPost.PLATFORM_INSTAGRAM_STORY: (
        _ig_id,
        lambda mid: instagram_client.get_post_metrics(mid, is_story=True),
    ),
    SocialPost.PLATFORM_MASTODON: (
        _mastodon_id,
        lambda sid: mastodon_client.get_status_metrics(sid),
    ),
    SocialPost.PLATFORM_BLUESKY: (
        _bluesky_uri,
        lambda uri: bluesky_client.get_post_metrics(uri),
    ),
    SocialPost.PLATFORM_TELEGRAM: (
        _telegram_id,
        lambda mid: telegram_client.get_post_metrics(mid),
    ),
    # Newsletter has no per-post engagement endpoint (we'd need
    # Brevo's /v3/transactionalEmails/statistics with per-message
    # tracking enabled). Skipped for now — handled at the platform
    # level by `directori_visibles` + `newsletter_subscriptors` in
    # snapshot_pipeline.
}

# Account-level stat fetchers per platform. Same late-binding
# rationale as above so test patches see the mock.
ACCOUNT_STATS: dict[str, Callable[[], dict]] = {
    "instagram": lambda: instagram_client.get_account_stats(),
    "mastodon": lambda: mastodon_client.get_account_stats(),
    "bluesky": lambda: bluesky_client.get_account_stats(),
    "telegram": lambda: telegram_client.get_account_stats(),
}


class Command(BaseCommand):
    help = (
        "Recull les mètriques d'engagement de cada xarxa social per "
        "a les publicacions dels darrers 30 dies."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--lookback",
            type=int,
            default=LOOKBACK_DAYS,
            help="Dies cap enrere de SocialPost a refrescar (default 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No escriguis res; només mostra què faria.",
        )

    def handle(self, *args, **opts) -> None:
        # Same lock family as the other "external API + DB write"
        # crons so we never run two of them concurrently on a 4 GB
        # box.
        with SingletonLock("analytics_metrics_social"):
            self._run(opts)

    def _run(self, opts) -> None:
        today = timezone.localdate()
        since_dt = timezone.now() - datetime.timedelta(days=int(opts["lookback"]))
        dry = bool(opts.get("dry_run"))

        # ── per-post engagement ─────────────────────────────────
        qs = SocialPost.objects.filter(
            status=SocialPost.STATUS_PUBLICAT,
            published_at__gte=since_dt,
        ).order_by("-published_at")
        n_total = qs.count()
        self.stdout.write(f"posts publicats darrers {opts['lookback']} dies: {n_total}")

        ok = 0
        skipped = 0
        errored = 0
        for post in qs.iterator():
            handler = PLATFORM_HANDLERS.get(post.platform)
            if handler is None:
                skipped += 1
                continue
            extractor, fetch = handler
            ext_id = extractor(post)
            if not ext_id:
                skipped += 1
                continue
            try:
                metrics = fetch(ext_id)
            except Exception as exc:  # noqa: BLE001 — fail-open per cron
                # WARNING (not ERROR): a transient hiccup on a third
                # party shouldn't dirty errors.log and trip the
                # `tq-health --email-on-fail` watchdog. The cron is
                # idempotent — next night's run picks it up again.
                logger.warning(
                    "metrics fetch failed for %s pk=%s ext=%s: %s",
                    post.platform,
                    post.pk,
                    ext_id,
                    exc,
                )
                errored += 1
                continue
            if dry:
                self.stdout.write(f"  · DRY {post.platform} pk={post.pk} → {metrics}")
                ok += 1
                continue
            with transaction.atomic():
                MetricaSocialPost.objects.update_or_create(
                    socialpost=post,
                    data=today,
                    defaults={
                        "likes": int(metrics.get("likes") or 0),
                        "replies": int(metrics.get("replies") or 0),
                        "shares": int(metrics.get("shares") or 0),
                        "reach": int(metrics.get("reach") or 0),
                        "impressions": int(metrics.get("impressions") or 0),
                        "clicks": int(metrics.get("clicks") or 0),
                        "raw": metrics.get("raw") or {},
                    },
                )
            ok += 1

        # ── per-platform account stats ──────────────────────────
        for platform, fetch_acct in ACCOUNT_STATS.items():
            try:
                stats = fetch_acct()
            except Exception as exc:  # noqa: BLE001
                # See WARNING rationale above (per-post block).
                logger.warning("account stats fetch failed for %s: %s", platform, exc)
                continue
            for metric_name, value in stats.items():
                if metric_name == "raw":
                    continue
                try:
                    valor = int(value)
                except (TypeError, ValueError):
                    continue
                if dry:
                    self.stdout.write(f"  · DRY {platform}/{metric_name}={valor}")
                    continue
                with transaction.atomic():
                    MetricaSocialPlatform.objects.update_or_create(
                        data=today,
                        platform=platform,
                        metric=metric_name,
                        defaults={
                            "valor": valor,
                            "raw": stats.get("raw") or {},
                        },
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"social metrics: ok={ok} skipped={skipped} errored={errored}"
            )
        )
