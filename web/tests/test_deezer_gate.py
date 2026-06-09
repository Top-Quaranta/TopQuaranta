"""Guards for the Deezer approval gate (2026-06).

An artist may only be approved with at least one ArtistaDeezer anchor, on
BOTH approval paths (pendent_aprovar + artista_detail PATCH aprovat=True),
mirroring the existing localitat check. A Deezer id that already belongs
to another artist returns a 409 (no longer a silent no-op). The
`tornar_pendents_sense_deezer` command is idempotent.
"""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from comptes.models import Usuari
from music.models import Artista, ArtistaDeezer, ArtistaLocalitat, Municipi, Territori


@pytest.fixture
def staff_client(db):
    u = Usuari.objects.create_user(
        username="deezergate", email="dg@example.com", password="x", is_staff=True
    )
    c = APIClient()
    c.force_authenticate(user=u)
    return c


@pytest.fixture
def municipi(db):
    t, _ = Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Principat"})
    return Municipi.objects.create(nom="Vila", comarca="Comarca", territori=t)


# ── pendent_aprovar gate ─────────────────────────────────────────────


@pytest.mark.django_db
def test_aprovar_rejects_without_deezer(staff_client, municipi):
    a = Artista.objects.create(nom="Sense DZ", aprovat=False, pendent_review=True)
    r = staff_client.post(
        f"/api/v1/staff/pendents/{a.pk}/aprovar/", {"municipi_id": municipi.pk}
    )
    assert r.status_code == 400
    assert "Deezer" in r.json()["error"]
    a.refresh_from_db()
    assert a.aprovat is False  # not approved


# NOTE: the pendent_aprovar happy path (approve WITH a deezer_id) is not
# unit-tested here because its proposta-auto-approve step uses a JSONField
# `__contains` lookup that the SQLite test backend rejects (pre-existing,
# unrelated to this gate). The with-Deezer approval is covered through the
# artista_detail PATCH path below, which has no such query.


# ── artista_detail PATCH gate ────────────────────────────────────────


@pytest.mark.django_db
def test_patch_approve_rejected_without_deezer(staff_client, municipi):
    a = Artista.objects.create(nom="Edit sense DZ", aprovat=False)
    ArtistaLocalitat.objects.create(artista=a, municipi=municipi)
    r = staff_client.patch(
        f"/api/v1/staff/artistes/{a.pk}/", {"aprovat": True}, format="json"
    )
    assert r.status_code == 400
    assert "Deezer" in r.json()["error"]
    a.refresh_from_db()
    assert a.aprovat is False


@pytest.mark.django_db
def test_patch_approve_with_deezer_in_same_call(staff_client, municipi):
    a = Artista.objects.create(nom="Edit amb DZ", aprovat=False)
    ArtistaLocalitat.objects.create(artista=a, municipi=municipi)
    r = staff_client.patch(
        f"/api/v1/staff/artistes/{a.pk}/",
        {"aprovat": True, "deezer_ids": [555]},
        format="json",
    )
    assert r.status_code == 200, r.content
    a.refresh_from_db()
    assert a.aprovat is True
    assert a.deezer_ids.filter(deezer_id=555).exists()


@pytest.mark.django_db
def test_patch_deezer_collision_returns_409(staff_client):
    owner = Artista.objects.create(nom="Propietari", aprovat=False)
    ArtistaDeezer.objects.create(artista=owner, deezer_id=999, principal=True)
    other = Artista.objects.create(nom="Altre", aprovat=False)
    r = staff_client.patch(
        f"/api/v1/staff/artistes/{other.pk}/",
        {"deezer_ids": [999]},
        format="json",
    )
    assert r.status_code == 409
    body = r.json()
    assert body["owner_pk"] == owner.pk
    assert "Propietari" in body["error"]
    # Nothing persisted on the other artist (rolled back).
    assert not other.deezer_ids.exists()


# ── data command idempotency ─────────────────────────────────────────


@pytest.mark.django_db
def test_command_moves_ghosts_and_is_idempotent():
    ghost = Artista.objects.create(nom="Fantasma", aprovat=True, pendent_review=False)
    keeper = Artista.objects.create(nom="Bo", aprovat=True, pendent_review=False)
    ArtistaDeezer.objects.create(artista=keeper, deezer_id=42, principal=True)

    out = io.StringIO()
    call_command("tornar_pendents_sense_deezer", stdout=out)
    ghost.refresh_from_db()
    keeper.refresh_from_db()
    assert ghost.aprovat is False and ghost.pendent_review is True
    assert keeper.aprovat is True  # untouched (has Deezer)

    # Second run finds nothing to do.
    out2 = io.StringIO()
    call_command("tornar_pendents_sense_deezer", stdout=out2)
    assert "Res a fer" in out2.getvalue()


@pytest.mark.django_db
def test_command_dry_run_changes_nothing():
    ghost = Artista.objects.create(nom="Fantasma2", aprovat=True, pendent_review=False)
    out = io.StringIO()
    call_command("tornar_pendents_sense_deezer", "--dry-run", stdout=out)
    assert "DRY-RUN" in out.getvalue()
    ghost.refresh_from_db()
    assert ghost.aprovat is True  # unchanged
