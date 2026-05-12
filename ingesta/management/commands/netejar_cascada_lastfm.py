"""One-shot cleanup of pendent → * edges in ArtistaLastfmSimilar.

The discovery cron (`obtenir_metadata_lastfm`) used to process pendent
artistes as similar sources, which inflated the backlog with edges
pendent → pendent that did not reflect approved-tier recommendations.
The cron was tightened on 2026-05-12 to only walk approved sources;
this command sweeps the historical residue.

Usage:
    ./manage.py netejar_cascada_lastfm --dry-run
    ./manage.py netejar_cascada_lastfm

The dry-run mode reports counts without writing. The real run wraps
the delete + recount in a single transaction and reports the
before/after distribution of `nb_similars_lastfm > 0` across pendents.
"""

from __future__ import annotations

import csv
import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from music.models import Artista, ArtistaLastfmSimilar


class Command(BaseCommand):
    help = "Delete ArtistaLastfmSimilar edges where source.aprovat=False."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report counts and exit without writing.",
        )

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]

        to_delete = ArtistaLastfmSimilar.objects.filter(source__aprovat=False)
        edges_to_delete = to_delete.count()
        affected_target_ids = set(to_delete.values_list("target_id", flat=True))

        # Snapshot the "before" state: how many pendents currently
        # carry nb_similars_lastfm > 0?
        pendents_with_signal_before = (
            Artista.objects.filter(aprovat=False, nb_similars_lastfm__gt=0).count()
        )
        total_edges_before = ArtistaLastfmSimilar.objects.count()

        self.stdout.write(
            f"Edges total before:                       {total_edges_before}"
        )
        self.stdout.write(
            f"Edges with source.aprovat=False (to del): {edges_to_delete}"
        )
        self.stdout.write(
            f"Distinct affected target artistes:        {len(affected_target_ids)}"
        )
        self.stdout.write(
            f"Pendents amb nb_similars_lastfm>0 BEFORE: {pendents_with_signal_before}"
        )

        # Recovery backup: serialise the edges we're about to drop
        # to a timestamped CSV under BASE_DIR/data/. Reading it back
        # is straightforward (csv.DictReader → bulk_create). Path is
        # logged in both dry-run and real-run for traceability.
        iso = datetime.date.today().isoformat()
        backup_dir = Path(settings.BASE_DIR) / "data"
        backup_path = backup_dir / f"cleanup_cascada_{iso}.csv"
        self.stdout.write(f"Backup CSV path:                          {backup_path}")

        if dry_run:
            self.stdout.write(self.style.NOTICE("--dry-run: no writes (CSV not created)."))
            return

        backup_dir.mkdir(parents=True, exist_ok=True)
        with backup_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["source_id", "source_nom", "target_id", "target_nom", "match"])
            rows_iter = (
                to_delete.select_related("source", "target")
                .values_list(
                    "source_id", "source__nom", "target_id", "target__nom", "match"
                )
                .iterator(chunk_size=2000)
            )
            for row in rows_iter:
                writer.writerow(row)
        self.stdout.write(f"Backup written: {backup_path}")

        with transaction.atomic():
            deleted, _ = to_delete.delete()
            # Recount cached nb_similars_lastfm on every affected
            # artista. Iterating one-by-one keeps the SQL simple and
            # the artista list is bounded (~tens of thousands).
            for tid in affected_target_ids:
                count = ArtistaLastfmSimilar.objects.filter(target_id=tid).count()
                Artista.objects.filter(pk=tid).update(nb_similars_lastfm=count)

        pendents_with_signal_after = (
            Artista.objects.filter(aprovat=False, nb_similars_lastfm__gt=0).count()
        )
        total_edges_after = ArtistaLastfmSimilar.objects.count()

        self.stdout.write(self.style.SUCCESS(f"Deleted edges: {deleted}"))
        self.stdout.write(
            f"Edges total after:                        {total_edges_after}"
        )
        self.stdout.write(
            f"Pendents amb nb_similars_lastfm>0 AFTER:  {pendents_with_signal_after}"
        )
        self.stdout.write(
            f"Delta (pendents that dropped to 0):       "
            f"{pendents_with_signal_before - pendents_with_signal_after}"
        )
