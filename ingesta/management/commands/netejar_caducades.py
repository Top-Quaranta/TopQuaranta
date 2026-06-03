import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from ingesta.caducitat import caducitat_cutoff
from music.models import Canco

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete unverified tracks older than 12 months."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        # Shared cutoff source (#131) — the same `caducitat_cutoff()` the
        # `enriquir_spotify` pending guard reads, so the enrich pending
        # pool stays EXACTLY the survivors of this purge. Never recompute
        # the 365-day boundary inline.
        cutoff = caducitat_cutoff()

        # `activa=True` (added May 2026): only purge rows that are still
        # in the active pool — i.e. unverified pending review tracks
        # that nobody has touched within `DIES_CADUCITAT`. Tracks
        # rejected via `rebutjar_canco` carry `activa=False` and must
        # stay forever as a permanent dedup marker, so the next
        # `_create_track` / `_upsert_track` doesn't re-ingest them
        # when Deezer offers the same recording under a different
        # `deezer_id` (re-issue) or a different album. Without this
        # filter the cron silently erased the rejection trail after
        # one year and the song reappeared in the pipeline.
        qs = Canco.objects.filter(
            verificada=False, activa=True, data_llancament__lt=cutoff
        )
        count = qs.count()

        if count == 0:
            self.stdout.write("Cap cançó caducada per esborrar.")
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN — s'esborrarien {count} cançons (data_llancament < {cutoff})"
                )
            )
            return

        with transaction.atomic():
            deleted, _ = qs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Esborrades {deleted} cançons caducades (data_llancament < {cutoff})"
            )
        )
