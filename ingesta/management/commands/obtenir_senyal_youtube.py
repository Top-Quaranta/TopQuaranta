"""Daily YouTube snapshot per matched track — the cheap half.

`videos.list?part=statistics` returns 50 ids for a single quota unit, so
the whole catalogue costs ~60 of the 10.000 daily units. That is the
entire reason this source is viable: discovery is rationed, polling is
not.

Writes one `SenyalYouTube` row per (canco, data) with the cumulative
`viewCount`, mirroring `obtenir_senyal`. The ranking reads 7-day deltas,
never the absolute value, so a track only starts counting once it has a
baseline — same lag as Last.fm.

Idempotent: tracks already snapshotted for the target date are skipped,
so a re-run after a partial failure costs only the missing ids.

    python manage.py obtenir_senyal_youtube [--data YYYY-MM-DD] [--dry-run]

# Spec: docs/architecture/pipeline.md
"""

from __future__ import annotations

import datetime
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ingesta.clients import youtube as yt
from music.constants import DIES_CADUCITAT
from music.models import Canco
from ranking.models import SenyalYouTube

logger = logging.getLogger(__name__)

BATCH = 50  # `videos.list` caps at 50 ids per call — and per quota unit.


class Command(BaseCommand):
    help = "Recull les visualitzacions diàries de YouTube de les cançons aparellades."

    def add_arguments(self, parser):
        parser.add_argument("--data", type=str, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts) -> None:
        if not settings.YOUTUBE_API_KEY:
            self.stdout.write(self.style.WARNING("YOUTUBE_API_KEY buit; no faig res."))
            return

        if opts["data"]:
            try:
                target = datetime.date.fromisoformat(opts["data"])
            except ValueError:
                raise CommandError(f"Data invàlida: {opts['data']}. Usa YYYY-MM-DD.")
        else:
            target = datetime.date.today()
        cutoff = target - datetime.timedelta(days=DIES_CADUCITAT)

        ja = set(
            SenyalYouTube.objects.filter(data=target).values_list("canco_id", flat=True)
        )
        pendents = list(
            Canco.objects.filter(
                activa=True, verificada=True, data_llancament__gte=cutoff
            )
            .exclude(youtube_video_id="")
            .exclude(pk__in=ja)
            .values_list("pk", "youtube_video_id")
        )
        self.stdout.write(
            f"Cançons aparellades pendents per a {target}: {len(pendents)} "
            f"(cost estimat {max(1, (len(pendents) + BATCH - 1) // BATCH)} unitats)"
        )
        if opts["dry_run"] or not pendents:
            self.stdout.write(f"WORK_DONE={0}")
            return

        ok = 0
        errors = 0
        files: list[SenyalYouTube] = []
        try:
            for i in range(0, len(pendents), BATCH):
                tros = pendents[i : i + BATCH]
                stats = yt.video_stats([vid for _, vid in tros])
                for pk, vid in tros:
                    s = stats.get(vid)
                    if s is None:
                        # The video is gone (takedown, re-upload) or the id
                        # is stale. Recorded, not silently dropped, so the
                        # daily report can surface a rising count.
                        files.append(
                            SenyalYouTube(
                                canco_id=pk,
                                data=target,
                                video_id=vid,
                                error=True,
                                error_msg=f"cap estadística per al vídeo {vid}",
                            )
                        )
                        errors += 1
                        continue
                    files.append(
                        SenyalYouTube(
                            canco_id=pk,
                            data=target,
                            video_id=vid,
                            views=s["views"],
                            likes=s["likes"],
                        )
                    )
                    ok += 1
        except yt.QuotaExhausted as exc:
            self.stdout.write(self.style.WARNING(f"Quota exhaurida: {exc}"))

        SenyalYouTube.objects.bulk_create(files, ignore_conflicts=True)
        self.stdout.write(
            self.style.SUCCESS(f"Snapshots: {ok} correctes, {errors} amb error.")
        )
        self.stdout.write(f"WORK_DONE={ok}")
