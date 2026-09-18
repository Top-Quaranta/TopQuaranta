"""Nightly retrain + rescore of the track-verification classifier.

This command is the ONLY path that writes `ml_classe` / `ml_confianca`
in bulk. Until 2026-09 the same work ran as a daemon thread inside the
gunicorn worker, kicked off by staff clicks; it kept dying unnoticed and
left the staff queue sorted by stale scores. See `music.ml.recalcular_ml`
for the measurements behind the move.

    python manage.py recalcular_ml [--limit N] [--entrenar auto|sempre|mai]

# Spec: docs/architecture/music.md
"""

from __future__ import annotations

import logging
import time

from django.core.management.base import BaseCommand

from music.constants import MIN_NEW_DECISIONS
from music.ml import decisions_des_de_l_ultim_recalc, recalcular_ml

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Reentrena el classificador i recalcula ml_classe/ml_confianca de "
        "les cançons pendents. Única via de reentrenament: cron nocturn "
        "amb SingletonLock, mai des d'una petició web."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument(
            "--entrenar",
            choices=("auto", "sempre", "mai"),
            default="auto",
            help=(
                "auto (per defecte): reentrena només si hi ha ≥ "
                f"{MIN_NEW_DECISIONS} decisions noves des de l'últim recalc. "
                "sempre: reentrena igualment. mai: només torna a puntuar."
            ),
        )

    def handle(self, *args, **options):
        # Exit 75 when another instance holds the lock, so `tq-run` records
        # SKIPPED_BY_LOCK and keeps the previous successful `last_run`
        # instead of pretending this tick succeeded. See `music.locks`.
        from music.locks import SingletonLock

        with SingletonLock("recalcular_ml"):
            noves = decisions_des_de_l_ultim_recalc()
            mode = options["entrenar"]
            entrenar = mode == "sempre" or (
                mode == "auto" and noves >= MIN_NEW_DECISIONS
            )

            self.stdout.write(
                f"Decisions noves des de l'últim recalc: {noves} "
                f"(llindar {MIN_NEW_DECISIONS}) · reentrenament: "
                f"{'sí' if entrenar else 'no'}"
            )
            logger.info(
                "recalcular_ml: noves=%d entrenar=%s limit=%s",
                noves,
                entrenar,
                options["limit"],
            )

            t0 = time.monotonic()
            updated = recalcular_ml(limit=options["limit"], entrenar=entrenar)
            durada = time.monotonic() - t0

            msg = f"{updated} cançons repuntuades en {durada:.0f}s."
            logger.info("recalcular_ml: %s", msg)
            self.stdout.write(self.style.SUCCESS(msg))
