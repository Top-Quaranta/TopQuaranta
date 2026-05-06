"""Auto-discard pendent collab artistes with no PPCC anchor.

Sibling of `netejar_pendents_orfes`. Different shape:

  * `font_descoberta` in {`collaborador`, `deezer_contributor`}
  * `aprovat=False`, `pendent_review=True` (still on the staff queue)
  * 0 main-FK Cançons (`artista=this`)
  * 0 PPCC `ArtistaLocalitat` rows (`localitats__municipi__isnull=False`)
  * 0 `StaffAuditLog` entries targeting this artiste (i.e. staff has
    never looked at it)

These pendents are noise: the collab pipeline (`_upsert_track` /
`_create_track`) creates an Artista row for every Deezer contributor
on a verified track, which over time drowns the staff queue with
non-PPCC names — sometimes thousands per profile when a verified
artista has a mixed-catalogue Deezer profile (e.g. Àlex Pérez,
contributor pk 1479910, 30+ albums across labels).

Action: set `pendent_review=False` (descartat — kept for FK integrity
in case a verified track still has a collab link). Audit-logged with
the `pendent_descartar` action so the trail survives.

`--dry-run` reports counts without writing. Designed to run weekly
alongside `netejar_pendents_orfes` (Mon 02:15 UTC).
"""

from __future__ import annotations

import logging
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from music.audit import log_staff_action
from music.models import Artista, StaffAuditLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Descarta pendents col·lab sense ancoratge PPCC ni activitat staff."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--max",
            type=int,
            default=500,
            help="Cap per execució per evitar tsunamis d'audit-log.",
        )

    def handle(self, *args, **opts):
        dry_run = bool(opts.get("dry_run"))
        cap = int(opts.get("max") or 500)

        # Candidates: collab-discovered pendent + 0 main tracks +
        # 0 PPCC localitats. We keep the queryset broad and prune
        # the staff-activity check per row (StaffAuditLog has no FK
        # to Artista, only target_type/target_id snapshot).
        qs = (
            Artista.objects.filter(
                aprovat=False,
                pendent_review=True,
                font_descoberta__in=("collaborador", "deezer_contributor"),
            )
            .annotate(
                n_main=Count("cancons", distinct=True),
                n_ppcc_loc=Count(
                    "localitats",
                    filter=Q(localitats__municipi__isnull=False),
                    distinct=True,
                ),
            )
            .filter(n_main=0, n_ppcc_loc=0)
        )

        results = Counter()
        seen = 0
        for orphan in qs.iterator():
            if results["descartat"] >= cap:
                self.stdout.write(
                    self.style.WARNING(f"  · cap {cap} assolit — aturant aquesta tanda")
                )
                break
            seen += 1

            # Staff-activity check. Any audit row whose target is
            # this artista counts — past triage means a human has
            # already weighed in and we shouldn't second-guess.
            has_activity = StaffAuditLog.objects.filter(
                target_type="Artista",
                target_id=orphan.pk,
            ).exists()
            if has_activity:
                results["te_activitat"] += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"  · DRY {orphan.nom!r} (pk={orphan.pk}, "
                    f"font={orphan.font_descoberta})"
                )
                results["descartat"] += 1
                continue

            with transaction.atomic():
                orphan.pendent_review = False
                orphan.save(update_fields=["pendent_review"])
                log_staff_action(
                    None,
                    "pendent_descartar",
                    target=orphan,
                    motiu="auto_no_ppcc",
                    font_descoberta=orphan.font_descoberta,
                    source="netejar_pendents_no_ppcc",
                )
            results["descartat"] += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Resum (vistos: {seen}):"))
        for k, v in results.items():
            self.stdout.write(f"  {k:14s} {v}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN — res escrit."))
