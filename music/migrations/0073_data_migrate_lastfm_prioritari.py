"""Sprint Portal Artista, 2026-05-19 (A.4).

Backfill `ArtistaLastfmAlias.prioritari` from the legacy
`Artista.lastfm_nom` field.

For every Artista whose `lastfm_nom` is non-empty:
  * If an `ArtistaLastfmAlias` with the same name already exists,
    flip `confirmat=True` (defensive — should already be) and
    `prioritari=True` on that row.
  * Otherwise create a new row with the same name, marked
    `confirmat=True, rebutjat=False, prioritari=True` and the
    current timestamp.

Artists with `lastfm_nom == ""` AND one or more confirmed aliases
are left untouched — the gestor will pick the prioritari from the
new portal.

Idempotent: re-running is a no-op because the unique constraints
on (artista, nom) and (artista, prioritari=True) keep the data
consistent.
"""

from django.db import migrations
from django.utils import timezone


def _backfill(apps, schema_editor):
    Artista = apps.get_model("music", "Artista")
    ArtistaLastfmAlias = apps.get_model("music", "ArtistaLastfmAlias")
    now = timezone.now()

    n_flipped = 0
    n_created = 0
    n_skipped_blank = 0

    for art in Artista.objects.exclude(lastfm_nom="").iterator():
        # Try to find an existing alias with the same name (case-
        # sensitive — Last.fm names are case-sensitive on the API
        # path, even though their URLs are case-insensitive).
        alias = ArtistaLastfmAlias.objects.filter(
            artista=art, nom=art.lastfm_nom
        ).first()
        if alias is not None:
            changed = False
            if not alias.confirmat:
                alias.confirmat = True
                changed = True
            if not alias.prioritari:
                alias.prioritari = True
                changed = True
            if alias.rebutjat:
                alias.rebutjat = False
                changed = True
            if changed:
                if alias.confirmat and alias.confirmat_at is None:
                    alias.confirmat_at = now
                alias.save(
                    update_fields=[
                        "confirmat",
                        "prioritari",
                        "rebutjat",
                        "confirmat_at",
                    ]
                )
                n_flipped += 1
            continue

        # No existing row — create one. If another row already holds
        # prioritari=True for this artist, the conditional unique
        # constraint would raise; skip in that case (the operator
        # can clean up manually).
        if ArtistaLastfmAlias.objects.filter(artista=art, prioritari=True).exists():
            n_skipped_blank += 1
            continue
        ArtistaLastfmAlias.objects.create(
            artista=art,
            nom=art.lastfm_nom,
            confirmat=True,
            rebutjat=False,
            prioritari=True,
            confirmat_at=now,
        )
        n_created += 1

    print(
        f"  data_migrate_lastfm_prioritari: "
        f"flipped={n_flipped} created={n_created} "
        f"skipped_existing_prioritari={n_skipped_blank}"
    )


def _reverse(apps, schema_editor):
    """Reverse: flip prioritari=False for every row. Safe because
    the forward migration is idempotent — re-applying restores."""
    ArtistaLastfmAlias = apps.get_model("music", "ArtistaLastfmAlias")
    ArtistaLastfmAlias.objects.filter(prioritari=True).update(prioritari=False)


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0072_artista_imatge_url_artista_ultim_ping_revisio_at_and_more"),
    ]

    operations = [
        migrations.RunPython(_backfill, reverse_code=_reverse),
    ]
