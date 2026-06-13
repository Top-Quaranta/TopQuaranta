"""Staff artistes list must not flood with descartats when the
"actius" filter is lifted (to hunt duplicates to merge).

Descartat = (aprovat=False, pendent_review=False) — terminal state.
- aprovat=0 (No aprovats) → pendents only, NOT descartats.
- aprovat="" (Tots)       → approved + pendents, NOT descartats.
- opt-in inclou_descartats=1 → descartats reachable again.
- aprovat=1 (Aprovats)    → unaffected.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from music.models import Artista


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="artistes_descartats_tester",
        email="ad@example.com",
        password="x",
        is_staff=True,
    )
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def three_states(db):
    aprovat = Artista.objects.create(
        nom="Aprovat U", slug="aprovat-u", aprovat=True, pendent_review=False
    )
    pendent = Artista.objects.create(
        nom="Pendent U", slug="pendent-u", aprovat=False, pendent_review=True
    )
    descartat = Artista.objects.create(
        nom="Descartat U", slug="descartat-u", aprovat=False, pendent_review=False
    )
    return aprovat, pendent, descartat


def _noms(resp):
    data = resp.json()
    rows = data.get("results", data) if isinstance(data, dict) else data
    return {r["nom"] for r in rows}


@pytest.mark.django_db
def test_no_aprovats_excludes_descartats(staff_client, three_states):
    _, pendent, descartat = three_states
    noms = _noms(staff_client.get("/api/v1/staff/artistes/?aprovat=0"))
    assert pendent.nom in noms
    assert descartat.nom not in noms


@pytest.mark.django_db
def test_tots_excludes_descartats(staff_client, three_states):
    aprovat, pendent, descartat = three_states
    noms = _noms(staff_client.get("/api/v1/staff/artistes/?aprovat="))
    assert {aprovat.nom, pendent.nom} <= noms
    assert descartat.nom not in noms


@pytest.mark.django_db
def test_opt_in_shows_descartats(staff_client, three_states):
    _, _, descartat = three_states
    noms = _noms(
        staff_client.get("/api/v1/staff/artistes/?aprovat=0&inclou_descartats=1")
    )
    assert descartat.nom in noms


@pytest.mark.django_db
def test_aprovats_unaffected(staff_client, three_states):
    aprovat, pendent, descartat = three_states
    noms = _noms(staff_client.get("/api/v1/staff/artistes/?aprovat=1"))
    assert noms == {aprovat.nom}
