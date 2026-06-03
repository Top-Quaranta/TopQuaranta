"""Add the `manual` enrichment status to `SpotifyMetadata`.

Staff can paste a Spotify track URL by hand in the canço editor
(store-and-trust: format validated, no API call). That value lands in
`SpotifyMetadata.spotify_id` with `enrichment_status='manual'` — a
status distinct from `found` so manual links are auditable and are
excluded from automatic re-enrichment (Process B's candidate query only
selects `not_attempted`/no-row rows; `manual` is never re-touched).
Process A (actualitzar_playlists_spotify) treats `manual` like `found`
and puts the track in playlists.

Choices-only change: no DB column alteration beyond the stored
`choices` metadata. Reverse restores the three-status list.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0086_historialrevisio_spotify_lookup_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="spotifymetadata",
            name="enrichment_status",
            field=models.CharField(
                choices=[
                    ("not_attempted", "Encara no provada"),
                    ("found", "Trobada"),
                    ("not_found", "ISRC no a Spotify"),
                    ("manual", "Manual (staff)"),
                ],
                db_index=True,
                default="not_attempted",
                max_length=20,
            ),
        ),
    ]
