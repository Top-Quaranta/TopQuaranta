"""Guards for the matrix `dia_setmana` weekday gate (5a, 2026-06).

Additive + neutral: with `dia_setmana=None` (the default) the new
`pot_distribuir_avui` gate behaves exactly like `actiu_per`, so the
publishers are unchanged until staff pins a day. NEVER triggers a real
publication.
"""

from __future__ import annotations

import datetime

import pytest
from rest_framework.test import APIClient

from comptes.models import Usuari
from music.models import StaffAuditLog
from ranking.models import MatriuPublicacio

MON = datetime.date(2026, 6, 1)  # Monday → weekday() == 0
TUE = datetime.date(2026, 6, 2)  # Tuesday → weekday() == 1


def _set(*, canal, tipus, actiu=True, dia_setmana=None):
    """Upsert a matrix cell (migration 0020 seeds rows → create collides)."""
    MatriuPublicacio.objects.update_or_create(
        canal=canal,
        tipus=tipus,
        defaults={"actiu": actiu, "dia_setmana": dia_setmana},
    )


@pytest.fixture
def staff_client(db):
    u = Usuari.objects.create_user(
        username="matriuday", email="md@example.com", password="x", is_staff=True
    )
    c = APIClient()
    c.force_authenticate(user=u)
    return c


# ── gate semantics ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_missing_row_is_fail_open():
    assert MatriuPublicacio.pot_distribuir_avui("mastodon", "top_ppcc", today=MON)


@pytest.mark.django_db
def test_inactive_cell_never_distributes():
    _set(canal="mastodon", tipus="top_ppcc", actiu=False)
    assert not MatriuPublicacio.pot_distribuir_avui("mastodon", "top_ppcc", today=MON)


@pytest.mark.django_db
def test_null_day_is_neutral_any_day():
    """dia_setmana=None → publishes on any day (same as actiu_per)."""
    _set(canal="mastodon", tipus="top_ppcc", actiu=True, dia_setmana=None)
    for d in (MON, TUE):
        assert MatriuPublicacio.pot_distribuir_avui("mastodon", "top_ppcc", today=d)
        # Neutrality: with a null day the day-gate matches the pure actiu bit.
        assert MatriuPublicacio.pot_distribuir_avui(
            "mastodon", "top_ppcc", today=d
        ) == MatriuPublicacio.actiu_per("mastodon", "top_ppcc")


@pytest.mark.django_db
def test_pinned_day_gates_to_that_weekday():
    _set(canal="mastodon", tipus="top_ppcc", actiu=True, dia_setmana=0)  # Monday
    assert MatriuPublicacio.pot_distribuir_avui("mastodon", "top_ppcc", today=MON)
    assert not MatriuPublicacio.pot_distribuir_avui("mastodon", "top_ppcc", today=TUE)


@pytest.mark.django_db
def test_pinned_day_still_respects_inactive():
    _set(canal="mastodon", tipus="top_ppcc", actiu=False, dia_setmana=0)
    assert not MatriuPublicacio.pot_distribuir_avui("mastodon", "top_ppcc", today=MON)


# ── endpoint ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_get_matriu_exposes_dia_setmana_and_dies(staff_client):
    _set(canal="mastodon", tipus="top_ppcc", actiu=True, dia_setmana=5)
    r = staff_client.get("/api/v1/staff/social/matriu/")
    assert r.status_code == 200
    assert any(d["value"] == 5 and d["label"] == "Dissabte" for d in r.data["dies"])
    cell = next(
        c
        for c in r.data["cells"]
        if c["canal"] == "mastodon" and c["tipus"] == "top_ppcc"
    )
    assert cell["dia_setmana"] == 5


@pytest.mark.django_db
def test_toggle_sets_day_without_flipping_actiu(staff_client):
    _set(canal="mastodon", tipus="top_ppcc", actiu=True, dia_setmana=None)
    r = staff_client.post(
        "/api/v1/staff/social/matriu/toggle/",
        {"canal": "mastodon", "tipus": "top_ppcc", "dia_setmana": 5},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["dia_setmana"] == 5
    assert r.data["actiu"] is True  # NOT flipped by a day edit
    cell = MatriuPublicacio.objects.get(canal="mastodon", tipus="top_ppcc")
    assert cell.dia_setmana == 5 and cell.actiu is True
    # The day change is audited.
    assert StaffAuditLog.objects.filter(action="config_update").exists()


@pytest.mark.django_db
def test_toggle_clears_day_with_null(staff_client):
    _set(canal="mastodon", tipus="top_ppcc", actiu=True, dia_setmana=3)
    r = staff_client.post(
        "/api/v1/staff/social/matriu/toggle/",
        {"canal": "mastodon", "tipus": "top_ppcc", "dia_setmana": None},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["dia_setmana"] is None


@pytest.mark.django_db
def test_toggle_rejects_out_of_range_day(staff_client):
    _set(canal="mastodon", tipus="top_ppcc", actiu=True)
    r = staff_client.post(
        "/api/v1/staff/social/matriu/toggle/",
        {"canal": "mastodon", "tipus": "top_ppcc", "dia_setmana": 9},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_toggle_actiu_still_works_unchanged(staff_client):
    """The legacy actiu-flip path (no dia_setmana in body) is preserved."""
    _set(canal="mastodon", tipus="top_ppcc", actiu=True)
    r = staff_client.post(
        "/api/v1/staff/social/matriu/toggle/",
        {"canal": "mastodon", "tipus": "top_ppcc"},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["actiu"] is False  # flipped
