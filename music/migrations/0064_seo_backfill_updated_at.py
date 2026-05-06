"""Backfill `updated_at` on existing rows with the best modification
proxy available per model.

The schema migration (0063) added the column with `auto_now=True`,
which seeds every existing row with NOW() — i.e. "edited today".
For the SEO sitemap's `lastmod` to be honest, we want a more
truthful initial value. Per model:

* Artista: `Coalesce(mb_last_sync, created_at)` — when MB last
  re-validated the artiste, that's a real modification touching
  area / aliases / discography / `mb_*` fields.
* Album:   `Coalesce(last_album_check, created_at)` — Cron P2 sets
  this on every Deezer re-scan; if the album's track list grew it
  was the moment.
* Canco:   `created_at` — no better proxy exists. The `auto_now=True`
  field captures every future staff edit / verification flip /
  ML reclassification, so the long tail self-corrects within weeks.

This is a one-shot data migration; no reverse direction (we'd
overwrite real edits with the proxy if rolled back).
"""

from django.db import migrations
from django.db.models import F
from django.db.models.functions import Coalesce


def backfill_updated_at(apps, schema_editor):
    Artista = apps.get_model("music", "Artista")
    Album = apps.get_model("music", "Album")
    Canco = apps.get_model("music", "Canco")

    Artista.objects.update(updated_at=Coalesce(F("mb_last_sync"), F("created_at")))
    Album.objects.update(updated_at=Coalesce(F("last_album_check"), F("created_at")))
    Canco.objects.update(updated_at=F("created_at"))


def noop(apps, schema_editor):
    """Reverse: no-op. Rolling back would clobber real post-deploy
    edits with the proxy values, which is worse than leaving them.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0063_seo_updated_at_artista_album_canco"),
    ]

    operations = [
        migrations.RunPython(backfill_updated_at, noop),
    ]
