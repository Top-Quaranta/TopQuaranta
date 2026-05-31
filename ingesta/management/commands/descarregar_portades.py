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
        n = len(entitats)
        # Split the budget evenly (limit // n) across entitats, but with
        # fall-through: when an entity runs out of candidates before
        # spending its budget, the unused part rolls into the NEXT
        # entity's budget, and the LAST entity absorbs whatever is left
        # (so the integer-division remainder is never wasted and the
        # full `limit` is used when candidates exist). Without this the
        # album iteration alone consumed the whole budget and cancio /
        # artista never got covers (validated 2026-05-30). Single-entity
        # mode (n == 1) is unchanged: the one entity gets the full limit.
        base = limit // n
        carry = 0
        remaining_total = limit
        stats: dict[str, tuple[int, int, int]] = {}

        for i, ent in enumerate(entitats):
            if i == n - 1:
                budget = remaining_total  # last absorbs the remainder
            else:
                budget = min(base + carry, remaining_total)
            found, failed, skipped, processed = self._process_entity(ent, budget, force)
            carry = budget - processed  # unused budget → next entity
            remaining_total -= processed
            stats[ent] = (found, failed, skipped)

        summary = "; ".join(
            f"{e}: found={stats[e][0]} failed={stats[e][1]} skipped={stats[e][2]}"
            for e in entitats
        )
        self.stdout.write(
            f"[descarregar_portades] done (entitat={entitat}, limit={limit}, "
            f"force={force}): {summary}"
        )

    def _process_entity(
        self, ent: str, budget: int, force: bool
    ) -> tuple[int, int, int, int]:
        """Process up to `budget` NEW downloads for one entity. Returns
        (found, failed, skipped, processed). Skips (already-present) do
        NOT consume the budget — only actual downloads do."""
        found = failed = skipped = processed = 0
        if budget <= 0:
            return found, failed, skipped, processed
        for deezer_id, source_url in self._iter_candidates(ent):
            if processed >= budget:
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
                    f"processed={processed}/{budget} found={found} failed={failed}"
                )
            time.sleep(THROTTLE_S)
        return found, failed, skipped, processed

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
                Artista.objects.exclude(imatge_url="").prefetch_related("deezer_ids")
                # chunk_size is required by Django when .iterator() follows
                # prefetch_related().
                .iterator(chunk_size=500)
            )
            for a in arts:
                dz = a.deezer_id_principal
                if dz is not None:
                    yield dz, a.imatge_url
        else:  # pragma: no cover - guarded by argparse choices
            raise CommandError(f"unknown entitat {entitat!r}")
