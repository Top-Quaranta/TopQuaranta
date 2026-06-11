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


@pytest.mark.django_db
def test_distribution_section_hidden_from_config_view(staff_client):
    """Distribution lives in the cockpit/matrix, not Configuració. The
    distribution fields must NOT appear in the view, the sections list must
    not include 'Distribució i canals', and a PATCH to a distribution field
    is ignored (the field keeps its value)."""
    from ranking.models import ConfiguracioGlobal

    r = staff_client.get("/api/v1/staff/configuracio/")
    fields = _fields(r)
    for hidden in (
        "distribucio_activa",
        "instagram_actiu",
        "newsletter_actiu",
        "rss_actiu",
        "delay_instagram_min",
        "newsletter_publicacio_pont_actiu",
    ):
        assert hidden not in fields, f"{hidden} should be hidden from Config"
    assert "Distribució i canals" not in r.data["sections"]
    # Ranking/soft-cap/editorial stay visible.
    assert "min_escoltes_top" in fields
    assert "soft_cap_actiu" in fields
    assert "editorial_veu" in fields

    # A PATCH targeting a distribution field is a no-op (cockpit owns it).
    ConfiguracioGlobal.objects.update_or_create(
        pk=1, defaults={"instagram_actiu": True}
    )
    r2 = staff_client.patch(
        "/api/v1/staff/configuracio/", {"instagram_actiu": "False"}, format="json"
    )
    assert r2.status_code == 200
    assert ConfiguracioGlobal.load().instagram_actiu is True  # unchanged
