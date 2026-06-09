"""Guards for the matrix day INDICATOR (item C, 2026-06).

The editable `MatriuPublicacio.dia_setmana` field + `pot_distribuir_avui`
gate were removed (redundant with the calendar, and a no-op since every
cell was null). The matrix now exposes a READ-ONLY publish-day indicator
derived from the real calendar/cron (`social.calendari.publish_weekdays_for`),
including the newsletter's Sunday send. The only editable control is
`actiu`. NEVER triggers a real publication.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from comptes.models import Usuari
from music.models import StaffAuditLog
from ranking.models import MatriuPublicacio
from social.calendari import NEWSLETTER_PUBLISH_WEEKDAY, publish_weekdays_for


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


def test_push_channels_follow_calendar():
    # weekday(): Mon=0 … Sun=6. top_ppcc=Sat, territorial=Mon+Wed,
    # singles=Fri, albums=Tue (matches social/calendari.py CALENDARI).
    for canal in ("instagram", "mastodon", "bluesky", "telegram"):
        assert publish_weekdays_for(canal, "top_ppcc") == [5]
        assert publish_weekdays_for(canal, "top_territorial") == [0, 2]
        assert publish_weekdays_for(canal, "nous_singles") == [4]
        assert publish_weekdays_for(canal, "nous_albums") == [1]


def test_newsletter_is_sunday_for_ppcc_only():
    # Newsletter only sends the PPCC top, on Sunday (its own enviar_newsletter
    # cron, NOT the calendari). Everything else → empty (not published).
    assert NEWSLETTER_PUBLISH_WEEKDAY == 6  # Sunday — must match the cron
    assert publish_weekdays_for("newsletter", "top_ppcc") == [6]
    assert publish_weekdays_for("newsletter", "top_territorial") == []
    assert publish_weekdays_for("newsletter", "nous_singles") == []
    assert publish_weekdays_for("newsletter", "nous_albums") == []


# ── GET exposes the indicator ────────────────────────────────────────


@pytest.mark.django_db
def test_get_matriu_exposes_dies_publicacio(staff_client):
    r = staff_client.get("/api/v1/staff/social/matriu/")
    assert r.status_code == 200
    cells = {(c["canal"], c["tipus"]): c for c in r.data["cells"]}
    # No editable day field is leaked anymore.
    assert "dia_setmana" not in cells[("mastodon", "top_ppcc")]
    # Push channel: top_ppcc → Saturday.
    assert cells[("mastodon", "top_ppcc")]["dies_publicacio"] == [5]
    # Territorial → Monday + Wednesday.
    assert cells[("mastodon", "top_territorial")]["dies_publicacio"] == [0, 2]
    # Newsletter top_ppcc → Sunday.
    assert cells[("newsletter", "top_ppcc")]["dies_publicacio"] == [6]
    # Newsletter never publishes territorial → empty (UI renders "—").
    assert cells[("newsletter", "top_territorial")]["dies_publicacio"] == []


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
