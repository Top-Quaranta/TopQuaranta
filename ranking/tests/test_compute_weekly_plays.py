"""Unit tests for `ranking.algorisme._compute_weekly_plays`.

Anchors the four branches of the per-canço weekly-plays estimator
documented in the function's docstring. Branch (4) is especially
important to lock in after the 2026-05-07 decision to drop lifetime
extrapolation in favour of returning 0 when no baseline exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ranking.algorisme import _compute_weekly_plays, _robust_weekly_from_series

# ── Lightweight fakes (no DB) ──────────────────────────────────────


@dataclass
class _Senyal:
    data: date
    lastfm_playcount: int | None
    # Track identity at sample time. Required so the track-switch
    # guard (added 2026-05-08 after the Pau Vallvé / Sopa de Cabra /
    # Smoking Souls live-album spike) can compare baseline to latest
    # and refuse the delta when Last.fm has flipped to a different
    # recording.
    lastfm_returned_track: str = ""


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


# ── Track-switch guard (2026-05-08) ────────────────────────────────


def test_track_switch_blocks_baseline_branch_2():
    """The Pau Vallvé / Sopa de Cabra / Smoking Souls live-album
    spike: 13 days at pc=3 against `lastfm_returned_track="X (Live)"`,
    then today's signal returns pc=6906 against
    `lastfm_returned_track="X"` (the studio version Last.fm fell back
    to). Without the guard, the delta would be 6 903 phantom plays;
    with it, the baseline is rejected as a different recording and
    the function falls through to branch (4) → 0.
    """
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2024, 1, 1))  # not a fresh release
    signals = [
        _Senyal(date(2026, 4, 30), 3, "Guarda'm l'aire (en directe)"),
        _Senyal(date(2026, 5, 7), 6906, "Guarda'm l'aire"),
    ]
    assert _compute_weekly_plays(canco, signals, today) == 0.0


def test_same_track_baseline_still_used():
    """Sanity: when `lastfm_returned_track` matches between baseline
    and latest, the delta is honoured. Same shape as the previous
    test but with consistent track identity."""
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2024, 1, 1))
    signals = [
        _Senyal(date(2026, 4, 30), 100, "Buguenvíl·lies (Live)"),
        _Senyal(date(2026, 5, 7), 250, "Buguenvíl·lies (Live)"),
    ]
    # delta = 150, gap = 7 d → 150 plays
    assert _compute_weekly_plays(canco, signals, today) == 150.0


def test_track_switch_blocks_remasteritzada():
    """Enemic Interior case (caught 2026-05-08): `"X (Remasteritzada)"`
    baseline against `"X"` latest. The track-identity normaliser
    keeps the parenthetical intact (only case + accents + punctuation
    collapse to whitespace), so the two strings remain distinct and
    the delta is rejected.
    """
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2024, 1, 1))
    signals = [
        _Senyal(date(2026, 4, 30), 30, "Camisa de Força (Remasteritzada)"),
        _Senyal(date(2026, 5, 7), 7600, "Camisa de Força"),
    ]
    assert _compute_weekly_plays(canco, signals, today) == 0.0


def test_track_switch_with_window_match_falls_back_to_branch_3():
    """When branch 2 has a match-track baseline AND a different-track
    candidate within window, the match-track wins. When only the
    different-track exists in window, branch 2 returns nothing and
    branch 3 looks for older same-track data."""
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2024, 1, 1))
    signals = [
        # 14 d back — same track, would qualify for branch 3
        _Senyal(date(2026, 4, 23), 50, "Vida (en directe)"),
        # 7 d back — DIFFERENT track (Last.fm flipped temporarily)
        _Senyal(date(2026, 4, 30), 6000, "Vida"),
        # today — back to live
        _Senyal(date(2026, 5, 7), 60, "Vida (en directe)"),
    ]
    # Branch 2 candidates window = [-9d, -5d]: only the 4-30 row,
    # which is a different track → filtered. Branch 3 finds the 4-23
    # same-track row. delta = 60 - 50 = 10 over 14 d → 5.0/week.
    assert _compute_weekly_plays(canco, signals, today) == 5.0


def test_legacy_signal_with_empty_returned_track_falls_through():
    """Pre-2026 SenyalDiari rows had `lastfm_returned_track` empty
    by default. The guard must NOT punish them (fall back to legacy
    behaviour: trust the baseline) — otherwise the algorithm goes
    silent overnight on an old DB."""
    today = date(2026, 5, 7)
    canco = _Canco(data_llancament=date(2024, 1, 1))
    signals = [
        _Senyal(date(2026, 4, 30), 100, ""),  # legacy: track unknown
        _Senyal(date(2026, 5, 7), 200, ""),
    ]
    # Delta = 100, gap = 7 d → 100 plays. No track filter applied
    # because `ref_track_n` is empty.
    assert _compute_weekly_plays(canco, signals, today) == 100.0


# ── Step-robust merge guard (2026-06-06) ───────────────────────────
#
# Last.fm merges scrobbles onto a canonical recording, doubling a
# track's CUMULATIVE playcount overnight (same track NAME, so the
# track-switch guard above does not fire). The strict 7-day delta then
# reads that one-day step as a week of plays. `_robust_weekly_from_series`
# excises the step and back-fills with the clean daily rhythm. The four
# named cases below are the sonda's no-regression net.


def _daily_series(start, base, increments):
    """Build ascending `(date, cumulative)` pairs from per-day
    `increments` starting at `base` on `start`."""
    out = [(start, base)]
    pc = base
    for i, inc in enumerate(increments, start=1):
        pc += inc
        out.append((start + timedelta(days=i), pc))
    return out


def test_robust_series_returns_none_without_merge():
    """Smooth daily growth → no merge → None (caller keeps legacy)."""
    series = _daily_series(date(2026, 5, 16), 1000, [10, 12, 11, 9, 13, 10, 12])
    assert _robust_weekly_from_series(series) is None


def test_robust_series_excises_merge_step():
    """A single overnight doubling (+8133 on a ~4/day rhythm) is
    excised; the week reflects the clean rhythm, not the step."""
    # Pau Riba «Noia de Porcellana» shape (sonda 2026-06-05).
    series = _daily_series(
        date(2026, 5, 16),
        8116,
        [0, 3, 4, 6, 8133, 6, 4],  # the 8133 step is the merge
    )
    out = _robust_weekly_from_series(series)
    assert out is not None
    # Clean rhythm ~3.8/day → ~27/week, not the 8156 the legacy delta
    # would have produced.
    assert out < 60


def test_robust_series_catches_sub_thousand_doubling():
    """«Sa Madona» (Júlia Colom) in BAL: a 956→1914 overnight doubling
    (+958, under the old 1000 floor) was a real merge that faked a #1
    in a small territory. The low absolute floor must still flag it."""
    series = _daily_series(
        date(2026, 5, 16),
        956,
        [0, 0, 0, 1, 957, 6, 0],  # +957 doubling on day 5
    )
    out = _robust_weekly_from_series(series)
    assert out is not None
    assert out < 30  # cleaned to its near-silent real rhythm


def test_robust_series_ignores_tiny_doubling():
    """A 3→7 "doubling" on a near-silent track is below the noise floor
    and left alone (no merge claim on trivial counts)."""
    series = _daily_series(date(2026, 5, 16), 3, [0, 1, 0, 4, 1, 0, 1])
    assert _robust_weekly_from_series(series) is None


def test_robust_series_too_few_points_returns_none():
    series = [(date(2026, 5, 20), 8129), (date(2026, 5, 23), 16262)]
    assert _robust_weekly_from_series(series) is None


# Calibration cases — the four sonda labels. `_compute_weekly_plays`
# end-to-end (fresh branch + track guard + robust + legacy).


def test_calib_pau_riba_noia_de_porcellana_is_cleaned():
    """Reissue (dl 2026-04-24, 29 d old) whose cumulative doubled on
    2026-05-21. Must NOT score the 8 156-play merge delta."""
    today = date(2026, 5, 23)
    canco = _Canco(data_llancament=date(2026, 4, 24))
    series = _daily_series(
        date(2026, 5, 16),
        8116,
        [0, 3, 4, 6, 8133, 6, 4],
    )
    signals = [_Senyal(d, pc, "Noia de Porcellana") for d, pc in series]
    out = _compute_weekly_plays(canco, signals, today)
    assert out < 60  # cleaned; legacy would have been ~8156


def test_calib_la_fumiga_gracies_per_tant_is_cleaned():
    """Long-runner (dl 2025-10-23) doubled on 2026-05-21 from a
    ~10/day rhythm. Must be cleaned to its real weekly rhythm."""
    today = date(2026, 5, 23)
    canco = _Canco(data_llancament=date(2025, 10, 23))
    series = _daily_series(
        date(2026, 5, 16),
        4297,
        [0, 8, 11, 8, 4383, 12, 24],  # 4383 step = merge
    )
    signals = [_Senyal(d, pc, "Gràcies per Tant") for d, pc in series]
    out = _compute_weekly_plays(canco, signals, today)
    assert out < 200  # cleaned; legacy would have been ~4456


def test_calib_rosalia_divinize_untouched():
    """Genuine high-play song: smooth ~3 500/day growth, no single-day
    outlier. Robust must defer (None) and the legacy delta is kept."""
    today = date(2026, 5, 23)
    canco = _Canco(data_llancament=date(2025, 11, 7))
    series = _daily_series(
        date(2026, 5, 16),
        3_074_025,
        [3787, 3194, 3329, 3895, 4130, 3836, 3859],
    )
    signals = [_Senyal(d, pc, "Divinize") for d, pc in series]
    out = _compute_weekly_plays(canco, signals, today)
    # Equals the legacy endpoint delta (last - first over 7 d): unchanged.
    assert out == float(series[-1][1] - series[0][1])
    assert out > 20_000


def test_calib_sx3_tots_som_supers_fresh_untouched():
    """Genuinely new release (dl 1 day before the run): the fresh
    branch returns the full count and the robust path is never reached."""
    today = date(2026, 5, 30)
    canco = _Canco(data_llancament=date(2026, 5, 29))  # 1 d old
    signals = [_Senyal(date(2026, 5, 30), 4656, "Tots Som Súpers")]
    assert _compute_weekly_plays(canco, signals, today) == 4656.0


def test_robust_next_week_after_merge_is_legacy_identical():
    """The week AFTER a merge: the step is before `today - 7`, so the
    strict window sees no merge and the value is the plain legacy delta
    (here ~20), never inflated."""
    today = date(2026, 5, 30)
    canco = _Canco(data_llancament=date(2026, 4, 24))
    # 05-21 step is now outside the [05-23, 05-30] window.
    series = _daily_series(
        date(2026, 5, 23),
        16272,
        [2, 4, 4, 4, 4, 6, 4],
    )
    signals = [_Senyal(d, pc, "Noia de Porcellana") for d, pc in series]
    out = _compute_weekly_plays(canco, signals, today)
    assert out == float(series[-1][1] - series[0][1])  # plain 7-day delta
