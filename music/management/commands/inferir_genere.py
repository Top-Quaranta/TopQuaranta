"""Infer canonical genre per approved artiste from Last.fm + MB tags.

Walks every approved artiste with `genere_locked=False`, runs the
priority-weighted tag mapping in `music.genere.infer_canonical`, and
writes the resulting canonical to `Artista.genere_canonical`.

Idempotent — can be re-run anytime. Cron schedule: nightly at 02:00
UTC, after `obtenir_metadata_lastfm` (05:00 the night before) so we
work on the freshest tag data each iteration.

Override path: staff sets `genere_canonical=…, genere_locked=True`
on the artiste edit page when they disagree with the inference. The
cron leaves locked rows untouched.
"""

from __future__ import annotations

import logging
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from music.genere import infer_canonical
from music.models import Artista

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Infereix Artista.genere_canonical des dels tags Last.fm + MB."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **opts):
        dry_run = bool(opts.get("dry_run"))
        limit = opts.get("limit")

        qs = (
            Artista.objects.public()
            .filter(genere_locked=False)
            .only(
                "pk",
                "nom",
                "lastfm_tags",
                "mb_tags",
                "genere_canonical",
                "lastfm_auto_match_disabled",
            )
        )
        total = qs.count()
        if limit:
            qs = qs[:limit]

        results = Counter()
        no_signal = 0
        changed = 0
        with transaction.atomic():
            for a in qs.iterator():
                # When Last.fm is locked out for an artiste (homonym
                # collision: e.g. our Mallorcan LGBT band "Fades"
                # silently redirected to the English punk band
                # "The Fades", contaminating tags), feed the inferer
                # only MB tags. If those are empty too, no signal →
                # no canonical assigned.
                lastfm_for_inference = (
                    [] if a.lastfm_auto_match_disabled else a.lastfm_tags
                )
                new_canonical = infer_canonical(lastfm_for_inference, a.mb_tags)
                if not new_canonical:
                    no_signal += 1
                    if a.genere_canonical and not dry_run:
                        # Lost signal since last run — clear stale value.
                        Artista.objects.filter(pk=a.pk).update(genere_canonical="")
                        changed += 1
                    continue
                results[new_canonical] += 1
                if new_canonical != a.genere_canonical:
                    if not dry_run:
                        Artista.objects.filter(pk=a.pk).update(
                            genere_canonical=new_canonical
                        )
                    changed += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Total approved + unlocked: {total}"))
        self.stdout.write(f"  with no genre signal:    {no_signal}")
        self.stdout.write(f"  newly assigned/changed:  {changed}")
        self.stdout.write("")
        self.stdout.write("Distribució per gènere canònic:")
        for canonical, count in sorted(results.items(), key=lambda kv: -kv[1]):
            pct = 100.0 * count / max(1, total)
            self.stdout.write(f"  {canonical:14s} {count:5d}  ({pct:.1f} %)")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN — res escrit."))
