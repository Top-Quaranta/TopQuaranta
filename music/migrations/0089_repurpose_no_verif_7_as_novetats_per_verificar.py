# 2026-06-06: repurpose the old no-verif-7 triage playlist as the
# permanent "Novetats per verificar" work list.
#
# Why convert in place instead of delete + create:
#   no-verif-7 already owns the Spotify playlist 6exFHk1DUrqSINn7oFZo8s.
#   Converting the row in place keeps that spotify_playlist_id (same URL,
#   same followers) and its last_n_* history. NO new Spotify playlist is
#   created. The 7th no_verificades chunk was the lowest-confidence dead
#   tail (~0% coverage by design); the window is capped to 6 chunks in
#   actualitzar_playlists_spotify, so this row no longer overlaps a chunk.
#
# The new kind (novetats_per_verificar) is kept OUT of the coverage
# health alert (music.health.check_spotify_coverage). Process A pushes
# the playlist name + description on each sync, so the rename flows
# through the sanctioned pipeline rather than a manual Spotify edit.
#
# Idempotent: filter().update() keyed on the old codi, so a re-run on an
# already-converted DB is a no-op. Forward-only (reverse is a no-op, to
# avoid orphaning an operator-visible Spotify row).

from django.db import migrations

_OLD_CODI = "no-verif-7"
_NEW_CODI = "novetats-per-verificar"
_NEW_KIND = "novetats_per_verificar"


def forwards(apps, schema_editor):
    SpotifyPlaylist = apps.get_model("music", "SpotifyPlaylist")
    SpotifyPlaylist.objects.filter(codi=_OLD_CODI).update(
        codi=_NEW_CODI,
        kind=_NEW_KIND,
        territori="",
        chunk_index=None,
        # spotify_playlist_id, freq and last_n_* are preserved untouched.
    )


def backwards(apps, schema_editor):
    # Forward-only: a reverse would orphan an operator-visible Spotify row.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0088_alter_spotifyplaylist_kind"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
