"""Admin pseudo-user DM relay.

PR #A (2026-05-18): a DM addressed to the `admin` pseudo-user
(settings.ADMIN_INBOX_USERNAME) is fanned out by email to every
active staff member in addition to the admin mailbox itself. DMs to
any other user keep the prior 1:1 behaviour (single recipient,
opt-out honoured).

The pseudo-user is seeded by migration 0016_admin_pseudouser; here we
construct it directly so the tests don't depend on migration state.
"""

from __future__ import annotations

import pytest
from django.core import mail
from rest_framework.test import APIClient

from comptes.models import Missatge, PerfilUsuari, Usuari


MISSATGE_CREAR_URL = "/api/v1/missatges/nou/"


@pytest.fixture
def admin_inbox(db):
    """Pseudo-user that fronts the staff inbox. The seed migration
    0016_admin_pseudouser already creates the row during test setup;
    we fetch it (or fall back to create_user when the migration
    didn't run, e.g. in an unmigrated test DB) and ensure the
    PerfilUsuari is in a deterministic state. The `notificar_missatges_email
    =False` setting exercises the branch where the staff fan-out
    bypasses the pseudo-user's opt-out."""
    user, _ = Usuari.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@topquaranta.cat",
            "first_name": "Admin",
            "last_name": "TopQuaranta",
            "is_active": True,
            "is_staff": False,
        },
    )
    PerfilUsuari.objects.update_or_create(
        usuari=user,
        defaults={
            "nom_public": "Admin TopQuaranta",
            "visible_directori": True,
            "notificar_missatges_email": False,
        },
    )
    return user


@pytest.fixture
def staff_a(db):
    return Usuari.objects.create_user(
        username="staffA",
        email="staffa@example.com",
        password="x",
        is_staff=True,
        is_active=True,
    )


@pytest.fixture
def staff_b(db):
    return Usuari.objects.create_user(
        username="staffB",
        email="staffb@example.com",
        password="x",
        is_staff=True,
        is_active=True,
    )


@pytest.fixture
def staff_inactive(db):
    """Inactive staff: their email must NOT receive the fan-out."""
    return Usuari.objects.create_user(
        username="staffOLD",
        email="staffold@example.com",
        password="x",
        is_staff=True,
        is_active=False,
    )


@pytest.fixture
def regular_user(db):
    return Usuari.objects.create_user(
        username="regular",
        email="regular@example.com",
        password="x",
    )


@pytest.fixture
def another_user(db):
    user = Usuari.objects.create_user(
        username="bob",
        email="bob@example.com",
        password="x",
    )
    PerfilUsuari.objects.filter(usuari=user).update(notificar_missatges_email=True)
    return user


@pytest.mark.django_db
def test_dm_to_admin_fans_out_to_all_active_staff(
    regular_user, admin_inbox, staff_a, staff_b, staff_inactive
):
    """End-to-end: a regular user POSTs a DM to the admin pseudo-user,
    every active staff member's email shows up in the outbox along
    with admin@topquaranta.cat. Inactive staff are excluded."""
    client = APIClient()
    client.force_authenticate(regular_user)
    resp = client.post(
        MISSATGE_CREAR_URL,
        {
            "destinatari_pk": admin_inbox.pk,
            "cos": "Hola staff, tinc una pregunta.",
            "assumpte": "Pregunta",
        },
        format="json",
    )
    assert resp.status_code == 201
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert set(msg.to) == {
        "admin@topquaranta.cat",
        "staffa@example.com",
        "staffb@example.com",
    }
    assert "staffold@example.com" not in msg.to


@pytest.mark.django_db
def test_dm_to_regular_user_keeps_existing_behaviour(
    regular_user, another_user, staff_a
):
    """A DM addressed to a non-admin user goes to that user only.
    Staff are not BCC'd, the previous contract is intact."""
    client = APIClient()
    client.force_authenticate(regular_user)
    resp = client.post(
        MISSATGE_CREAR_URL,
        {
            "destinatari_pk": another_user.pk,
            "cos": "Hola Bob.",
            "assumpte": "Hi",
        },
        format="json",
    )
    assert resp.status_code == 201
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["bob@example.com"]


@pytest.mark.django_db
def test_staff_reply_keeps_staff_as_sender(regular_user, admin_inbox, staff_a):
    """When staff responds, the Missatge.remitent is the staff user
    themselves, NOT the admin pseudo-user. The user sees who actually
    replied (preserves accountability)."""
    # Step 1: user → admin (one Missatge created).
    client = APIClient()
    client.force_authenticate(regular_user)
    client.post(
        MISSATGE_CREAR_URL,
        {
            "destinatari_pk": admin_inbox.pk,
            "cos": "Hola",
        },
        format="json",
    )
    # Step 2: staff_a replies → regular_user.
    client.force_authenticate(staff_a)
    resp = client.post(
        MISSATGE_CREAR_URL,
        {
            "destinatari_pk": regular_user.pk,
            "cos": "Hola, soc del staff. Ja t'ho mirem.",
        },
        format="json",
    )
    assert resp.status_code == 201
    reply = Missatge.objects.filter(destinatari=regular_user).order_by("-pk").first()
    assert reply.remitent_id == staff_a.pk
    assert reply.remitent_id != admin_inbox.pk


@pytest.mark.django_db
def test_dm_to_admin_with_no_active_staff_still_hits_admin_mailbox(
    regular_user, admin_inbox
):
    """No staff configured → fan-out is just the admin mailbox.
    Doesn't crash; still delivers."""
    client = APIClient()
    client.force_authenticate(regular_user)
    resp = client.post(
        MISSATGE_CREAR_URL,
        {"destinatari_pk": admin_inbox.pk, "cos": "Sol contacte"},
        format="json",
    )
    assert resp.status_code == 201
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["admin@topquaranta.cat"]
