# Backfill SpotifyMetadata rows for every existing Canco.
#
# Rules:
#   * Canço with Canco.spotify_id populated -> create row with
#     enrichment_status="found", copying spotify_id and stamping
#     enriched_at=now. Other metadata fields stay empty; Process B
#     will fill them on a future re-enrichment if ever needed, but
#     since the existing spotify_id alone suffices for Process A
#     (sync to playlist) we don't force a re-run.
#   * Canço without Canco.spotify_id -> create row with
#     enrichment_status="not_attempted".
#
# Idempotent via get_or_create on the OneToOne canco field. Forward-
# only; reverse is a no-op so test fake-migration doesn't blow up.

from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    Canco = apps.get_model("music", "Canco")
    SpotifyMetadata = apps.get_model("music", "SpotifyMetadata")

    now = timezone.now()
    found_count = 0
    not_attempted_count = 0

    for canco in Canco.objects.all().iterator(chunk_size=500):
        existing = SpotifyMetadata.objects.filter(canco_id=canco.pk).first()
        if existing:
            continue
        if canco.spotify_id:
            SpotifyMetadata.objects.create(
                canco_id=canco.pk,
                spotify_id=canco.spotify_id,
                enrichment_status="found",
                enriched_at=now,
            )
            found_count += 1
        else:
            SpotifyMetadata.objects.create(
                canco_id=canco.pk,
                enrichment_status="not_attempted",
            )
            not_attempted_count += 1

    print(
        f"  SpotifyMetadata backfill: {found_count} found, "
        f"{not_attempted_count} not_attempted."
    )


def backwards(apps, schema_editor):
    # No-op so tests can fake-migrate without error. The schema reverse
    # (drop table) is handled by the previous migration.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0079_spotify_metadata_dispersion"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
