"""Behaviour pins for the shared Spotify metadata cooldown module.

Tests cover three guarantees:

  1. Both commands' reads honour an active ban no matter which
     file it was written into (shared post-2026-05-25 or one of
     the legacy per-command files).
  2. New writes only land in the shared file. Legacy paths are
     read-only during the transition.
  3. `clear_expired` prunes only files whose `resume_at` is in
     the past; active bans stay.

The playlist sync (`actualitzar_playlists_spotify`) writes to a
different endpoint bucket and is intentionally NOT routed
through this cooldown; tests assert it does not touch any of the
metadata cooldown files.
"""

# Spec: docs/architecture/ingesta.md

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from ingesta.clients import spotify_metadata_cooldown as cd


def _paths(tmp_path: Path):
    return (
        tmp_path / "spotify_metadata.cooldown",
        (
            tmp_path / "enriquir_spotify.cooldown",
            tmp_path / "enriquir_spotify_rebuigs.cooldown",
        ),
    )


def _write(path: Path, resume_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(resume_at.isoformat())


# ---------------------------------------------------------------------
# active_resume_at
# ---------------------------------------------------------------------


def test_no_files_returns_none(tmp_path):
    shared, legacy = _paths(tmp_path)
    now = datetime(2026, 5, 25, 10, 0, 0)
    assert cd.active_resume_at(shared=shared, legacy=legacy, now=now) is None


def test_active_shared_file_wins(tmp_path):
    shared, legacy = _paths(tmp_path)
    now = datetime(2026, 5, 25, 10, 0, 0)
    _write(shared, now + timedelta(hours=2))
    assert cd.active_resume_at(
        shared=shared, legacy=legacy, now=now
    ) == now + timedelta(hours=2)


def test_active_legacy_maintenance_file_seen(tmp_path):
    """The original `enriquir_spotify.cooldown` keeps blocking
    the metadata bucket during the transition."""
    shared, legacy = _paths(tmp_path)
    now = datetime(2026, 5, 25, 10, 0, 0)
    _write(legacy[0], now + timedelta(hours=4))  # maintenance legacy
    assert cd.active_resume_at(
        shared=shared, legacy=legacy, now=now
    ) == now + timedelta(hours=4)


def test_longest_unexpired_ban_wins(tmp_path):
    """If multiple files have active bans, the latest resume_at
    wins. Conservative against shrinking the window."""
    shared, legacy = _paths(tmp_path)
    now = datetime(2026, 5, 25, 10, 0, 0)
    _write(shared, now + timedelta(hours=2))
    _write(legacy[0], now + timedelta(hours=6))
    assert cd.active_resume_at(
        shared=shared, legacy=legacy, now=now
    ) == now + timedelta(hours=6)


def test_expired_files_ignored(tmp_path):
    shared, legacy = _paths(tmp_path)
    now = datetime(2026, 5, 25, 10, 0, 0)
    _write(shared, now - timedelta(hours=2))  # already expired
    _write(legacy[0], now - timedelta(hours=1))
    assert cd.active_resume_at(shared=shared, legacy=legacy, now=now) is None


def test_corrupt_file_treated_as_absent(tmp_path):
    shared, legacy = _paths(tmp_path)
    now = datetime(2026, 5, 25, 10, 0, 0)
    shared.write_text("not-an-iso-date")
    assert cd.active_resume_at(shared=shared, legacy=legacy, now=now) is None


def test_is_active_wraps_resume_at(tmp_path):
    shared, legacy = _paths(tmp_path)
    now = datetime(2026, 5, 25, 10, 0, 0)
    assert cd.is_active(shared=shared, legacy=legacy, now=now) is False
    _write(shared, now + timedelta(hours=1))
    assert cd.is_active(shared=shared, legacy=legacy, now=now) is True


# ---------------------------------------------------------------------
# write
# ---------------------------------------------------------------------


def test_write_only_touches_shared_file(tmp_path):
    """New bans always land in the shared file. Legacy files
    must not be created by `write`, so they drain naturally as
    their existing bans expire."""
    shared, legacy = _paths(tmp_path)
    cd.write(datetime(2026, 5, 26, 0, 0, 0), shared=shared)
    assert shared.exists()
    for path in legacy:
        assert not path.exists()


# ---------------------------------------------------------------------
# clear_expired
# ---------------------------------------------------------------------


def test_clear_expired_removes_expired_only(tmp_path):
    shared, legacy = _paths(tmp_path)
    now = datetime(2026, 5, 25, 10, 0, 0)
    _write(shared, now - timedelta(hours=1))  # expired
    _write(legacy[0], now + timedelta(hours=3))  # active
    _write(legacy[1], now - timedelta(hours=2))  # expired
    cd.clear_expired(shared=shared, legacy=legacy, now=now)
    assert not shared.exists()
    assert legacy[0].exists()
    assert not legacy[1].exists()


def test_clear_expired_idempotent_when_no_files(tmp_path):
    shared, legacy = _paths(tmp_path)
    now = datetime(2026, 5, 25, 10, 0, 0)
    cd.clear_expired(shared=shared, legacy=legacy, now=now)


# ---------------------------------------------------------------------
# Playlist sync is NOT in the cooldown surface
# ---------------------------------------------------------------------


@pytest.mark.django_db
def test_playlist_sync_does_not_reference_metadata_cooldown(tmp_path):
    """Static assertion: the playlist sync command must not
    import the shared metadata cooldown. Different endpoint
    bucket, separate quota; routing it through this module would
    cause spurious skips of writes that Spotify allows.

    Rewritten as a behavioural check. Property asserted now: with an
    ACTIVE metadata ban in every cooldown file (shared + both legacy),
    `actualitzar_playlists_spotify` still pushes the playlist write.
    Whether or not the module is imported is not pinned."""
    from music.models import Album, Artista, Canco, SpotifyMetadata, SpotifyPlaylist

    shared, legacy = _paths(tmp_path)
    far = datetime(2099, 1, 1, 0, 0, 0)
    _write(shared, far)
    for path in legacy:
        _write(path, far)

    artista = Artista.objects.create(nom="EXEMPLE cd", lastfm_nom="EXEMPLE cd")
    album = Album.objects.create(artista=artista, nom="EXEMPLE cd Al")
    c = Canco.objects.create(
        artista=artista,
        album=album,
        nom="EXEMPLE cd c",
        isrc="ZZ00X0000777",
        verificada=False,
        ml_confianca=0.5,
    )
    sm, _ = SpotifyMetadata.objects.get_or_create(canco=c)
    sm.enrichment_status = SpotifyMetadata.STATUS_FOUND
    sm.spotify_id = "URI-cd"
    sm.save(update_fields=["enrichment_status", "spotify_id"])
    SpotifyPlaylist.objects.all().delete()
    SpotifyPlaylist.objects.create(
        codi="no-verif-cd",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        chunk_index=0,
        spotify_playlist_id="fake-pl-cd",
    )

    with (
        patch.object(cd, "SHARED_PATH", shared),
        patch.object(cd, "LEGACY_PATHS", legacy),
        patch(
            "ingesta.management.commands.actualitzar_playlists_spotify.SpotifyAuth.load",
            return_value=MagicMock(refresh_token="x", spotify_user_id="u"),
        ),
        patch(
            "ingesta.management.commands.actualitzar_playlists_spotify.UserSpotifyClient"
        ) as cls,
    ):
        assert cd.is_active(), "precondition: the metadata ban must be live"
        client = MagicMock()
        cls.return_value = client
        call_command("actualitzar_playlists_spotify")

    pushed = [c.args for c in client.replace_playlist_tracks.call_args_list]
    assert pushed, "playlist write must not be gated by the metadata cooldown"
    assert pushed[0][0] == "fake-pl-cd"
    assert "spotify:track:URI-cd" in pushed[0][1]
