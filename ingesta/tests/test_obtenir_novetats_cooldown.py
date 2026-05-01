"""P3 cooldown gate on `obtenir_novetats`.

Caught 2026-05-01: a single cron invocation never exited because
the P3 query (approved artists ordered by `last_checked_deezer`)
was always non-empty — every iteration just reshuffled the queue
and revisited the same artists. The hourly cron's lock-skip path
hid this for 12 days.

Fix: filter the P3 query to artists either never checked or last
checked ≥24h ago. When the queue drains, `.first()` returns None,
the `if not artista: break` fires, and the run exits cleanly.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from music.models import Artista, ArtistaDeezer


@pytest.fixture(autouse=True)
def bypass_singleton_lock():
    """The real `SingletonLock` flocks `/tmp/obtenir_novetats.lock`,
    which collides with any running cron / dev process on the host.
    Replace it with a no-op context manager for the test."""
    from contextlib import contextmanager

    @contextmanager
    def _noop_lock(name):
        yield None

    with patch("music.locks.SingletonLock", _noop_lock):
        yield


@pytest.fixture
def deezer_quota_clean():
    """Stub deezer.quota_exhausted -> False so the command runs the
    P3 path freely. We never want a real Deezer call in tests."""
    with patch(
        "ingesta.management.commands.obtenir_novetats.deezer.quota_exhausted",
        return_value=False,
    ):
        yield


@pytest.fixture
def stub_deezer_calls():
    """Replace every Deezer client method that touches the network."""
    with (
        patch(
            "ingesta.management.commands.obtenir_novetats.deezer.get_artist_albums",
            return_value=[],
        ),
        patch(
            "ingesta.management.commands.obtenir_novetats.deezer.get_album_tracks",
            return_value=[],
        ),
        patch(
            "ingesta.management.commands.obtenir_novetats.deezer._get",
            return_value=None,
        ),
    ):
        yield


@pytest.mark.django_db
def test_p3_cooldown_skips_recently_checked(db, deezer_quota_clean, stub_deezer_calls):
    """An artist checked <24h ago must NOT appear in the P3 queue —
    otherwise the run revisits the same artist forever."""
    a = Artista.objects.create(nom="A", lastfm_nom="A", aprovat=True)
    ArtistaDeezer.objects.create(artista=a, deezer_id=1)
    a.last_checked_deezer = timezone.now() - timedelta(hours=1)
    a.save(update_fields=["last_checked_deezer"])

    out = StringIO()
    # Should exit immediately because the only approved+deezer
    # artist was checked 1h ago (< 24h cooldown).
    call_command("obtenir_novetats", stdout=out)
    assert "Total crides: 0" in out.getvalue()


@pytest.mark.django_db
def test_p3_cooldown_processes_stale_check(db, deezer_quota_clean, stub_deezer_calls):
    """An artist checked >24h ago is eligible and gets refreshed."""
    a = Artista.objects.create(nom="A", lastfm_nom="A", aprovat=True)
    ArtistaDeezer.objects.create(artista=a, deezer_id=1)
    a.last_checked_deezer = timezone.now() - timedelta(hours=25)
    a.save(update_fields=["last_checked_deezer"])

    out = StringIO()
    call_command("obtenir_novetats", stdout=out)
    text = out.getvalue()
    assert "P3 artista" in text
    a.refresh_from_db()
    # Refreshed: last_checked_deezer pushed to ~now.
    assert a.last_checked_deezer > timezone.now() - timedelta(minutes=5)


@pytest.mark.django_db
def test_p3_cooldown_picks_never_checked(db, deezer_quota_clean, stub_deezer_calls):
    """An artist with last_checked_deezer=NULL is eligible (priority
    nulls-first). New approvals must be picked up immediately."""
    a = Artista.objects.create(nom="A", lastfm_nom="A", aprovat=True)
    ArtistaDeezer.objects.create(artista=a, deezer_id=1)
    # last_checked_deezer is NULL by default.
    assert a.last_checked_deezer is None

    out = StringIO()
    call_command("obtenir_novetats", stdout=out)
    assert "P3 artista" in out.getvalue()
    a.refresh_from_db()
    assert a.last_checked_deezer is not None


@pytest.mark.django_db
def test_p3_cooldown_exits_when_all_recent(db, deezer_quota_clean, stub_deezer_calls):
    """Mixed queue: some artists eligible, some not. The eligible
    ones get processed; once they all fall above the cooldown
    threshold (because they were just refreshed), the run exits."""
    fresh = Artista.objects.create(nom="Fresh", lastfm_nom="Fresh", aprovat=True)
    ArtistaDeezer.objects.create(artista=fresh, deezer_id=1)
    fresh.last_checked_deezer = timezone.now() - timedelta(hours=2)
    fresh.save(update_fields=["last_checked_deezer"])

    stale = Artista.objects.create(nom="Stale", lastfm_nom="Stale", aprovat=True)
    ArtistaDeezer.objects.create(artista=stale, deezer_id=2)
    stale.last_checked_deezer = timezone.now() - timedelta(hours=48)
    stale.save(update_fields=["last_checked_deezer"])

    out = StringIO()
    call_command("obtenir_novetats", stdout=out)
    text = out.getvalue()
    # Only the stale one was processed; the fresh one stays
    # untouched until its cooldown expires.
    assert "Stale" in text
    assert "Fresh" not in text
    fresh.refresh_from_db()
    # `fresh.last_checked_deezer` is the same value we set above
    # (2h ago) — not refreshed in this run.
    assert fresh.last_checked_deezer < timezone.now() - timedelta(hours=1)
