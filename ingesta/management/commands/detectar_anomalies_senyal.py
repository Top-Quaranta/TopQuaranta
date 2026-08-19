"""Preventive anomaly detector for Last.fm signal.

Runs daily after `obtenir_senyal` writes the day's rows. For each
Cançó with a fresh signal, compares today's playcount delta against
the median day-to-day delta over the prior 7 days. When the delta
spikes implausibly the row is flagged `corregit=True` so the ranking
algorithm skips it (the same lever the `_detect_drift` track-name
mismatch already pulls).

This is a defence-in-depth layer for changes in Last.fm's API
behaviour we haven't anticipated:

* The 2026-05-08 incident — Last.fm's autocorrect/fallback flipped
  variant queries (live, remix, remasteritzada) onto the main studio
  recording, producing 53 cançons with 1 000-30 000 plays of phantom
  weekly delta. The track-switch guard in `algorisme._compute_weekly_plays`
  catches that specific class. This detector catches the broader case
  of "today's delta is wildly outside normal range" regardless of
  cause: a Last.fm bulk-correction, a scrape error, an autocorrect
  swap on a track that doesn't show up via `lastfm_returned_track`,
  etc.

Heuristic (deliberately conservative — false positives mean a real
spike gets ignored for 7 days, which is acceptable; false negatives
are the worse outcome):

    abs(today_delta) >= FLOOR_PLAYS                 (noise floor)
    AND
    abs(today_delta) > MULTIPLIER * max(median_baseline_delta, 1)

Defaults: FLOOR=100 (smaller absolute moves are noise on the long
tail), MULTIPLIER=20× (a track adding 20× its typical day-to-day
gain in one tick is almost certainly an artefact). Tunable via
`--floor` / `--multiplier` flags.

When triggered, the today's `SenyalDiari` row is updated:
    corregit=True
    error_msg="anomaly: delta=X median=Y"
The row stays in the DB (we don't delete signals) but is filtered
out by the ranking's `error=False, corregit=False` gate. Once the
new playcount stabilises, future days produce sensible deltas again
and the cançó re-enters the ranking organically.
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from music.locks import SingletonLock
from ranking.models import SenyalDiari

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_FLOOR = 100
DEFAULT_MULTIPLIER = 20.0


class Command(BaseCommand):
    help = (
        "Flag day-over-day anomalies in SenyalDiari (corregit=True) so the "
        "ranking algorithm skips them. Run daily after obtenir_senyal."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--data",
            type=str,
            default=None,
            help="ISO date of 'today'. Defaults to today UTC.",
        )
        parser.add_argument(
            "--lookback-days",
            type=int,
            default=DEFAULT_LOOKBACK_DAYS,
            help="How many baseline days to compute the median delta from.",
        )
        parser.add_argument(
            "--floor",
            type=int,
            default=DEFAULT_FLOOR,
            help=(
                "Absolute delta below this is never flagged. Avoids noise "
                "on long-tail tracks where small movements are normal."
            ),
        )
        parser.add_argument(
            "--multiplier",
            type=float,
            default=DEFAULT_MULTIPLIER,
            help=(
                "Today's delta must exceed this × the median baseline delta "
                "(plus the floor) to be flagged."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report flagged rows but don't update SenyalDiari.",
        )

    def handle(self, *args, **opts):
        with SingletonLock("detectar_anomalies_senyal"):
            self._run(**opts)

    def _run(
        self,
        data: str | None,
        lookback_days: int,
        floor: int,
        multiplier: float,
        dry_run: bool,
        **_kwargs,
    ) -> None:
        today = date.fromisoformat(data) if data else date.today()
        cutoff = today - timedelta(days=lookback_days + 1)

        # Pull all SenyalDiari rows in [cutoff, today] for cançons that
        # have a row exactly today. Working set is small (≤ ~3 k tracks
        # × 8 days = 24 k rows) so we materialise it.
        today_rows = SenyalDiari.objects.filter(
            data=today, lastfm_playcount__isnull=False
        ).values_list("canco_id", flat=True)
        today_canco_ids = set(today_rows)
        if not today_canco_ids:
            self.stdout.write(f"No signals for {today}; nothing to scan.")
            self.stdout.write("WORK_DONE=0")
            return

        rows = SenyalDiari.objects.filter(
            data__gte=cutoff,
            data__lte=today,
            canco_id__in=today_canco_ids,
            lastfm_playcount__isnull=False,
        ).only("id", "canco_id", "data", "lastfm_playcount", "corregit")

        by_canco: dict[int, list[SenyalDiari]] = defaultdict(list)
        for r in rows:
            by_canco[r.canco_id].append(r)

        flagged_ids: list[int] = []
        scanned = 0
        for cid, sigs in by_canco.items():
            sigs.sort(key=lambda s: s.data)
            if len(sigs) < 3:
                # Not enough history to judge — let it through.
                continue
            scanned += 1
            today_row = sigs[-1]
            if today_row.data != today or today_row.corregit:
                continue
            # Build day-to-day deltas (skip gaps where the sample is
            # missing). Each pair is ordered (older, newer).
            deltas: list[int] = []
            for prev, nxt in zip(sigs, sigs[1:]):
                if (
                    prev.lastfm_playcount is not None
                    and nxt.lastfm_playcount is not None
                    and (nxt.data - prev.data).days <= 2
                ):
                    deltas.append(nxt.lastfm_playcount - prev.lastfm_playcount)
            if len(deltas) < 2:
                continue
            today_delta = deltas[-1]
            baseline_deltas = [abs(d) for d in deltas[:-1]]
            if not baseline_deltas:
                continue
            median_baseline = statistics.median(baseline_deltas)
            threshold = multiplier * max(median_baseline, 1)
            if abs(today_delta) >= floor and abs(today_delta) > threshold:
                flagged_ids.append(today_row.id)
                logger.info(
                    "anomaly canco=%d data=%s delta=%d median=%.1f threshold=%.1f",
                    cid,
                    today_row.data.isoformat(),
                    today_delta,
                    median_baseline,
                    threshold,
                )

        n = len(flagged_ids)
        self.stdout.write(
            f"Scanned {scanned} cançons, flagged {n} anomalies "
            f"(floor={floor}, multiplier={multiplier})"
        )
        if dry_run:
            self.stdout.write("--dry-run: SenyalDiari not modified.")
            self.stdout.write(f"WORK_DONE={n}")
            return
        if flagged_ids:
            updated = SenyalDiari.objects.filter(id__in=flagged_ids).update(
                corregit=True,
                error_msg="anomaly: today's delta exceeds median baseline × "
                f"{multiplier:g}",
            )
            self.stdout.write(f"  {updated} rows marked corregit=True.")
        # WORK_DONE protocol — see docs/ops/runbook.md (WORK_DONE).
        self.stdout.write(f"WORK_DONE={n}")
