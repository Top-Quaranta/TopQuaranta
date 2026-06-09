"""Adaptive outlier soft-cap on weekly plays (2026-06-09).

`TestApplySoftCap` is pure arithmetic and runs without the DB.
`TestSoftCapKnee` exercises the per-territori adaptive knee and needs the
`TopSetmanal.weekly_plays` column + the `soft_cap_*` ConfiguracioGlobal
fields, so it requires the migration that adds them.
"""

import math
from datetime import date, timedelta

import pytest

from ranking.algorisme import _apply_soft_cap, _soft_cap_knee
from ranking.models import ConfiguracioGlobal, TopSetmanal


class TestApplySoftCap:
    """Pure-math compression: normals untouched, outliers squashed."""

    def test_below_knee_unchanged(self):
        assert _apply_soft_cap(500.0, 1000.0) == 500.0

    def test_at_knee_unchanged(self):
        assert _apply_soft_cap(1000.0, 1000.0) == 1000.0

    def test_above_knee_compressed(self):
        eff = _apply_soft_cap(23193.0, 1500.0)
        assert eff == pytest.approx(1500.0 * (1.0 + math.log(23193.0 / 1500.0)))
        # Strictly between the knee and the raw value.
        assert 1500.0 < eff < 23193.0

    def test_none_knee_unchanged(self):
        assert _apply_soft_cap(23193.0, None) == 23193.0

    def test_nonpositive_knee_unchanged(self):
        assert _apply_soft_cap(23193.0, 0.0) == 23193.0
        assert _apply_soft_cap(23193.0, -5.0) == 23193.0

    def test_monotone_but_gap_compressed(self):
        a = _apply_soft_cap(5_000.0, 1_000.0)
        b = _apply_soft_cap(20_000.0, 1_000.0)
        assert b > a  # order among outliers preserved
        assert (b - a) < (20_000.0 - 5_000.0)  # but the gap is compressed


@pytest.mark.django_db
class TestSoftCapKnee:
    """Adaptive knee = max(floor, M × median(top-N plays, last W weeks))."""

    def _row(self, territori, setmana, posicio, plays):
        return TopSetmanal.objects.create(
            territori=territori,
            setmana=setmana,
            posicio=posicio,
            score_setmanal=0.0,
            weekly_plays=plays,
        )

    def test_disabled_returns_none(self):
        cfg = ConfiguracioGlobal.objects.create(pk=1, soft_cap_actiu=False)
        assert _soft_cap_knee("CAT", cfg, date.today()) is None

    def test_knee_from_median(self):
        cfg = ConfiguracioGlobal.objects.create(
            pk=1,
            soft_cap_actiu=True,
            soft_cap_multiplicador="3",
            soft_cap_floor_escoltes=0,
        )
        today = date.today()
        wk = today - timedelta(days=7)
        for i, p in enumerate([100, 200, 300, 400, 500], start=1):
            self._row("CAT", wk, i, p)
        # median = 300 → knee = 3 × 300 = 900
        assert _soft_cap_knee("CAT", cfg, today) == pytest.approx(900.0)

    def test_floor_wins_when_median_low(self):
        cfg = ConfiguracioGlobal.objects.create(
            pk=1,
            soft_cap_actiu=True,
            soft_cap_multiplicador="3",
            soft_cap_floor_escoltes=2000,
        )
        today = date.today()
        wk = today - timedelta(days=7)
        for i, p in enumerate([30, 40, 50], start=1):
            self._row("CAT", wk, i, p)
        # 3 × 40 = 120 < floor → 2000
        assert _soft_cap_knee("CAT", cfg, today) == pytest.approx(2000.0)

    def test_no_history_uses_floor(self):
        cfg = ConfiguracioGlobal.objects.create(
            pk=1, soft_cap_actiu=True, soft_cap_floor_escoltes=500
        )
        assert _soft_cap_knee("CAT", cfg, date.today()) == pytest.approx(500.0)

    def test_no_history_no_floor_returns_none(self):
        cfg = ConfiguracioGlobal.objects.create(
            pk=1, soft_cap_actiu=True, soft_cap_floor_escoltes=0
        )
        assert _soft_cap_knee("CAT", cfg, date.today()) is None

    def test_ignores_out_of_scope_rows(self):
        cfg = ConfiguracioGlobal.objects.create(
            pk=1,
            soft_cap_actiu=True,
            soft_cap_multiplicador="3",
            soft_cap_floor_escoltes=0,
        )
        today = date.today()
        recent = today - timedelta(days=7)
        old = today - timedelta(days=7 * 12)  # outside the 10-week window
        for i, p in enumerate([100, 200, 300, 400, 500], start=1):
            self._row("CAT", recent, i, p)
        # Noise that must NOT move the median:
        self._row("CAT", recent, 11, 999_999)  # position beyond top-N
        self._row("CAT", old, 1, 999_999)  # too old
        self._row("VAL", recent, 1, 999_999)  # different territori
        assert _soft_cap_knee("CAT", cfg, today) == pytest.approx(900.0)
