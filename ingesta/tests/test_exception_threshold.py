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
    """No artists in the queryset → processed=0 → no raise.

    Property asserted now: a run where every artista succeeds (0 %
    failure) completes without CommandError, both with an empty
    queryset and with a populated one. The summary text is not pinned."""
    from music.models import Artista

    call_command("obtenir_metadata", stdout=StringIO())  # processed=0

    for i in range(3):
        Artista.objects.create(nom=f"X{i}", slug=f"x{i}", aprovat=True)
    with patch(
        "ingesta.management.commands.obtenir_metadata.Command._process_artist",
        return_value=(0, 0, 0, 0),
    ) as proc:
        call_command("obtenir_metadata", stdout=StringIO())
    assert proc.call_count == 3  # the whole queryset was iterated


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
    """30% failure rate → no raise.

    Property asserted now: the run completes without CommandError and
    every artista was still visited (fail-open per item). The
    "Artists errors: N" summary text is not pinned."""
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
        call_command("obtenir_metadata", stdout=StringIO())  # must not raise
    assert call_count["n"] == len(artists)


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


@pytest.mark.django_db
def test_restaurar_command_has_logger_in_audit_except_block(caplog):
    """Code-level invariant: the `except Exception:` after
    `log_staff_action(...)` in `restaurar_mb_falsament_desassignats`
    contains `logger.warning` (was bare `pass` before E2 B-1).

    The full-stack test is too tangled to set up (the restore loop
    needs Artista + Localitat + previous unassign audit + `_looks_ppcc`
    True for the artist's localitats), so we settle for an AST-grep
    invariant. Cheaper, still pins the regression.

    Rewritten as a behavioural test: an audit row whose reason is an
    inconclusive country ("Spain") drives the restore path with
    `--apply`; `log_staff_action` is patched to raise. Property
    asserted now: the restore itself lands (MBID reassigned, block-list
    cleaned) AND a WARNING is emitted from the command's logger, i.e.
    the audit failure is neither fatal nor silent."""
    import logging

    from music.models import Artista, StaffAuditLog

    mbid = "11111111-2222-3333-4444-555555555555"
    a = Artista.objects.create(
        nom="EXEMPLE Restaurable",
        slug="exemple-restaurable",
        aprovat=True,
        musicbrainz_id="",
        mb_blocked_mbids=[mbid],
    )
    StaffAuditLog.objects.create(
        action="artista_mbid_auto_unassign",
        target_type="artista",
        target_id=a.pk,
        metadata={"mbid": mbid, "reason": "mb-area-non-ppcc:Spain"},
    )

    with patch(
        "music.management.commands.restaurar_mb_falsament_desassignats.log_staff_action",
        side_effect=RuntimeError("synthetic audit outage"),
    ):
        with caplog.at_level(
            logging.WARNING,
            logger="music.management.commands.restaurar_mb_falsament_desassignats",
        ):
            call_command(
                "restaurar_mb_falsament_desassignats", "--apply", stdout=StringIO()
            )

    a.refresh_from_db()
    assert a.musicbrainz_id == mbid
    assert mbid not in (a.mb_blocked_mbids or [])
    warnings = [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING
        and r.name == "music.management.commands.restaurar_mb_falsament_desassignats"
    ]
    assert warnings, "audit failure must be logged, not swallowed"
