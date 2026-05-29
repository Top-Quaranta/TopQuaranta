"""Download + transcode Deezer covers into self-hosted variants.

Fase 1 of the cover self-hosting work: pure ingestion. Reads the
stored Deezer cover URL for each entity, normalises it to the source
size, and writes webp/avif/jpg variants under `PORTADES_ROOT` via
`ingesta.portades.manager`. No DB writes, no model changes — state is
the filesystem.

Per-entity source:
  - album   → Album.deezer_id + Album.imatge_url (the Deezer cover_xl)
  - cancio  → Canco.deezer_id + Canco.album.imatge_url (album cover)
  - artista → Artista.deezer_id_principal + Artista.imatge_url

Entities without a deezer_id or without a stored image URL are
skipped. `--force` re-downloads even when the variants already exist.

# Spec: docs/architecture/portades.md
"""

from __future__ import annotations

import logging
import time

from django.core.management.base import BaseCommand, CommandError

from ingesta.portades import download_and_convert, exists
from music.models import Album, Artista, Canco

logger = logging.getLogger(__name__)

ENTITATS = ("album", "cancio", "artista")
# Be gentle with Deezer's CDN between downloads.
THROTTLE_S = 0.4
PROGRESS_EVERY = 50


class Command(BaseCommand):
    help = "Download Deezer covers and transcode them to self-hosted webp/avif/jpg variants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--entitat",
            choices=(*ENTITATS, "all"),
            default="all",
            help="Which entity to process (default: all → album, cancio, artista).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Max entities to PROCESS this run (across all entitats). Default 200.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-download even if variants already exist on disk.",
        )

    def handle(self, *args, **opts):
        entitat = opts["entitat"]
        limit = opts["limit"]
        force = opts["force"]
        if limit <= 0:
            raise CommandError("--limit must be positive")

        entitats = ENTITATS if entitat == "all" else (entitat,)
        found = failed = skipped = 0
        processed = 0

        for ent in entitats:
            for deezer_id, source_url in self._iter_candidates(ent):
                if processed >= limit:
                    break
                # Skip already-present unless forced (read-only disk check,
                # no download).
                if not force and exists(ent, deezer_id):
                    skipped += 1
                    continue
                processed += 1
                ok = download_and_convert(ent, deezer_id, source_url)
                if ok:
                    found += 1
                else:
                    failed += 1
                if processed % PROGRESS_EVERY == 0:
                    self.stdout.write(
                        f"[descarregar_portades] {ent}: progress "
                        f"processed={processed} found={found} failed={failed}"
                    )
                time.sleep(THROTTLE_S)
            if processed >= limit:
                break

        self.stdout.write(
            f"[descarregar_portades] done (entitat={entitat}, limit={limit}, "
            f"force={force}): found={found} failed={failed} skipped={skipped}"
        )

    # ── candidate selection ─────────────────────────────────────────
    def _iter_candidates(self, entitat: str):
        """Yield (deezer_id, source_url) pairs for an entity. Only rows
        that carry both a deezer_id and a non-empty image URL."""
        if entitat == "album":
            qs = (
                Album.objects.exclude(deezer_id__isnull=True)
                .exclude(imatge_url="")
                .values_list("deezer_id", "imatge_url")
                .iterator()
            )
            yield from qs
        elif entitat == "cancio":
            qs = (
                Canco.objects.exclude(deezer_id__isnull=True)
                .exclude(album__imatge_url="")
                .exclude(album__isnull=True)
                .values_list("deezer_id", "album__imatge_url")
                .iterator()
            )
            yield from qs
        elif entitat == "artista":
            # Artista has no direct deezer_id column (M2M via
            # ArtistaDeezer); resolve the principal id per row. Only
            # artistes with a stored image are candidates.
            arts = (
                Artista.objects.exclude(imatge_url="")
                .prefetch_related("deezer_ids")
                .iterator()
            )
            for a in arts:
                dz = a.deezer_id_principal
                if dz is not None:
                    yield dz, a.imatge_url
        else:  # pragma: no cover - guarded by argparse choices
            raise CommandError(f"unknown entitat {entitat!r}")
