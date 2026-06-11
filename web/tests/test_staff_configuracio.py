"""Guards for the staff config endpoint (/staff/configuracio/).

The reflection serializer exposes each field's `type` so the SPA can pick
an input widget (long TextField → textarea, short → input). Round-trip
GET/PATCH keeps the value identical.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from comptes.models import Usuari


@pytest.fixture
def staff_client(db):
    u = Usuari.objects.create_user(
        username="cfgtester", email="cfg@example.com", password="x", is_staff=True
    )
    c = APIClient()
    c.force_authenticate(user=u)
    return c


def _fields(resp):
    return {f["name"]: f for f in resp.data["fields"]}


@pytest.mark.django_db
def test_get_exposes_field_type(staff_client):
    r = staff_client.get("/api/v1/staff/configuracio/")
    assert r.status_code == 200
    fields = _fields(r)
    # editorial_veu is a TextField → the SPA renders it as a textarea.
    assert fields["editorial_veu"]["type"] == "TextField"
    # A numeric coefficient is NOT a TextField (stays a one-line input).
    assert fields["min_escoltes_top"]["type"] != "TextField"


@pytest.mark.django_db
def test_editorial_veu_help_text_says_blank_generates_nothing(staff_client):
    r = staff_client.get("/api/v1/staff/configuracio/")
    help_text = _fields(r)["editorial_veu"]["help"]
    assert "no genera res" in help_text


@pytest.mark.django_db
def test_round_trip_patch_get_identical(staff_client):
    voice = "Veu càlida i propera.\nMai cursi.\nFrases curtes."
    p = staff_client.patch(
        "/api/v1/staff/configuracio/", {"editorial_veu": voice}, format="json"
    )
    assert p.status_code == 200
    g = staff_client.get("/api/v1/staff/configuracio/")
    assert _fields(g)["editorial_veu"]["value"] == voice
