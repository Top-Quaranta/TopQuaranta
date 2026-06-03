"""Add `HistorialRevisio.artista_spotify_id` and backfill it from
existing `SpotifyMetadata` rows where possible.

Context: the per-pair rejection-ratio feature in `music.ml`
groups by (artista_deezer_id, artista_spotify_id) to disambiguate
Deezer-collapsed homonyms. The Deezer id was already on
`HistorialRevisio.artista_deezer_id`; the Spotify id wasn't
stored anywhere, only derivable via canço_deezer_id ->
SpotifyMetadata, and only for the ~6% of HR rows that map to an
enriched canço (the rebuigs are essentially 0% enriched).

This migration:
  1. Adds `artista_spotify_id` (CharField, blank, indexed).
  2. Backfills it for the HR rows whose `canco_deezer_id` already
     maps to a SpotifyMetadata with a non-empty principal
     `spotify_artist_id`. At migration time this is ~917 rows
     (aprovades and one rebuig). The rest stay blank and will be
     filled by the dedicated backfill command once Process B
     enriches their cançons.

Reverse migration drops the column.
"""

from django.db import migrations, models


def backfill_from_spotify_metadata(apps, schema_editor):
    HistorialRevisio = apps.get_model("music", "HistorialRevisio")
    Canco = apps.get_model("music", "Canco")
    SpotifyMetadata = apps.get_model("music", "SpotifyMetadata")

    # Build deezer_id -> spotify_artist_id map from current
    # enrichment state. Only rows in `enrichment_status='found'`
    # with a non-empty principal id qualify.
    pairs = (
        SpotifyMetadata.objects.filter(enrichment_status="found")
        .exclude(spotify_artist_id__isnull=True)
        .exclude(spotify_artist_id="")
        .values_list("canco__deezer_id", "spotify_artist_id")
    )
    by_dz = {dz: sp for dz, sp in pairs if dz is not None}

    if not by_dz:
        print("  [music.0085] no enriched cançons; nothing to backfill")
        return

    # Update in chunks to keep memory + transaction time bounded.
    affected = 0
    qs = HistorialRevisio.objects.filter(
        canco_deezer_id__in=by_dz.keys(),
        artista_spotify_id="",
    )
    for row in qs.iterator(chunk_size=1000):
        sp = by_dz.get(row.canco_deezer_id)
        if not sp:
            continue
        row.artista_spotify_id = sp
        row.save(update_fields=["artista_spotify_id"])
        affected += 1

    print(
        f"  [music.0085] backfilled artista_spotify_id on "
        f"{affected} HistorialRevisio rows from current SpotifyMetadata"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0084_requeue_desvincular_artista_victims"),
    ]

    operations = [
        migrations.AddField(
            model_name="historialrevisio",
            name="artista_spotify_id",
            field=models.CharField(blank=True, db_index=True, max_length=50),
        ),
        migrations.RunPython(
            backfill_from_spotify_metadata,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
