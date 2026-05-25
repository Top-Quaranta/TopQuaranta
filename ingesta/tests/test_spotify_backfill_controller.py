"""Behaviour pins for the AIMD ramp-up controller.

The controller's job is to keep the Spotify-backfill rate below
whatever quota Spotify is willing to grant today. Tests use
tmp_path for the state file and synthetic cooldown files for the
ban signal so they do not touch the production paths.
"""

# Spec: docs/architecture/pipeline.md

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ingesta.clients.spotify_backfill_controller import (
    BUMP,
    DAYS_BEFORE_BUMP,
    INITIAL_LIMIT,
    MAX_DAILY_LIMIT,
    MIN_LIMIT,
    ControllerState,
    adjust_for_run,
    detect_recent_ban,
)


def _touch_cooldown(path: Path, when: datetime) -> None:
    """Write a cooldown file with a future resume_at + set mtime
    to `when`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((when + timedelta(hours=12)).isoformat())
    ts = when.timestamp()
    import os

    os.utime(path, (ts, ts))


# ---------------------------------------------------------------------
# adjust_for_run: AI side (no ban) and MD side (ban)
# ---------------------------------------------------------------------


def test_cold_start_initial_limit():
    s = adjust_for_run(ControllerState(), cooldown_paths=())
    assert s.limit_actual == INITIAL_LIMIT
    assert s.dies_sense_ban == 1


def test_three_clean_days_bumps_limit():
    s = ControllerState()
    for _ in range(DAYS_BEFORE_BUMP):
        s = adjust_for_run(s, cooldown_paths=())
    # Counter resets on bump; limit advances.
    assert s.limit_actual == INITIAL_LIMIT + BUMP
    assert s.dies_sense_ban == 0
    # The previously-held limit is now last_safe.
    assert s.last_safe_limit == INITIAL_LIMIT


def test_bump_stops_at_ceiling():
    s = ControllerState(limit_actual=MAX_DAILY_LIMIT - 50)
    for _ in range(DAYS_BEFORE_BUMP):
        s = adjust_for_run(s, cooldown_paths=())
    assert s.limit_actual == MAX_DAILY_LIMIT
    # Bumping again has no effect.
    s.dies_sense_ban = DAYS_BEFORE_BUMP - 1
    s = adjust_for_run(s, cooldown_paths=())
    assert s.limit_actual == MAX_DAILY_LIMIT


def test_ban_drops_to_last_safe_when_available(tmp_path):
    cooldown = tmp_path / "spotify.cooldown"
    s = ControllerState(limit_actual=600, last_safe_limit=400, dies_sense_ban=2)
    now = datetime(2026, 5, 25, 3, 0, 0)
    _touch_cooldown(cooldown, now - timedelta(hours=1))
    s = adjust_for_run(s, now=now, cooldown_paths=(cooldown,))
    assert s.limit_actual == 400
    assert s.dies_sense_ban == 0
    assert s.last_ban_at is not None


def test_ban_halves_when_no_last_safe(tmp_path):
    cooldown = tmp_path / "spotify.cooldown"
    s = ControllerState(limit_actual=200, last_safe_limit=None)
    now = datetime(2026, 5, 25, 3, 0, 0)
    _touch_cooldown(cooldown, now - timedelta(hours=1))
    s = adjust_for_run(s, now=now, cooldown_paths=(cooldown,))
    assert s.limit_actual == 100  # halved
    assert s.dies_sense_ban == 0


def test_ban_floors_at_min_limit(tmp_path):
    """Even repeated bans cannot push the limit below MIN_LIMIT."""
    cooldown = tmp_path / "spotify.cooldown"
    s = ControllerState(limit_actual=MIN_LIMIT, last_safe_limit=None)
    now = datetime(2026, 5, 25, 3, 0, 0)
    _touch_cooldown(cooldown, now - timedelta(hours=1))
    s = adjust_for_run(s, now=now, cooldown_paths=(cooldown,))
    assert s.limit_actual == MIN_LIMIT


def test_ban_at_proven_safe_level_falls_to_halving(tmp_path):
    """If the level we drop to was itself the last safe, the next
    ban must halve, not stay put. Convergence guarantee."""
    cooldown = tmp_path / "spotify.cooldown"
    s = ControllerState(limit_actual=400, last_safe_limit=400)
    now = datetime(2026, 5, 25, 3, 0, 0)
    _touch_cooldown(cooldown, now - timedelta(hours=1))
    s = adjust_for_run(s, now=now, cooldown_paths=(cooldown,))
    assert s.limit_actual == 200  # halved (400 wasn't actually safe)


# ---------------------------------------------------------------------
# detect_recent_ban
# ---------------------------------------------------------------------


def test_no_cooldown_no_history_returns_none(tmp_path):
    cooldown = tmp_path / "spotify.cooldown"
    s = ControllerState(last_run_at="2026-05-25T03:00:00")
    assert detect_recent_ban(s, cooldown_paths=(cooldown,)) is None


def test_fresh_cooldown_seen(tmp_path):
    cooldown = tmp_path / "spotify.cooldown"
    last_run = datetime(2026, 5, 24, 3, 0, 0)
    fresh = datetime(2026, 5, 25, 1, 0, 0)
    _touch_cooldown(cooldown, fresh)
    s = ControllerState(last_run_at=last_run.isoformat())
    assert detect_recent_ban(s, cooldown_paths=(cooldown,)).date() == fresh.date()


def test_stale_cooldown_before_last_run_not_seen(tmp_path):
    cooldown = tmp_path / "spotify.cooldown"
    stale = datetime(2026, 5, 23, 3, 0, 0)
    _touch_cooldown(cooldown, stale)
    s = ControllerState(last_run_at="2026-05-24T03:00:00")
    assert detect_recent_ban(s, cooldown_paths=(cooldown,)) is None


def test_persisted_last_ban_remembered_within_24h(tmp_path):
    """The maintenance command can delete its own cooldown when
    it expires; the controller's persisted memory still treats
    the recent ban as recent for a 24h window."""
    s = ControllerState(
        last_run_at="2026-05-25T03:00:00",
        last_ban_at="2026-05-25T01:00:00",
    )
    cooldown = tmp_path / "spotify.cooldown"  # does not exist
    now = datetime(2026, 5, 25, 12, 0, 0)
    detected = detect_recent_ban(s, cooldown_paths=(cooldown,), now=now)
    assert detected is not None


def test_persisted_last_ban_forgotten_after_24h(tmp_path):
    s = ControllerState(
        last_run_at="2026-05-25T03:00:00",
        last_ban_at="2026-05-23T03:00:00",
    )
    cooldown = tmp_path / "spotify.cooldown"
    now = datetime(2026, 5, 25, 12, 0, 0)
    assert detect_recent_ban(s, cooldown_paths=(cooldown,), now=now) is None


# ---------------------------------------------------------------------
# State serialisation
# ---------------------------------------------------------------------


def test_state_serialisation_roundtrip():
    s = ControllerState(
        limit_actual=400,
        dies_sense_ban=2,
        last_safe_limit=200,
        last_ban_at="2026-05-24T03:00:00",
        last_run_at="2026-05-25T03:00:00",
    )
    s2 = ControllerState.from_dict(s.to_dict())
    assert s2 == s


def test_state_loader_drops_unknown_keys():
    """Older state files may have extra keys when the schema
    evolves; the loader must accept them."""
    raw = {
        "limit_actual": 400,
        "ancient_field": "ignore me",
    }
    s = ControllerState.from_dict(raw)
    assert s.limit_actual == 400
    # Other fields default.
    assert s.dies_sense_ban == 0
    assert s.last_safe_limit is None


# ---------------------------------------------------------------------
# AIMD convergence smoke test (multi-day)
# ---------------------------------------------------------------------


def test_aimd_converges_below_ban_threshold(tmp_path):
    """Simulated calendar: every 6th run the controller observes a
    ban (a stand-in for "the current limit is too high"). After a
    few cycles the limit should settle below the bumping ceiling
    instead of oscillating to MAX."""
    cooldown = tmp_path / "spotify.cooldown"
    s = ControllerState()
    seen_limits = []
    now = datetime(2026, 5, 1, 3, 0, 0)
    for day in range(40):
        if day in {15, 25, 35}:  # bans on these days
            _touch_cooldown(cooldown, now - timedelta(hours=1))
        else:
            cooldown.unlink(missing_ok=True)
        s = adjust_for_run(s, now=now, cooldown_paths=(cooldown,))
        seen_limits.append(s.limit_actual)
        now += timedelta(days=1)
    # The limit should never have exceeded MAX_DAILY_LIMIT.
    assert max(seen_limits) <= MAX_DAILY_LIMIT
    # After a ban, the limit must immediately be smaller than the
    # value just before the ban.
    for ban_day in (15, 25, 35):
        assert seen_limits[ban_day] < seen_limits[ban_day - 1]
