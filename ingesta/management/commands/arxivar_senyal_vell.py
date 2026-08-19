"""Φ6: archive SenyalDiari rows older than the retention window.

Exports old rows to `/home/topquaranta/archive/senyal-<year>.csv.gz`
and deletes them from the live DB. See `docs/ops/runbook.md` (retention) for the
policy this implements.

Scheduled quarterly via cron; see README / CLAUDE.md §3.
"""

import csv
import gzip
import os
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ranking.models import SenyalDiari

# Columns to include in the archive. Chosen to match the table schema
# faithfully — a researcher should be able to rebuild a queryable copy
# from these files alone.
ARCHIVE_COLUMNS = [
    "id",
    "canco_id",
    "data",
    "lastfm_playcount",
    "lastfm_listeners",
    "lastfm_returned_track",
    "lastfm_returned_artista",
    "corregit",
    "error",
    "error_msg",
    "created_at",
]

# 2 years before today. Kept as a constant so the retention threshold
# is visible next to the command that uses it (and in tests).
RETENTION_DAYS = 730

DEFAULT_ARCHIVE_DIR = "/home/topquaranta/archive"


class Command(BaseCommand):
    help = (
        "Archive SenyalDiari rows older than the retention window "
        "to gzipped CSV and delete them from the live DB."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--archive-dir",
            default=DEFAULT_ARCHIVE_DIR,
            help=f"Output directory for archive files (default: {DEFAULT_ARCHIVE_DIR}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count rows that would be archived without writing or deleting anything.",
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            default=RETENTION_DAYS,
            help=f"Keep rows whose data is within this many days (default: {RETENTION_DAYS}).",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        retention_days: int = options["retention_days"]
        archive_dir = Path(options["archive_dir"])

        cutoff = timezone.now().date() - timedelta(days=retention_days)
        qs = SenyalDiari.objects.filter(data__lt=cutoff)
        total = qs.count()
        self.stdout.write(
            f"Cutoff: {cutoff} — {total} SenyalDiari rows older than "
            f"{retention_days} days"
        )

        if total == 0:
            self.stdout.write("Nothing to archive.")
            return

        # Group rows by calendar year of `data` so each archive file
        # corresponds to a full year.
        rows_by_year: dict[int, list[SenyalDiari]] = defaultdict(list)
        for row in qs.order_by("data", "id").iterator():
            rows_by_year[row.data.year].append(row)

        for year in sorted(rows_by_year):
            rows = rows_by_year[year]
            out_path = archive_dir / f"senyal-{year}.csv.gz"
            self.stdout.write(f"  {year}: {len(rows)} rows → {out_path}")

            if dry_run:
                continue

            archive_dir.mkdir(parents=True, exist_ok=True)

            # Append to an existing file if it's already there from a
            # prior run (e.g. late arrivals). CSV with header if new.
            is_new = not out_path.exists()
            tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
            with gzip.open(tmp_path, "wt", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=ARCHIVE_COLUMNS)
                if is_new:
                    writer.writeheader()
                else:
                    # Copy existing content first so we append to the
                    # same stream. Necessary because gzip doesn't have
                    # safe concatenation for our CSV.
                    with gzip.open(out_path, "rt", newline="") as existing:
                        for line in existing:
                            fh.write(line)
                for row in rows:
                    writer.writerow({c: getattr(row, c) for c in ARCHIVE_COLUMNS})
                fh.flush()
                os.fsync(fh.fileno())

            # Atomic swap so a crash leaves either the old file or the
            # new one — never a truncated partial.
            tmp_path.replace(out_path)

            # Only after the gzip is durable do we delete the DB rows.
            ids = [row.id for row in rows]
            with transaction.atomic():
                deleted, _ = SenyalDiari.objects.filter(id__in=ids).delete()
            self.stdout.write(f"    archived + deleted {deleted} rows")

        self.stdout.write(
            self.style.SUCCESS(f"Done. {total} rows archived + deleted total.")
        )
