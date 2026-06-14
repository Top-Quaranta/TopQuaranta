"""Guards for the staff "enviar avisos top" endpoint (Slice F2)."""

from __future__ import annotations

import datetime

import pytest
from rest_framework.test import APIClient

from comptes.models import AvisTopEnviat
from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="avisos_tester", email="a@example.com", password="x", is_staff=True
    )
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def _seed_top(db):
    # Minimal PPCC top so the command resolves a week (else it STOPs
    # with "no TopSetmanal de PPCC").
    a = Artista.objects.create(nom="Top A", slug="top-a", aprovat=True)
    al = Album.objects.create(nom="Al", slug="al-top-a", artista=a)
    c = Canco.objects.create(
        nom="C", slug="c-top-a", artista=a, album=al, verificada=True, activa=True
    )
    setmana = datetime.date(2026, 6, 8)
    setmana -= datetime.timedelta(days=setmana.weekday())
    TopSetmanal.objects.create(
        canco=c, territori="PPCC", setmana=setmana, posicio=1, score_setmanal=1.0
    )


@pytest.mark.django_db
def test_dry_run_default_no_send(staff_client, _seed_top):
    """No `send` -> DRY-RUN: 200, send=False, no ledger rows written."""
    r = staff_client.post("/api/v1/staff/avisos-top/enviar/", {}, format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["ok"] is True and body["send"] is False
    assert "stdout" in body
    assert AvisTopEnviat.objects.count() == 0


@pytest.mark.django_db
def test_requires_staff(db):
    """Anonymous (non-staff) is rejected."""
    r = APIClient().post("/api/v1/staff/avisos-top/enviar/", {}, format="json")
    assert r.status_code in (401, 403)
