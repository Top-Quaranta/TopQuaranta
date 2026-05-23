# FASE D (2026-05-23): seed the 5 weekly Spotify playlist rows + mark
# the existing daily-tops explicitly with freq=daily.
#
# The 5 weekly playlists already exist on Spotify (created during the
# 2026-04 legacy sprint, 82 followers combined) but were never
# registered in SpotifyPlaylist, so the sync command could not touch
# them. Their content has been stale since April.
#
# IDs come from the Spotify dashboard inventory; territori labels
# follow the ranking-eligible codes (PPCC + CAT + VAL + BAL + ALT).
#
# Idempotent: get_or_create by codi. Forward-only; reverse is a no-op
# so test fake-migration does not crash.

from django.db import migrations

# Existing daily-top rows that we mark explicitly (default is already
# "daily" from the field default, but we set it for clarity and to
# tolerate future changes to the default).
_DAILY_CODIS = ["top-cat", "top-val", "top-bal", "top-alt", "top-ppcc"]

# New weekly rows. codi pattern mirrors the existing daily naming.
# (codi, territori, spotify_playlist_id)
_WEEKLY = [
    ("top-ppcc-weekly", "PPCC", "75IQLLWrOrJ1BaJc1RlJeY"),
    ("top-cat-weekly", "CAT", "2rjDevnzE7qPphdrxAhYOT"),
    ("top-val-weekly", "VAL", "5yMimy5GaaG5ipQadbm1Yq"),
    ("top-bal-weekly", "BAL", "4GhnQ4rvBPJxwBH0PJ3QKK"),
    ("top-alt-weekly", "ALT", "4ts0Pyov3qnexNGrk6wWul"),
]


def forwards(apps, schema_editor):
    SpotifyPlaylist = apps.get_model("music", "SpotifyPlaylist")
    # Mark legacy daily-tops explicitly. The default is already "daily"
    # so this is mostly defensive (and emits a stat line for the log).
    daily_count = SpotifyPlaylist.objects.filter(codi__in=_DAILY_CODIS).update(
        freq="daily"
    )

    # Seed the 5 weekly rows.
    created = 0
    for codi, territori, sp_id in _WEEKLY:
        _, was_created = SpotifyPlaylist.objects.get_or_create(
            codi=codi,
            defaults={
                "kind": "top",
                "freq": "weekly",
                "territori": territori,
                "spotify_playlist_id": sp_id,
            },
        )
        if was_created:
            created += 1

    print(
        f"  SpotifyPlaylist FASE D: daily_marked={daily_count} "
        f"weekly_seeded={created}"
    )


def backwards(apps, schema_editor):
    # Forward-only: a reverse would orphan operator-visible Spotify
    # playlists from their managed SpotifyPlaylist rows.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0081_spotify_playlist_freq"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
