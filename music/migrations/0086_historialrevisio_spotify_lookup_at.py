"""Track the last orphan-flow Spotify lookup per HistorialRevisio
row so the backfill does not re-search the same ISRC on every
nightly run.

Orphan HR rows (those whose `canco_deezer_id` no longer
corresponds to a live `Canco` row because `rebutjar_album` /
`rebutjar_artista` deleted them) can still carry an ISRC; the
backfill's new orphan flow does one `/v1/search?q=isrc:<X>` per
ISRC and writes the resolved `spotify_artist_id` back to every HR
row with that ISRC. To avoid re-issuing the same search forever
when Spotify replies "not found", every attempt also stamps
`spotify_lookup_at` so the candidate query can exclude rows
looked up recently.

Indexed: the candidate query filters `spotify_lookup_at__isnull=
True OR spotify_lookup_at__lt=<cutoff>`, scanning ~10k rows; a
btree index keeps that lookup cheap as the table grows.
"""

import django.db.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0085_historialrevisio_artista_spotify_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="historialrevisio",
            name="spotify_lookup_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                db_index=True,
                help_text=(
                    "Set by the rebuig backfill (`enriquir_spotify_rebuigs`) "
                    "every time the orphan flow runs an ISRC lookup against "
                    "Spotify for this row. NULL = never attempted. The "
                    "candidate query excludes rows looked up within the "
                    "last 30 days, regardless of whether the previous "
                    "attempt resolved the artist or not."
                ),
            ),
        ),
    ]
