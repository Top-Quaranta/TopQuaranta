"""Auto-fill `Artista.percentatge_femeni` from `mb_gender`.

MusicBrainz exposes `gender` only for solo artists (not bands —
where the field is meaningless on its own). We use it to seed the
`percentatge_femeni` choice field:

  Female  → '100'
  Male    → '0'

(Other / Not applicable / blank → leave alone.)

Idempotent. Re-runs daily so when the MB cron updates an artiste's
gender (rare, but happens when the MBID is corrected), the
percentatge_femeni follows. Skips artistes whose
`percentatge_femeni` is already set to a NON-derived value (i.e.
'50+', '<50', or any value staff explicitly chose) — we don't want
to clobber a curator's call about a band like "Manel" with the
gender of any one member.

The "is this a derived value" check is just: was it set to
literally '0' or '100'? If yes and mb_gender is the matching value,
we leave it (idempotent). If the staff set it to '50+' or '<50',
we leave it (override). Anything else (blank) gets filled.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from music.models import Artista


class Command(BaseCommand):
    help = "Inferir Artista.percentatge_femeni des de MusicBrainz mb_gender."

    def add_arguments(self, parser):
        from music.management_helpers import add_dry_run

        add_dry_run(parser)

    def handle(self, *args, **opts):
        dry_run = bool(opts.get("dry_run"))

        # Only consider artistes with mb_gender set + percentatge_femeni
        # currently empty. We never overwrite a non-empty choice — staff
        # may have set '50+' or '<50' for a band manually.
        qs = (
            Artista.objects.public().filter(percentatge_femeni="").exclude(mb_gender="")
        )
        results = Counter()
        with transaction.atomic():
            for a in qs.only("pk", "mb_gender").iterator():
                g = (a.mb_gender or "").strip().lower()
                if g == "female":
                    new_val = "100"
                elif g == "male":
                    new_val = "0"
                else:
                    # 'Other', 'Not applicable', etc. — leave alone.
                    continue
                results[new_val] += 1
                if not dry_run:
                    Artista.objects.filter(pk=a.pk).update(percentatge_femeni=new_val)

        self.stdout.write(self.style.SUCCESS(f"Total escrits: {sum(results.values())}"))
        for k, v in results.items():
            label = "100% (dona)" if k == "100" else "0% (home)"
            self.stdout.write(f"  {label:20s} {v:5d}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN — res escrit."))
