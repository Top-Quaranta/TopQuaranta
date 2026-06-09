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


@pytest.mark.django_db
class TestMergeInertness:
    """The feature is inert by default. With soft_cap_actiu=False the cap
    is a pure no-op on the scoring input — every weekly_plays value passes
    through unchanged, so calcular_top produces scores IDENTICAL to before
    the feature existed. (calcular_top_territori is Postgres-only raw SQL,
    skipped on the SQLite CI DB; this pins the exact per-song Python
    transform it applies, which is what makes the merge inert.)"""

    def test_off_is_identity_over_all_plays(self):
        cfg = ConfiguracioGlobal.objects.create(pk=1, soft_cap_actiu=False)
        knee = _soft_cap_knee("CAT", cfg, date.today())
        assert knee is None  # off → no knee, no DB query, no compression
        for plays in [0.0, 1.0, 5.0, 500.0, 5_000.0, 99_999.0, 1_000_000.0]:
            # Identity transform → the score uses the raw plays, unchanged.
            assert _apply_soft_cap(plays, knee) == plays


@pytest.mark.django_db
class TestBaseTopNConfigurable:
    """The median population is the configurable top-N head, not hardcoded."""

    def _seed(self):
        s = date.today() - timedelta(weeks=1)
        for pos, plays in [(1, 100), (2, 200), (3, 300), (4, 9000), (5, 9000)]:
            TopSetmanal.objects.create(
                territori="CAT",
                setmana=s,
                posicio=pos,
                score_setmanal=0.0,
                weekly_plays=plays,
            )

    def test_base_top_n_controls_median_population(self):
        cfg = ConfiguracioGlobal.objects.create(
            pk=1,
            soft_cap_actiu=True,
            soft_cap_multiplicador=1,
            soft_cap_floor_escoltes=0,
            soft_cap_base_top_n=3,
        )
        self._seed()
        # base_top_n=3 → median([100, 200, 300]) = 200 (tail 9000s excluded).
        assert _soft_cap_knee("CAT", cfg, date.today()) == 200.0
        # Widen to 5 → median([100, 200, 300, 9000, 9000]) = 300.
        cfg.soft_cap_base_top_n = 5
        cfg.save()
        assert _soft_cap_knee("CAT", cfg, date.today()) == 300.0
