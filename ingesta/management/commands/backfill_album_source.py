"""Backfill `Album.source_deezer_id` for legacy rows.

Pre-2026-05-03 albums were created without recording which Deezer
profile of the artista they came from. This command queries Deezer's
`/album/{id}` endpoint, reads `album.artist.id`, and if that id is
one of the artista's `ArtistaDeezer` rows, stores it as
`source_deezer_id`.

Idempotent and rate-limit polite (Deezer caps at ~50 reqs/sec; we
sleep 50 ms between calls). Run once after deploy:

    sudo -u topquaranta tq-run backfill_album_source

`--limit N` to bound a single invocation; `--dry-run` to preview.
"""

from __future__ import annotations

import logging
import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from ingesta.clients import deezer
from music.models import Album, ArtistaDeezer

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill Album.source_deezer_id by querying Deezer for the album owner."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cap the number of albums processed in this run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing.",
        )

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]
        limit = opts["limit"]

        # Only legacy rows: have a deezer_id but no source_deezer_id.
        # We restrict to albums whose artista has at least one
        # ArtistaDeezer (otherwise there's nothing to match against).
        qs = (
            Album.objects.filter(
                deezer_id__isnull=False,
                source_deezer_id__isnull=True,
                artista__deezer_ids__isnull=False,
            )
            .select_related("artista")
            .distinct()
            .order_by("pk")
        )
        total = qs.count()
        self.stdout.write(f"Backfill candidates: {total}")
        if limit:
            qs = qs[:limit]
            self.stdout.write(f"  Limited to: {limit}")

        ok = 0
        unmatched = 0
        errors = 0
        for i, alb in enumerate(qs.iterator(), 1):
            artista_dz_ids = set(
                ArtistaDeezer.objects.filter(artista=alb.artista).values_list(
                    "deezer_id", flat=True
                )
            )
            try:
                data = deezer._get(f"{deezer.API_BASE}/album/{alb.deezer_id}")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Deezer error for album deezer_id=%s: %s",
                    alb.deezer_id,
                    exc,
                )
                errors += 1
                time.sleep(0.05)
                continue

            if not data or not data.get("artist"):
                unmatched += 1
                time.sleep(0.05)
                continue

            owner_id = data["artist"].get("id")
            if owner_id and owner_id in artista_dz_ids:
                if not dry_run:
                    alb.source_deezer_id = owner_id
                    alb.save(update_fields=["source_deezer_id"])
                ok += 1
            else:
                # Album owner on Deezer isn't in our ArtistaDeezer set
                # — likely a legacy carry-over from a profile we've
                # since unlinked, or a stale row. Leave NULL so the
                # smart unlink defers; staff can clean up if needed.
                unmatched += 1

            if i % 100 == 0:
                self.stdout.write(
                    f"  ... {i}/{total} (ok={ok}, unmatched={unmatched}, errors={errors})"
                )
            # Rate-limit politeness — Deezer's public limit is ~50/s.
            time.sleep(0.05)

        verb = "would set" if dry_run else "set"
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {verb}={ok}, unmatched={unmatched}, errors={errors}"
            )
        )
