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

# Spec: docs/architecture/pipeline.md

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

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


def test_active_legacy_backfill_file_seen(tmp_path):
    shared, legacy = _paths(tmp_path)
    now = datetime(2026, 5, 25, 10, 0, 0)
    _write(legacy[1], now + timedelta(hours=4))  # backfill legacy
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


def test_playlist_sync_does_not_reference_metadata_cooldown():
    """Static assertion: the playlist sync command must not
    import the shared metadata cooldown. Different endpoint
    bucket, separate quota; routing it through this module would
    cause spurious skips of writes that Spotify allows."""
    src = (
        Path(__file__).resolve().parent.parent.parent
        / "ingesta"
        / "management"
        / "commands"
        / "actualitzar_playlists_spotify.py"
    )
    text = src.read_text(encoding="utf-8")
    assert "spotify_metadata_cooldown" not in text, (
        "actualitzar_playlists_spotify must not import the metadata "
        "cooldown; the playlist-write bucket is separate."
    )
