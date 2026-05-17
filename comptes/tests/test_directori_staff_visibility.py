"""Staff can see every active profile in the community directory.

Fase 1.5.B partial (2026-05-17): a staff admin needs to be able to
reach users for one-on-one moderation correspondence even when those
users haven't self-published in the directory. The directory listing
is bifurcated: staff get every active profile, regular users keep the
`visible_directori=True` gate intact. Each row in the staff response
carries the `visible_directori` flag so the SPA can render a clear
"perfil no públic" badge.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from comptes.models import PerfilUsuari, Usuari

DIRECTORI_URL = "/api/v1/comunitat/directori/"
MISSATGE_CREAR_URL = "/api/v1/missatges/nou/"


@pytest.fixture
def staff(db):
    user = Usuari.objects.create_user(
        username="staffmate",
        email="staff@example.com",
        password="x",
        is_staff=True,
        is_active=True,
    )
    # PerfilUsuari is created by post_save signal; ensure deterministic
    # state in the directory by NOT publishing the staff member.
    PerfilUsuari.objects.filter(usuari=user).update(visible_directori=False)
    return user


@pytest.fixture
def public_user(db):
    user = Usuari.objects.create_user(
        username="publicuser",
        email="public@example.com",
        password="x",
    )
    PerfilUsuari.objects.filter(usuari=user).update(visible_directori=True)
    return user


@pytest.fixture
def private_user(db):
    user = Usuari.objects.create_user(
        username="privateuser",
        email="private@example.com",
        password="x",
    )
    PerfilUsuari.objects.filter(usuari=user).update(visible_directori=False)
    return user


def _usernames(payload: dict) -> set[str]:
    return {row["username"] for row in payload["results"]}


@pytest.mark.django_db
def test_regular_user_sees_only_public_profiles(public_user, private_user):
    """A non-staff viewer keeps the original gate: only profiles with
    `visible_directori=True` show up."""
    client = APIClient()
    client.force_authenticate(public_user)
    resp = client.get(DIRECTORI_URL)
    assert resp.status_code == 200
    usernames = _usernames(resp.data)
    assert "publicuser" in usernames
    assert "privateuser" not in usernames


@pytest.mark.django_db
def test_staff_sees_private_profiles_with_visibility_flag(
    staff, public_user, private_user
):
    """Staff sees every active profile, regardless of the flag, and
    each row carries `visible_directori` so the SPA can render the
    'perfil no públic' badge."""
    client = APIClient()
    client.force_authenticate(staff)
    resp = client.get(DIRECTORI_URL)
    assert resp.status_code == 200
    rows = {row["username"]: row for row in resp.data["results"]}
    assert "publicuser" in rows
    assert "privateuser" in rows
    assert rows["publicuser"]["visible_directori"] is True
    assert rows["privateuser"]["visible_directori"] is False


@pytest.mark.django_db
def test_inactive_users_excluded_even_for_staff(staff, public_user):
    """Staff still doesn't see deactivated accounts — those are
    operationally gone, not just non-public."""
    public_user.is_active = False
    public_user.save(update_fields=["is_active"])
    client = APIClient()
    client.force_authenticate(staff)
    resp = client.get(DIRECTORI_URL)
    assert resp.status_code == 200
    assert "publicuser" not in _usernames(resp.data)


@pytest.mark.django_db
def test_regular_user_cannot_dm_private_user_via_directory(public_user, private_user):
    """The implicit gate is discoverability: a non-staff user cannot
    see `private_user` in the directory and therefore has no UI path
    to obtain their pk for the DM endpoint. This test locks that
    contract in at the directory level. (The `missatge_crear` endpoint
    itself is intentionally permissive on lookup; the gate is
    discoverability, not validation.)"""
    client = APIClient()
    client.force_authenticate(public_user)
    resp = client.get(DIRECTORI_URL)
    assert resp.status_code == 200
    assert "privateuser" not in _usernames(resp.data)


@pytest.mark.django_db
def test_staff_can_dm_private_user(staff, private_user):
    """End-to-end: staff sees the private user in the directory, then
    posts to `missatge_crear` with their pk and it succeeds."""
    client = APIClient()
    client.force_authenticate(staff)
    directori = client.get(DIRECTORI_URL)
    target_row = next(
        r for r in directori.data["results"] if r["username"] == "privateuser"
    )
    resp = client.post(
        MISSATGE_CREAR_URL,
        {
            "destinatari_pk": target_row["usuari_id"],
            "cos": "Hola, tinc una pregunta sobre el teu perfil.",
            "assumpte": "Moderació",
        },
        format="json",
    )
    assert resp.status_code == 201
