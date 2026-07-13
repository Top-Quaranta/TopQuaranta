"""Run Whisper LID on tracks' Deezer previews.

Processes tracks in this order:
  1. Never processed (whisper_processat_at IS NULL), with a preview URL.
  2. Optionally, tracks processed more than N days ago if
     --refresh-older-than is given.

Updates three fields:
  Canco.whisper_lang          — ISO language code (ca, es, en, …)
  Canco.whisper_p             — top-1 language probability [0, 1]
  Canco.whisper_processat_at  — timestamp of the analysis

Designed for nightly cron via `tq-run analitzar_whisper`. Heavy:
loads faster-whisper large-v3 (~1.5 GB on disk, ~3 GB RAM) once, then
~27 s per track on CPU. Don't invoke from the web process.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ingesta.clients.whisper import analyze_preview, get_model
from music.models import Canco
from music.services import auto_aprovar_per_whisper

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compute Whisper LID language + probability for tracks with a preview URL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum tracks to process in this run.",
        )
        parser.add_argument(
            "--refresh-older-than",
            type=int,
            default=None,
            help="Also re-process tracks analysed more than N days ago.",
        )
        parser.add_argument(
            "--canco-id",
            type=int,
            default=None,
            help="Single-track mode (for debugging).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be processed without downloading or writing.",
        )

    def handle(self, *args, **options):
        # Shared `"ram_heavy"` lock with `obtenir_metadata_musicbrainz`:
        # both commands together exceed the 4 GB CX22 budget (Whisper
        # large-v3 int8 ≈ 3 GB on its own). Without this mutex the
        # OOM-killer takes one of them, exit code 137. See
        # `music.locks.SingletonLock` for the exit-75 contract.
        from music.locks import SingletonLock

        with SingletonLock("ram_heavy"):
            self._run(**options)

    def _run(self, **options):
        limit = options["limit"]
        dry_run: bool = options["dry_run"]
        canco_id = options["canco_id"]
        refresh_days = options["refresh_older_than"]

        if canco_id is not None:
            qs = Canco.objects.filter(pk=canco_id)
        else:
            qs = Canco.objects.filter(
                preview_url__isnull=False,
                whisper_processat_at__isnull=True,
            ).exclude(preview_url="")
            if refresh_days is not None:
                cutoff = timezone.now() - timedelta(days=refresh_days)
                refresh_qs = Canco.objects.filter(
                    preview_url__isnull=False,
                    whisper_processat_at__lt=cutoff,
                ).exclude(preview_url="")
                qs = qs.union(refresh_qs)
            qs = qs.order_by("-created_at")

        if limit is not None:
            qs = qs[:limit]

        total = qs.count() if hasattr(qs, "count") else len(list(qs))
        self.stdout.write(f"Tracks to process: {total}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no downloads, no writes."))
            for c in list(qs)[:20]:
                self.stdout.write(
                    f"  [{c.pk}] {c.nom!r} preview={(c.preview_url or '')[:60]}…"
                )
            return

        # Pre-load the model once so per-track timing reflects pure inference.
        self.stdout.write("Loading faster-whisper large-v3 (CPU, int8)…")
        get_model()

        ok = 0
        fail = 0
        ca = 0
        non_ca = 0
        auto_ap = 0
        for i, canco in enumerate(qs, 1):
            result = analyze_preview(canco.preview_url, canco.deezer_id)
            if result is None:
                fail += 1
                # Leave whisper_processat_at NULL → retry next run.
                continue
            lang, prob, all_probs = result
            canco.whisper_lang = lang
            canco.whisper_p = prob
            canco.whisper_all_probs = all_probs
            canco.whisper_processat_at = timezone.now()
            with transaction.atomic():
                canco.save(
                    update_fields=[
                        "whisper_lang",
                        "whisper_p",
                        "whisper_all_probs",
                        "whisper_processat_at",
                    ]
                )
                # Whisper-LID gate: near-certain Catalan → auto-approve
                # now instead of queueing for staff. No-op unless the
                # track is still pending with an approved artist anchor.
                if auto_aprovar_per_whisper(canco):
                    auto_ap += 1
            ok += 1
            if lang == "ca":
                ca += 1
            else:
                non_ca += 1
            if i % 50 == 0:
                self.stdout.write(
                    f"  Processed {i}/{total}  ok={ok} fail={fail} "
                    f"ca={ca} non_ca={non_ca} auto_ap={auto_ap}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n  Done. ok={ok} fail={fail} ca={ca} non_ca={non_ca} "
                f"auto_aprovades={auto_ap} total={total}"
            )
        )
