"""Clean up orphan pendent artistes.

Caught 2026-05-06: a pendent named "Cactus" (pk=5619, font=
deezer_contributor) had 0 Deezer IDs (its ArtistaDeezer was unlinked
by the smart-homonym fix earlier in May) and 0 main tracks, but was
still attached as `artistes_col` to two verified songs from other
artistes (Tesa, La Fúmiga). The polluted pendent kept showing up at
`/staff/pendents` even though it could never be approved (no
external anchor → invariant violation), and clicking through to its
"verified collab tracks" rendered a confusing detail page.

This command sweeps every pendent (`aprovat=False`) artista with:
  * 0 ArtistaDeezer rows (no Deezer anchor)
  * 0 main-FK Cançons (`artista=this`)
  * ≥1 collab Cançons (`artistes_col=this`)
  * Exactly ONE approved Artista with the same name elsewhere

…and re-routes the collab links to the approved sibling, then
deletes the orphan. If there are multiple approved siblings (real
homonym ambiguity) we leave it alone — staff has to pick.

Idempotent. Designed to run weekly. Audit-logged via
`StaffAuditLog` so the trail survives the deletion.
"""

from __future__ import annotations

import logging
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from music.audit import log_staff_action
from music.models import Artista, Canco

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Neteja pendents òrfens (sense Deezer ID + sense main tracks)."

    def add_arguments(self, parser):
        from music.management_helpers import add_dry_run

        add_dry_run(parser)

    def handle(self, *args, **opts):
        dry_run = bool(opts.get("dry_run"))

        # Candidate orphans: pendent + 0 Deezer IDs + 0 main tracks.
        candidates = (
            Artista.objects.filter(aprovat=False)
            .annotate(
                n_dz=Count("deezer_ids", distinct=True),
                n_main=Count("cancons", distinct=True),
                n_col=Count("participacions", distinct=True),
            )
            .filter(n_dz=0, n_main=0, n_col__gt=0)
        )

        results = Counter()
        for orphan in candidates.iterator():
            siblings = list(Artista.objects.public().filter(nom__iexact=orphan.nom))
            if len(siblings) == 0:
                results["no_sibling"] += 1
                self.stdout.write(
                    f"  · {orphan.nom!r} (pk={orphan.pk}): cap "
                    "germà aprovat — deixar com està"
                )
                continue
            if len(siblings) > 1:
                results["ambiguous"] += 1
                self.stdout.write(
                    f"  · {orphan.nom!r} (pk={orphan.pk}): "
                    f"{len(siblings)} germans aprovats — staff manual"
                )
                continue

            target = siblings[0]
            collabs = list(Canco.objects.filter(artistes_col=orphan).distinct())
            if dry_run:
                self.stdout.write(
                    f"  · DRY {orphan.nom!r} (pk={orphan.pk}) → pk={target.pk} "
                    f"({len(collabs)} collabs)"
                )
                results["would_merge"] += 1
                continue

            with transaction.atomic():
                for c in collabs:
                    c.artistes_col.remove(orphan)
                    c.artistes_col.add(target)
                # Audit before the row disappears.
                log_staff_action(
                    None,
                    "pendent_orphan_merged",
                    target=target,
                    orphan_pk=orphan.pk,
                    orphan_nom=orphan.nom,
                    collabs_moved=len(collabs),
                    source="netejar_pendents_orfes",
                )
                orphan.delete()
            results["merged"] += 1
            self.stdout.write(
                f"  ✓ {orphan.nom!r} (pk={orphan.pk}) → pk={target.pk} "
                f"({len(collabs)} collabs)"
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Resum:"))
        for k, v in results.items():
            self.stdout.write(f"  {k:12s} {v}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN — res escrit."))
