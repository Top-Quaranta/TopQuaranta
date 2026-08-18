"""Guards for the matrix day INDICATOR (item C, 2026-06).

The editable `MatriuPublicacio.dia_setmana` field + `pot_distribuir_avui`
gate were removed (redundant with the calendar, and a no-op since every
cell was null). The matrix now exposes a READ-ONLY publish-day indicator
derived from the real calendar/cron (`social.calendari.publish_weekdays_for`),
including the newsletter's Sunday send. The only editable control is
`actiu`. NEVER triggers a real publication.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from comptes.models import Usuari
from music.models import StaffAuditLog
from ranking.models import MatriuPublicacio
from social.calendari import (
    CALENDARI,
    NEWSLETTER_PUBLISH_WEEKDAY,
    publish_weekdays_for,
)


def _set(*, canal, tipus, actiu=True):
    """Upsert a matrix cell (migration 0020 seeds rows → create collides)."""
    MatriuPublicacio.objects.update_or_create(
        canal=canal, tipus=tipus, defaults={"actiu": actiu}
    )


@pytest.fixture
def staff_client(db):
    u = Usuari.objects.create_user(
        username="matriuday", email="md@example.com", password="x", is_staff=True
    )
    c = APIClient()
    c.force_authenticate(user=u)
    return c


# ── indicator derivation (publish_weekdays_for) ──────────────────────

_CRON_FILE = Path(__file__).resolve().parents[2] / "deploy" / "cron.topquaranta"
_PUSH_CANALS = ("instagram", "mastodon", "bluesky", "telegram")
_FEED_TIPUS = ("top_ppcc", "top_territorial", "nous_singles", "nous_albums")


def _cron_weekdays(command_pattern: str) -> set[int]:
    """Python weekdays (Mon=0 … Sun=6) on which a cron line whose command
    matches `command_pattern` fires. Parsed from `deploy/cron.topquaranta`
    (the real schedule) so the tests never mirror a literal weekday."""
    days: set[int] = set()
    for line in _CRON_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 7 or not re.search(command_pattern, " ".join(parts[6:])):
            continue
        for tok in parts[4].split(","):
            days.add((int(tok) - 1) % 7)  # cron: Sun=0 … Sat=6 → Python
    return days


def test_push_channels_follow_calendar():
    # Property: for the push channels the indicator is derived from the
    # real `CALENDARI` (one weekday per slot of that tipus, no invented
    # day), it is never empty for a tipus the calendar carries, it is
    # identical across the four push channels, and every day it reports is
    # a day the push-channel cron (`publicar_canal`) actually fires on.
    cron_days = _cron_weekdays(r"publicar_canal --channel mastodon")
    for tipus in _FEED_TIPUS:
        expected = sorted({s.weekday for s in CALENDARI if s.tipus == tipus})
        assert expected, tipus  # the calendar does carry this tipus
        for canal in _PUSH_CANALS:
            got = publish_weekdays_for(canal, tipus)
            assert got == expected, (canal, tipus)
            assert set(got) <= cron_days, (canal, tipus, got, cron_days)
    # A tipus the calendar never carries → [] (honest, no day invented).
    assert publish_weekdays_for("mastodon", "no_existeix") == []


def test_newsletter_is_sunday_for_ppcc_only():
    # Newsletter only sends the PPCC top, on Sunday (its own enviar_newsletter
    # cron, NOT the calendari). Everything else → empty (not published).
    # Property: the Sunday constant is checked against the real cron line
    # in deploy/cron.topquaranta, not against a literal; and no tipus other
    # than top_ppcc gets a day.
    cron_days = _cron_weekdays(r"\benviar_newsletter\b")
    assert cron_days == {NEWSLETTER_PUBLISH_WEEKDAY}
    assert publish_weekdays_for("newsletter", "top_ppcc") == [
        NEWSLETTER_PUBLISH_WEEKDAY
    ]
    for tipus in _FEED_TIPUS:
        if tipus != "top_ppcc":
            assert publish_weekdays_for("newsletter", tipus) == []


# ── GET exposes the indicator ────────────────────────────────────────


@pytest.mark.django_db
def test_get_matriu_exposes_dies_publicacio(staff_client):
    # Property: no cell leaks the removed editable `dia_setmana`; every
    # cell's `dies_publicacio` equals `publish_weekdays_for(canal, tipus)`
    # (the calendar-derived source), and the newsletter × territorial cell
    # is empty (UI renders "—").
    r = staff_client.get("/api/v1/staff/social/matriu/")
    assert r.status_code == 200
    assert r.data["cells"]
    for c in r.data["cells"]:
        assert "dia_setmana" not in c
        assert c["dies_publicacio"] == publish_weekdays_for(c["canal"], c["tipus"])
    cells = {(c["canal"], c["tipus"]): c for c in r.data["cells"]}
    assert cells[("newsletter", "top_territorial")]["dies_publicacio"] == []
    assert cells[("mastodon", "top_ppcc")]["dies_publicacio"]  # non-empty


# ── toggle is actiu-only ─────────────────────────────────────────────


@pytest.mark.django_db
def test_toggle_flips_actiu_only(staff_client):
    _set(canal="mastodon", tipus="top_ppcc", actiu=True)
    r = staff_client.post(
        "/api/v1/staff/social/matriu/toggle/",
        {"canal": "mastodon", "tipus": "top_ppcc"},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["actiu"] is False  # flipped
    assert "dia_setmana" not in r.data  # no day field anymore
    assert StaffAuditLog.objects.filter(action="config_update").exists()


@pytest.mark.django_db
def test_toggle_explicit_actiu_value(staff_client):
    _set(canal="mastodon", tipus="top_ppcc", actiu=True)
    r = staff_client.post(
        "/api/v1/staff/social/matriu/toggle/",
        {"canal": "mastodon", "tipus": "top_ppcc", "actiu": False},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["actiu"] is False
    assert (
        MatriuPublicacio.objects.get(canal="mastodon", tipus="top_ppcc").actiu is False
    )
