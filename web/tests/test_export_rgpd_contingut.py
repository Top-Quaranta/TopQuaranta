"""What the RGPD export actually contains.

The existing test asserts the mail has an attachment ending in `.json`
and stops there (`test_legal_endpoints.py:115`). So the *contents* — the
thing the regulation is about, and the thing a user asks for when they
want to know what we hold — was unverified. CLAUDE.md records that the
export must carry the `StaffAuditLog` rows targeting the user and their
axes login history; nothing checked either.

The failure mode is quiet: `rgpd.py` swallows an axes `ImportError` and
emits `[]`, so an export could ship with an empty login history and a
green suite. That is a bad answer to a legal request — it looks like
"we hold nothing" rather than "we failed to look".
"""

from __future__ import annotations

import json

import pytest
from django.core import mail
from rest_framework.test import APIClient

from comptes.models import Usuari
from music.models import StaffAuditLog

URL = "/api/v1/compte/exportar-dades/"


@pytest.fixture
def user(db):
    return Usuari.objects.create_user(
        username="exportador", email="jo@example.com", password="x"
    )


def _export(user):
    c = APIClient()
    c.force_authenticate(user=user)
    r = c.post(URL)
    assert r.status_code == 200, r.content
    assert len(mail.outbox) == 1
    nom, contingut, _ = mail.outbox[0].attachments[0]
    assert nom.endswith(".json")
    return json.loads(contingut)


@pytest.mark.django_db
def test_the_export_carries_the_account_itself(user):
    dades = _export(user)
    assert dades["usuari"]["email"] == "jo@example.com"


@pytest.mark.django_db
def test_the_export_carries_staff_decisions_about_the_user(user):
    """A person has the right to know what was decided about them and by
    whom — this is the block that answers "why was I rejected"."""
    admin = Usuari.objects.create_user(
        username="admin_test", email="a@example.com", password="x", is_staff=True
    )
    StaffAuditLog.objects.create(
        actor=admin,
        action="usuari_desactivar",
        target_type="usuari",
        target_id=user.pk,
        target_label=str(user),
        metadata={},
    )

    dades = _export(user)
    entrades = dades["audit_log_sobre_meu"]
    assert len(entrades) == 1
    assert entrades[0]["action"] == "usuari_desactivar"
    assert entrades[0]["actor_username"] == "admin_test"


@pytest.mark.django_db
def test_the_export_does_not_leak_decisions_about_other_people(user):
    """Same block, opposite risk: an off-by-one on the filter would hand
    one user somebody else's moderation history."""
    altre = Usuari.objects.create_user(
        username="altre", email="altre@example.com", password="x"
    )
    StaffAuditLog.objects.create(
        actor=None,
        action="usuari_desactivar",
        target_type="usuari",
        target_id=altre.pk,
        target_label=str(altre),
        metadata={},
    )

    assert _export(user)["audit_log_sobre_meu"] == []


@pytest.mark.django_db
def test_the_login_history_block_is_always_present(user):
    """Present even when empty. Its absence would silently turn a legal
    answer into a different one."""
    dades = _export(user)
    assert "login_history" in dades
    assert isinstance(dades["login_history"], list)
