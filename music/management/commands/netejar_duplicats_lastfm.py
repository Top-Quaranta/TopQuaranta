"""Sweep stale Last.fm-cron-created pendents that should already
have been absorbed by their canonical artist's confirmed alias.

Background — caught 2026-05-01:

For every confirmed `ArtistaLastfmAlias` row, the staff has
explicitly said 'this variant name belongs to this canonical
artist'. The pre-alias-era similars cron, however, often
auto-created a separate `Artista` (aprovat=False, pendent_review=True,
font_descoberta='lastfm_similar') at exactly the variant spelling.
Once an alias is confirmed, that pendent is by definition the
same artist as the canonical and should be absorbed.

Going forward, the absorb step runs synchronously when staff
confirms (or manually adds) an alias. This command is the
backfill for the existing mess.

Same safety rules as the live absorb (see
`web.api.staff.artistes._absorb_lastfm_duplicate_pendents`):
only delete pendents with no Cançons, no Deezer IDs, no
territoris, no collaborations, and `font_descoberta='lastfm_similar'`.

Usage:
    .venv/bin/python manage.py netejar_duplicats_lastfm                # dry-run
    .venv/bin/python manage.py netejar_duplicats_lastfm --apply
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from music.models import Artista, ArtistaLastfmAlias, ArtistaLastfmSimilar


class Command(BaseCommand):
    help = (
        "Absorb pre-existing pendent Artistes whose name matches a "
        "confirmed Last.fm alias of an approved artist."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        apply_changes = opts["apply"]
        # Re-implement the live helper here so the management command
        # doesn't import from the API package (which would pull in
        # DRF / auth machinery for what's essentially a DB chore).
        # Identical safety rules.
        confirmed = ArtistaLastfmAlias.objects.filter(
            confirmat=True, artista__aprovat=True
        ).select_related("artista")

        total_absorbed = 0
        total_skipped = 0
        for alias in confirmed:
            canon = alias.artista
            candidates = (
                Artista.objects.filter(aprovat=False)
                .filter(font_descoberta="lastfm_similar")
                .filter(Q(lastfm_nom__iexact=alias.nom) | Q(nom__iexact=alias.nom))
                .exclude(pk=canon.pk)
            )
            for dup in candidates:
                if (
                    dup.cancons.exists()
                    or dup.deezer_ids.exists()
                    or dup.territoris.exists()
                    or dup.participacions.exists()
                ):
                    self.stdout.write(
                        f"  SKIP pk={dup.pk} {dup.nom!r} — té dades reals"
                    )
                    total_skipped += 1
                    continue

                self.stdout.write(
                    f"  {'absorb' if apply_changes else '[DRY] would-absorb'} "
                    f"pk={dup.pk} {dup.nom!r} → canon pk={canon.pk} {canon.nom!r}"
                )
                if apply_changes:
                    # Redirect Last.fm similars (skip rows that
                    # would violate UNIQUE(source, target)).
                    existing = set(
                        ArtistaLastfmSimilar.objects.filter(target=canon).values_list(
                            "source_id", flat=True
                        )
                    )
                    for row in ArtistaLastfmSimilar.objects.filter(target=dup):
                        if row.source_id in existing:
                            row.delete()
                        else:
                            row.target = canon
                            row.save(update_fields=["target"])
                            existing.add(row.source_id)
                    ArtistaLastfmSimilar.objects.filter(source=dup).delete()
                    dup.delete()
                total_absorbed += 1

            if apply_changes and total_absorbed:
                # Recompute canonical's cached count once per pass,
                # at the end. Cheap (one COUNT query).
                Artista.objects.filter(pk=canon.pk).update(
                    nb_similars_lastfm=ArtistaLastfmSimilar.objects.filter(
                        target=canon
                    ).count()
                )

        verb = "Absorbed" if apply_changes else "Would absorb"
        self.stdout.write("")
        self.stdout.write(f"{verb}: {total_absorbed} pendents")
        self.stdout.write(f"Skipped (real data): {total_skipped} pendents")
        if not apply_changes and total_absorbed:
            self.stdout.write("Re-run with --apply to commit.")
