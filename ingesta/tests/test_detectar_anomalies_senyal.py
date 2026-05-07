"""Coverage for `detectar_anomalies_senyal`.

Anchor for the 2026-05-08 lesson: when Last.fm changes its
autocorrect/fallback behaviour and starts pointing variant queries
(live, remix, remasteritzada) at the main studio recording, day-
over-day deltas spike implausibly. The track-switch guard in
`algorisme._compute_weekly_plays` catches the specific case where
`lastfm_returned_track` flips between samples; this command is the
broader net for any anomaly we haven't anticipated.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from music.models import Album, Artista, Canco, Territori
from ranking.models import SenyalDiari


@pytest.fixture(autouse=True)
def territori_cat():
    Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Catalunya"})


def _mk_canco(nom="Track", isrc="XX000000ANOM"):
    a = Artista.objects.create(nom="Test", lastfm_nom="Test", aprovat=True)
    al = Album.objects.create(artista=a, nom="Album", data_llancament=date(2024, 1, 1))
    return Canco.objects.create(
        artista=a,
        album=al,
        nom=nom,
        isrc=isrc,
        verificada=True,
        activa=True,
        data_llancament=date(2024, 1, 1),
    )


def _seed_signals(canco, today, deltas, base=10):
    """Create SenyalDiari rows for `len(deltas)+1` consecutive days
    ending on `today`. `deltas[i]` is the day-i+1 increment over
    `base + sum(deltas[:i])`."""
    pc = base
    rows = []
    rows.append(
        SenyalDiari.objects.create(
            canco=canco,
            data=today - timedelta(days=len(deltas)),
            lastfm_playcount=pc,
            lastfm_listeners=1,
        )
    )
    for i, d in enumerate(deltas, start=1):
        pc += d
        rows.append(
            SenyalDiari.objects.create(
                canco=canco,
                data=today - timedelta(days=len(deltas) - i),
                lastfm_playcount=pc,
                lastfm_listeners=1,
            )
        )
    return rows


@pytest.mark.django_db
def test_anomaly_flags_today_row_when_delta_spikes():
    today = date(2026, 5, 7)
    c = _mk_canco("Spiker")
    # 6 days of small (0-3) deltas, then today: +6900 plays — the
    # Smoking Souls / Pau Vallvé pattern.
    _seed_signals(c, today, [0, 0, 1, 0, 1, 0, 6900])

    out = StringIO()
    call_command("detectar_anomalies_senyal", "--data", today.isoformat(), stdout=out)
    today_row = SenyalDiari.objects.get(canco=c, data=today)
    assert today_row.corregit is True
    assert "anomaly" in today_row.error_msg
    assert "WORK_DONE=1" in out.getvalue()


@pytest.mark.django_db
def test_steady_growth_not_flagged():
    today = date(2026, 5, 7)
    c = _mk_canco("Steady")
    # 7 days of consistent ~5-play growth — exactly the kind of
    # honest day-to-day movement we must NEVER flag.
    _seed_signals(c, today, [5, 4, 6, 5, 5, 6, 5])

    out = StringIO()
    call_command("detectar_anomalies_senyal", "--data", today.isoformat(), stdout=out)
    today_row = SenyalDiari.objects.get(canco=c, data=today)
    assert today_row.corregit is False
    assert "WORK_DONE=0" in out.getvalue()


@pytest.mark.django_db
def test_below_floor_not_flagged():
    """A jump from 0 to 50 plays in a day looks huge multiplicatively
    but is below the absolute noise floor (default 100). Don't flag."""
    today = date(2026, 5, 7)
    c = _mk_canco("Tiny")
    _seed_signals(c, today, [0, 0, 0, 0, 0, 0, 50])

    out = StringIO()
    call_command("detectar_anomalies_senyal", "--data", today.isoformat(), stdout=out)
    today_row = SenyalDiari.objects.get(canco=c, data=today)
    assert today_row.corregit is False


@pytest.mark.django_db
def test_short_history_skipped():
    """A canço with only 1-2 days of signal can't be judged. Don't
    flag — better to wait for history."""
    today = date(2026, 5, 7)
    c = _mk_canco("New")
    _seed_signals(c, today, [10000])  # only 2 rows

    out = StringIO()
    call_command("detectar_anomalies_senyal", "--data", today.isoformat(), stdout=out)
    today_row = SenyalDiari.objects.get(canco=c, data=today)
    assert today_row.corregit is False


@pytest.mark.django_db
def test_dry_run_does_not_modify():
    today = date(2026, 5, 7)
    c = _mk_canco("Spiker")
    _seed_signals(c, today, [0, 0, 1, 0, 1, 0, 6900])

    out = StringIO()
    call_command(
        "detectar_anomalies_senyal",
        "--data",
        today.isoformat(),
        "--dry-run",
        stdout=out,
    )
    today_row = SenyalDiari.objects.get(canco=c, data=today)
    assert today_row.corregit is False  # not modified
    assert "--dry-run" in out.getvalue()
    assert "WORK_DONE=1" in out.getvalue()


@pytest.mark.django_db
def test_already_corrected_row_skipped():
    """If something else has already flagged today's row (e.g. the
    drift detector inside obtenir_senyal), don't re-process it."""
    today = date(2026, 5, 7)
    c = _mk_canco("Already")
    _seed_signals(c, today, [0, 0, 1, 0, 1, 0, 6900])
    SenyalDiari.objects.filter(canco=c, data=today).update(corregit=True)

    out = StringIO()
    call_command("detectar_anomalies_senyal", "--data", today.isoformat(), stdout=out)
    # Row stays as it was — we don't double-count.
    assert "WORK_DONE=0" in out.getvalue()


@pytest.mark.django_db
def test_threshold_tunable_via_flag():
    """Operator can tighten/loosen the multiplier."""
    today = date(2026, 5, 7)
    c = _mk_canco("Borderline")
    # 5× the ~10-play median: should NOT trigger at default 20×, but
    # SHOULD trigger at multiplier=3.
    _seed_signals(c, today, [10, 10, 10, 10, 10, 10, 110])

    out = StringIO()
    call_command(
        "detectar_anomalies_senyal",
        "--data",
        today.isoformat(),
        "--multiplier",
        "3",
        stdout=out,
    )
    today_row = SenyalDiari.objects.get(canco=c, data=today)
    assert today_row.corregit is True
