# FASE C (2026-05-22): re-label the legacy `novetats` row as top-ppcc
# and seed the 7 no_verificades triage playlists.
#
# Why re-label instead of delete+create:
#   The legacy `novetats` row already holds spotify_playlist_id
#   4nBIangCLrNMFj0L1Uj2jb, which (it turns out) is the playlist admin@
#   actually uses as the PPCC daily-revisio playlist. We re-label in
#   place so the spotify_playlist_id stays attached and `last_n_*` stats
#   from prior runs survive.
#
# The novetats concept is parked here; if/when we want a real release-day
# playlist we'll add a fresh row with a fresh spotify_playlist_id.
#
# Idempotent: uses filter().update() and get_or_create so a re-run on
# an already-migrated DB is a no-op. Forward-only (reverse is a no-op).

from django.db import migrations

# Re-label: (old_codi, new_codi, kind, territori) — preserves spotify_playlist_id.
_RELABEL = [
    ("novetats", "top-ppcc", "top", "PPCC"),
]

# Seed: codi → (spotify_playlist_id, chunk_index). Order matches the
# C.0 validation list (chunk 0 = newest 100; chunk 6 = entries 601-700).
_NO_VERIF_SEED = [
    ("no-verif-1", "1UVpQh2fGGtG7bAOkjGlYx", 0),
    ("no-verif-2", "1aLbOqACZdpwAa7O56neoW", 1),
    ("no-verif-3", "0FgFm7qNcdPzETGyJdNaUJ", 2),
    ("no-verif-4", "3HGl5GvhZaCLX9grkVBBTn", 3),
    ("no-verif-5", "0jvRYoHtv1iwVd0BAVqkDZ", 4),
    ("no-verif-6", "6St966o9lNhq5ICJp80c8V", 5),
    ("no-verif-7", "6exFHk1DUrqSINn7oFZo8s", 6),
]


def forwards(apps, schema_editor):
    SpotifyPlaylist = apps.get_model("music", "SpotifyPlaylist")

    # Step 1: re-label novetats -> top-ppcc (preserve spotify_playlist_id).
    for old_codi, new_codi, kind, territori in _RELABEL:
        SpotifyPlaylist.objects.filter(codi=old_codi).update(
            codi=new_codi, kind=kind, territori=territori
        )

    # Step 2: seed the 7 no_verificades playlists.
    for codi, sp_id, chunk in _NO_VERIF_SEED:
        SpotifyPlaylist.objects.update_or_create(
            codi=codi,
            defaults={
                "kind": "no_verificades",
                "territori": "",
                "spotify_playlist_id": sp_id,
                "chunk_index": chunk,
                "last_sync_ok": True,
            },
        )


def backwards(apps, schema_editor):
    # Forward-only: a reverse would orphan operator-visible Spotify rows.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0077_spotify_playlist_no_verif"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
