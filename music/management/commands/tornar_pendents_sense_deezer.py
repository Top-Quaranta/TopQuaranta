"""Return approved artists that have NO Deezer anchor to the pending queue.

The Deezer-approval gate (2026-06) is enforced going forward at the
approval endpoints, but a handful of artists were approved before it
existed without any `ArtistaDeezer` row (some are MusicBrainz-anchored,
some are true ghosts). This command moves them back to pending
(`aprovat=False, pendent_review=True`) so staff re-approve them with a
Deezer. It NEVER merges duplicates, NEVER recomputes the top, and NEVER
publishes — the change simply rests until the next cron tick.

Idempotent: a second run finds nothing (the moved rows are no longer
`aprovat=True`). `--dry-run` prints the impact report (how many of each
artist's Cançons sit in the current public top) and changes nothing.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max

from music.audit import log_staff_action
from music.models import Artista
from ranking.models import TopSetmanal


class Command(BaseCommand):
    help = "Torna a pendents els artistes aprovats sense cap ArtistaDeezer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Només imprimeix l'informe; no escriu res.",
        )

    def handle(self, *args, **opts):
        dry_run = bool(opts.get("dry_run"))

        # Approved artists with zero ArtistaDeezer rows.
        ghosts = list(
            Artista.objects.filter(aprovat=True, deezer_ids__isnull=True)
            .distinct()
            .order_by("nom")
        )

        if not ghosts:
            self.stdout.write("Cap artista aprovat sense Deezer. Res a fer.")
            return

        # Current public top = the latest consolidated TopSetmanal week
        # (any territori). Used only for the downstream-impact report.
        latest = TopSetmanal.objects.aggregate(m=Max("setmana"))["m"]

        self.stdout.write(
            f"{'[DRY-RUN] ' if dry_run else ''}"
            f"{len(ghosts)} artistes aprovats sense Deezer:"
        )
        total_top_cancons = 0
        for a in ghosts:
            n_top = 0
            if latest is not None:
                n_top = (
                    TopSetmanal.objects.filter(setmana=latest, canco__artista=a)
                    .values("canco_id")
                    .distinct()
                    .count()
                )
            total_top_cancons += n_top
            has_mbid = bool((a.musicbrainz_id or "").strip())
            self.stdout.write(
                f"  pk={a.pk} «{a.nom}» mbid={'sí' if has_mbid else 'NO'} "
                f"localitats={a.localitats.count()} "
                f"cançons_al_top_actual={n_top}"
            )

        self.stdout.write(
            f"\nImpacte aigües avall: {total_top_cancons} cançons d'aquests "
            f"artistes són al top públic actual (setmana {latest})."
        )

        if dry_run:
            self.stdout.write("\n[DRY-RUN] Cap canvi aplicat.")
            return

        moved = 0
        for a in ghosts:
            with transaction.atomic():
                a.aprovat = False
                a.pendent_review = True
                a.save(update_fields=["aprovat", "pendent_review"])
                log_staff_action(
                    None,
                    "artista_edit",
                    target=a,
                    accio="tornat_a_pendents_sense_deezer",
                    tenia_mbid=bool((a.musicbrainz_id or "").strip()),
                )
            moved += 1

        self.stdout.write(self.style.SUCCESS(f"\n{moved} artistes tornats a pendents."))
