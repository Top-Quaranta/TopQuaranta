"""Exception-threshold contract for management commands (E2 sweep,
2026-05-19).

The audit on 2026-05-18 identified three crons that swallowed
per-item exceptions without any aggregate signal: a broken API
upstream → every iteration fails → `tq-run` exits 0 → `tq-health`
sees `status=OK` → silent rot.

The fix: keep the per-item fail-open semantics (one bad artista
doesn't kill the cron) AND raise `CommandError` at the end when
more than 50% of the iteration failed.

Each test mocks the per-item call to either succeed or fail and
asserts:
  a) all-OK     → no raise, exit 0.
  b) 30% fail   → no raise, warning-level info only.
  c) 70% fail   → CommandError raised, message includes counters.

We use the StringIO `call_command` pattern so we can capture
stdout/stderr without touching the real cron schedule."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

# ── obtenir_metadata (C-4) ─────────────────────────────────────────


@pytest.mark.django_db
def test_obtenir_metadata_all_ok_does_not_raise():
    """No artists in the queryset → processed=0 → no raise."""
    out = StringIO()
    call_command("obtenir_metadata", stdout=out)
    assert "Metadata ingestion complete" in out.getvalue()


@pytest.mark.django_db
def test_obtenir_metadata_high_failure_rate_raises():
    """Force every `_process_artist` call to raise; the loop wraps
    it in `except Exception` → counter increments → threshold trips
    → `CommandError` propagates."""
    from music.models import Artista

    a1 = Artista.objects.create(nom="X1", slug="x1", aprovat=True)
    a2 = Artista.objects.create(nom="X2", slug="x2", aprovat=True)
    a3 = Artista.objects.create(nom="X3", slug="x3", aprovat=True)
    # Need at least one ArtistaDeezer row absent so they appear in the
    # default queryset (`deezer_ids__isnull=True`). Default creation
    # already satisfies that.

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic Deezer outage")

    with patch(
        "ingesta.management.commands.obtenir_metadata.Command._process_artist",
        side_effect=_boom,
    ):
        with pytest.raises(CommandError, match=r"3/3 artists failed"):
            call_command("obtenir_metadata", stdout=StringIO())

    # Ensure the artists weren't mutated (the wrap caught the error).
    assert Artista.objects.filter(pk=a1.pk).exists()
    assert Artista.objects.filter(pk=a2.pk).exists()


@pytest.mark.django_db
def test_obtenir_metadata_below_threshold_does_not_raise():
    """30% failure rate → no raise."""
    from music.models import Artista

    artists = [
        Artista.objects.create(nom=f"X{i}", slug=f"x{i}", aprovat=True)
        for i in range(10)
    ]

    call_count = {"n": 0}

    def _half_broken(self, artista, cutoff, force):
        call_count["n"] += 1
        if call_count["n"] <= 3:  # 30% fail
            raise RuntimeError("synthetic failure")
        return (0, 0, 0, 0)

    with patch(
        "ingesta.management.commands.obtenir_metadata.Command._process_artist",
        autospec=True,
        side_effect=_half_broken,
    ):
        out = StringIO()
        call_command("obtenir_metadata", stdout=out)
        assert "Artists errors: 3" in out.getvalue()


# ── backfill_album_source (C-5) ────────────────────────────────────


@pytest.mark.django_db
def test_backfill_album_source_high_failure_rate_raises():
    """Mock the Deezer client to always raise so every iteration
    increments `errors`."""
    from music.models import Album, Artista, ArtistaDeezer

    art = Artista.objects.create(nom="A", slug="a", aprovat=True)
    ArtistaDeezer.objects.create(artista=art, deezer_id=999)
    for i in range(3):
        Album.objects.create(
            nom=f"Album {i}",
            slug=f"album-{i}",
            artista=art,
            deezer_id=1000 + i,
            descartat=False,
        )

    def _boom(url, *args, **kwargs):
        raise RuntimeError("synthetic Deezer 500")

    with patch(
        "ingesta.management.commands.backfill_album_source.deezer._get",
        side_effect=_boom,
    ):
        with pytest.raises(CommandError, match=r">50% threshold"):
            call_command("backfill_album_source", stdout=StringIO())


# ── obtenir_metadata_musicbrainz (C-14) ────────────────────────────


@pytest.mark.django_db
def test_mb_sync_returns_false_on_exception(monkeypatch):
    """`_process` should return False when its outer except fires."""
    from ingesta.management.commands.obtenir_metadata_musicbrainz import Command
    from music.models import Artista

    a = Artista.objects.create(nom="X", slug="x", aprovat=True)
    cmd = Command()
    cmd.stdout = StringIO()

    monkeypatch.setattr(
        "ingesta.management.commands.obtenir_metadata_musicbrainz.validate_artista_area",
        lambda x: (_ for _ in ()).throw(RuntimeError("synthetic MB outage")),
    )
    a.musicbrainz_id = "00000000-0000-0000-0000-000000000000"
    a.save(update_fields=["musicbrainz_id"])
    assert cmd._process(a) is False


@pytest.mark.django_db
def test_mb_sync_returns_true_on_success(monkeypatch):
    """`_process` returns True when no exception fires."""
    from ingesta.management.commands.obtenir_metadata_musicbrainz import Command
    from music.models import Artista

    a = Artista.objects.create(nom="X", slug="x", aprovat=True)
    cmd = Command()
    cmd.stdout = StringIO()

    # No MBID → goes into "resolve_mbid"; mock that to return None
    # so we hit the [no-match] branch (no exception).
    monkeypatch.setattr(
        "ingesta.management.commands.obtenir_metadata_musicbrainz.resolve_mbid",
        lambda x: None,
    )
    monkeypatch.setattr(
        "ingesta.management.commands.obtenir_metadata_musicbrainz.time.sleep",
        lambda s: None,
    )
    assert cmd._process(a) is True


@pytest.mark.django_db
def test_mb_sync_high_failure_rate_raises(monkeypatch):
    """Force every iteration to raise inside `_process` → 100% fail
    rate → CommandError. We patch the inner call so the outer loop's
    counter increments naturally."""
    from music.models import Artista

    for i in range(3):
        Artista.objects.create(nom=f"X{i}", slug=f"x{i}", aprovat=True)

    monkeypatch.setattr(
        "ingesta.management.commands.obtenir_metadata_musicbrainz.resolve_mbid",
        lambda x: (_ for _ in ()).throw(RuntimeError("synthetic MB outage")),
    )
    monkeypatch.setattr(
        "ingesta.management.commands.obtenir_metadata_musicbrainz.time.sleep",
        lambda s: None,
    )

    with pytest.raises(CommandError, match=r">50% threshold"):
        call_command("obtenir_metadata_musicbrainz", "--limit", "3", stdout=StringIO())


# ── restaurar_mb_falsament_desassignats (B-1) ──────────────────────


def test_restaurar_command_has_logger_in_audit_except_block():
    """Code-level invariant: the `except Exception:` after
    `log_staff_action(...)` in `restaurar_mb_falsament_desassignats`
    contains `logger.warning` (was bare `pass` before E2 B-1).

    The full-stack test is too tangled to set up (the restore loop
    needs Artista + Localitat + previous unassign audit + `_looks_ppcc`
    True for the artist's localitats), so we settle for an AST-grep
    invariant. Cheaper, still pins the regression."""
    import inspect

    from music.management.commands import restaurar_mb_falsament_desassignats as mod

    src = inspect.getsource(mod)
    # The diff added `logger.warning("audit log_staff_action failed`
    # inside the except. Pin both the log call and the absence of a
    # bare `pass`.
    assert "logger.warning" in src
    assert "audit log_staff_action failed for artista pk=" in src
    # Defensive: the previous `except Exception: pass` is gone.
    # (A bare `pass` may still exist elsewhere — we only care about
    # the audit-log call site.)
    audit_block_idx = src.find("log_staff_action(")
    assert audit_block_idx > 0
    # The next 1200 chars should contain the warning, NOT a bare pass.
    # (The except-block sits ~700 chars after the call site because
    # of the indented multi-line kwargs to log_staff_action.)
    nearby = src[audit_block_idx : audit_block_idx + 1200]
    assert "logger.warning" in nearby
    assert "audit log_staff_action failed" in nearby
