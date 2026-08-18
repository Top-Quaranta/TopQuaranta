"""Prune self-hosted covers that no longer back any public surface.

# Spec: docs/architecture/portades.md

Retention for `PORTADES_ROOT` (disk-90% alert, 2026-08-12): the
download cron had iterated the ENTIRE catalogue — descartat albums,
unverified cançons, deleted rows — accumulating ~60k files with no
prune. `descarregar_portades` now bounds its candidates to the public
catalogue; this command is the recurring sweep that deletes what that
filter no longer yields (and any orphan left by row deletion).

KEEP-set per entity (everything else on disk is deleted):

- album:  non-descartat albums with a deezer_id, PLUS the album of
  every cançó that has EVER appeared in a `TopSetmanal`. The ranking
  union is load-bearing: newsletter emails embed absolute
  `/portades/album/<id>-<mida>.jpg` URLs (`comptes/newsletter_covers`),
  so pruning an ever-ranked album cover would break images inside
  already-delivered emails.
- canco:  verificada cançons on a non-descartat album, plus
  ever-ranked cançons (same drift guard: an old ranked cançó whose
  album was later descartat keeps her cover).
- artista: aprovat artistes' principal Deezer ids. No ranking union
  needed — no email ever embeds artista covers; the SPA falls back to
  Deezer on a 404.

Deleting a kept-out cover only degrades that page to the Deezer CDN
fallback (`Cover.jsx` stepped chain) — nothing breaks. Fully
re-derivable: a wrongly-pruned cover is re-downloaded by the nightly
cron the moment its entity re-enters the candidate set. Idempotent.
Designed to run weekly via cron; emits `WORK_DONE=N` for tq-health.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from ingesta.portades import manager
from music.models import Album, Artista, Canco

logger = logging.getLogger(__name__)

# <deezer_id>-<mida>.<format> — anything else in the dir is ignored.
_FILE_RE = re.compile(r"^(\d+)-\d+\.(?:avif|webp|jpg)$")

ENTITATS = ("album", "canco", "artista")


class Command(BaseCommand):
    help = "Esborra portades locals d'entitats fora del catàleg públic."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Només informa: no esborra cap fitxer.",
        )

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        total_ids = 0
        for entitat in ENTITATS:
            d = Path(settings.PORTADES_ROOT) / entitat
            if not d.is_dir():
                continue
            on_disk: set[int] = set()
            for f in d.iterdir():
                m = _FILE_RE.match(f.name)
                if m:
                    on_disk.add(int(m.group(1)))
            stale = on_disk - self._keep_ids(entitat)
            for deezer_id in sorted(stale):
                if not dry:
                    manager.delete(entitat, deezer_id)
                logger.info(
                    "portada %s/%s %s",
                    entitat,
                    deezer_id,
                    "es podaria (dry-run)" if dry else "podada",
                )
            total_ids += len(stale)
            self.stdout.write(
                f"{entitat}: {len(on_disk)} en disc, {len(stale)} "
                f"{'a podar (dry-run)' if dry else 'podades'}"
            )
        self.stdout.write(f"WORK_DONE={total_ids}")

    @staticmethod
    def _keep_ids(entitat: str) -> set[int]:
        if entitat == "album":
            keep = set(
                Album.objects.filter(descartat=False)
                .exclude(deezer_id__isnull=True)
                .values_list("deezer_id", flat=True)
            )
            keep |= set(
                Album.objects.filter(cancons__rankings__isnull=False)
                .exclude(deezer_id__isnull=True)
                .values_list("deezer_id", flat=True)
            )
            return keep
        if entitat == "canco":
            keep = set(
                Canco.objects.filter(verificada=True, album__descartat=False)
                .exclude(deezer_id__isnull=True)
                .values_list("deezer_id", flat=True)
            )
            keep |= set(
                Canco.objects.filter(rankings__isnull=False)
                .exclude(deezer_id__isnull=True)
                .values_list("deezer_id", flat=True)
            )
            return keep
        # artista — principal id needs Python-side resolution (M2M).
        return {
            dz
            for a in Artista.objects.filter(aprovat=True)
            .exclude(imatge_url="")
            .prefetch_related("deezer_ids")
            if (dz := a.deezer_id_principal) is not None
        }
