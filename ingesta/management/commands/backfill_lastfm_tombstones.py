"""One-shot backfill for the Last.fm similar→reject resurrection loop.

Context (audit 2026-06-02): `pendent_descartar` used to HARD-DELETE
song-less pendents, so `obtenir_metadata_lastfm._resolve_similar_target`
re-created them on the next sync of any approved artist that still
recommended the name (Tremenda Jauría / The Fades, each discarded 4×).
The code fix tombstones on discard going forward; this command repairs
the live damage by RE-TOMBSTONING the pendents that have already
resurrected.

It flips a pendent to a tombstone (aprovat=False, pendent_review=False)
iff BOTH hold:

  (i)  it is live NOW — aprovat=False, pendent_review=True — with
       font_descoberta="lastfm_similar", and
  (ii) its name has a prior `pendent_descartar` / deleted trace in
       StaffAuditLog (i.e. staff already discarded a same-named pendent
       before, and the old hard-delete let it come back).

By design it only RESTORES discards staff already made — it never
discards a pendent nobody has triaged, never touches non-lastfm_similar
sources, and creates nothing speculative. Name matching is
case-insensitive against either `nom` or `lastfm_nom`.

# Spec: docs/architecture/pipeline.md

Run `--dry-run` first; it writes nothing and prints the exact flip list.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Lower

from music.models import Artista, StaffAuditLog


class Command(BaseCommand):
    help = (
        "Re-tombstone live lastfm_similar pendents that staff already "
        "discarded-and-deleted before the tombstone fix."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def _deleted_names_lower(self) -> set[str]:
        """Lower-cased names from `pendent_descartar` audit rows that hard
        -deleted a pendent (`action_taken="deleted"`)."""
        rows = StaffAuditLog.objects.filter(
            action="pendent_descartar",
            metadata__action_taken="deleted",
        ).values_list("metadata__target_label_deleted", flat=True)
        return {(n or "").strip().lower() for n in rows if (n or "").strip()}

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        deleted = self._deleted_names_lower()

        # (i) live lastfm_similar pendents  ∩  (ii) prior deleted trace.
        to_flip = list(
            Artista.objects.filter(
                aprovat=False,
                pendent_review=True,
                font_descoberta="lastfm_similar",
            )
            .annotate(_nom_l=Lower("nom"), _lfm_l=Lower("lastfm_nom"))
            .filter(Q(_nom_l__in=deleted) | Q(_lfm_l__in=deleted))
            .order_by("pk")
        )

        self.stdout.write(
            f"{len(deleted)} distinct discarded names in the audit log; "
            f"{len(to_flip)} live lastfm_similar pendent(s) with a prior "
            f"discard → flip to tombstone."
        )
        for a in to_flip:
            self.stdout.write(f"  ~ {a.nom} (pk={a.pk})")

        if dry:
            self.stdout.write(self.style.WARNING("DRY RUN — no writes."))
            return

        with transaction.atomic():
            for a in to_flip:
                a.aprovat = False
                a.pendent_review = False
                a.save(update_fields=["aprovat", "pendent_review"])
        self.stdout.write(
            self.style.SUCCESS(f"Flipped {len(to_flip)} pendent(s) to tombstone.")
        )
