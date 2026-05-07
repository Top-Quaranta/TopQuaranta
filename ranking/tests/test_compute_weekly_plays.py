"""Unit tests for `ranking.algorisme._compute_weekly_plays`.

Anchors the four branches of the per-canço weekly-plays estimator
documented in the function's docstring. Branch (4) is especially
important to lock in after the 2026-05-07 decision to drop lifetime
extrapolation in favour of returning 0 when no baseline exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ranking.algorisme import _compute_weekly_plays

# ── Lightweight fakes (no DB) ──────────────────────────────────────


@dataclass
class _Senyal:
    data: date
    lastfm_playcount: int | None


@dataclass
class _Canco:
    data_llancament: date | None


# ── Branch 1: fresh release (< 7 days old) ─────────────────────────


def test_fresh_release_returns_today_playcount():
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2026, 5, 5))  # 2 d old
    signals = [_Senyal(date(2026, 5, 7), 750)]
    assert _compute_weekly_plays(canco, signals, today) == 750.0


def test_fresh_release_ignores_baseline_even_if_present():
    """A 2-day-old release with a single ingested signal: even if
    we somehow had a fake baseline from 7 d ago, branch (1) wins."""
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2026, 5, 5))
    signals = [
        _Senyal(date(2026, 4, 30), 50),  # noise / shouldn't be reachable
        _Senyal(date(2026, 5, 7), 800),
    ]
    assert _compute_weekly_plays(canco, signals, today) == 800.0


# ── Branch 2: rolling 7-day delta with full baseline ───────────────


def test_rolling_delta_full_window():
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2025, 1, 1))
    # Baseline 7 days back exact, latest today.
    signals = [
        _Senyal(date(2026, 4, 30), 1000),
        _Senyal(date(2026, 5, 7), 1500),
    ]
    # Δ=500 over 7 days → 500.
    assert _compute_weekly_plays(canco, signals, today) == 500.0


def test_rolling_delta_negative_clamps_to_zero():
    """Last.fm sometimes back-corrects play counts down. We clamp."""
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2025, 1, 1))
    signals = [
        _Senyal(date(2026, 4, 30), 1500),
        _Senyal(date(2026, 5, 7), 1000),  # went DOWN
    ]
    assert _compute_weekly_plays(canco, signals, today) == 0.0


# ── Branch 3: older delta fallback ─────────────────────────────────


def test_older_delta_rescaled():
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2025, 1, 1))
    # Only a 10-day-old baseline. Δ over 10 d → rescale to 7 d.
    signals = [
        _Senyal(date(2026, 4, 27), 1000),
        _Senyal(date(2026, 5, 7), 1100),
    ]
    # Δ=100 / 10 d * 7 = 70.
    assert _compute_weekly_plays(canco, signals, today) == 70.0


# ── Branch 4: NEW behaviour — no signal → 0 ────────────────────────


def test_no_baseline_returns_zero_not_extrapolation():
    """May-2026 audit decision (Option A): when the canço is older
    than 7 days but we lack any usable baseline, return 0. The old
    code did lifetime extrapolation, which conflated long-tail plays
    with current-week activity."""
    today = date(2026, 5, 7)
    # 6 months old — old enough to have collected lots of lifetime
    # plays. Only signal is today's snapshot.
    canco = _Canco(data_llancament=date(2025, 11, 1))
    signals = [_Senyal(date(2026, 5, 7), 70_000)]
    assert _compute_weekly_plays(canco, signals, today) == 0.0


def test_no_signals_returns_zero():
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2025, 1, 1))
    assert _compute_weekly_plays(canco, [], today) == 0.0


def test_today_playcount_none_returns_zero():
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2025, 1, 1))
    signals = [_Senyal(date(2026, 5, 7), None)]
    assert _compute_weekly_plays(canco, signals, today) == 0.0


def test_only_recent_signal_no_baseline_returns_zero():
    """Edge of branch (3): we have signals, but none at least 4 d
    back. Used to fall through to lifetime extrapolation; now → 0."""
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2025, 1, 1))
    signals = [
        _Senyal(date(2026, 5, 5), 1000),  # 2 d back (too recent for branch 3)
        _Senyal(date(2026, 5, 6), 1100),
        _Senyal(date(2026, 5, 7), 1200),
    ]
    assert _compute_weekly_plays(canco, signals, today) == 0.0


def test_no_release_date_no_baseline_returns_zero():
    """Edge case the old code handled separately (data_llancament
    None → returned 0 anyway). Behaviour unchanged."""
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=None)
    signals = [_Senyal(date(2026, 5, 7), 1000)]
    assert _compute_weekly_plays(canco, signals, today) == 0.0
