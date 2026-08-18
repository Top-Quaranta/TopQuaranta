"""The staff panel's destructive writes on user accounts.

`web/api/staff/usuaris.py` holds the most damaging buttons in the
project — hard-delete an account, deactivate it, wipe its 2FA devices —
and a 2026-08-15 audit found **not one test** on any of them. Each has
guards written into it (no deleting other staff, no deactivating
yourself) that nothing was checking, and every one of them writes a
`StaffAuditLog` row that is the only record of who did what.
"""

from __future__ import annotations

import pytest
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient

from comptes.models import Usuari
from music.models import StaffAuditLog


@pytest.fixture
def staff(db):
    return Usuari.objects.create_user(
        username="jefa", email="jefa@example.com", password="x", is_staff=True
    )


@pytest.fixture
def client(staff):
    c = APIClient()
    c.force_authenticate(user=staff)
    return c


@pytest.fixture
def victima(db):
    return Usuari.objects.create_user(
        username="normal", email="normal@example.com", password="x"
    )


def _url(pk, accio):
    return f"/api/v1/staff/usuaris/{pk}/{accio}/"


# ── esborrar ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_deleting_a_user_removes_it_and_leaves_an_audit_trail(client, victima):
    """The row is gone forever, so the log line is the only evidence the
    action ever happened — and it has to survive the target it names."""
    pk = victima.pk
    r = client.post(_url(pk, "esborrar"))
    assert r.status_code == 200, r.content
    assert not Usuari.objects.filter(pk=pk).exists()

    log = StaffAuditLog.objects.filter(action="usuari_esborrar").latest("id")
    assert log.metadata.get("email") == "normal@example.com"
    assert log.metadata.get("target_id_deleted") == pk


@pytest.mark.django_db
def test_staff_cannot_delete_another_staff(client, db):
    company = Usuari.objects.create_user(
        username="company", email="c@example.com", password="x", is_staff=True
    )
    assert client.post(_url(company.pk, "esborrar")).status_code == 400
    assert Usuari.objects.filter(pk=company.pk).exists()


@pytest.mark.django_db
def test_staff_cannot_delete_themselves_from_the_panel(client, staff):
    """There is a separate account flow with an emailed confirmation; the
    panel button must not become a one-click way around it.

    Asserting the MESSAGE, not just the 400: the is_staff guard sits
    above this one and also answers 400, so a status-only assertion
    passes even with the self-check deleted — it would be pinning the
    wrong guard (caught by mutation, 2026-08-15)."""
    r = client.post(_url(staff.pk, "esborrar"))
    assert r.status_code == 400
    assert "auto-esborrar" in str(r.json())
    assert Usuari.objects.filter(pk=staff.pk).exists()


# ── desactivar ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_toggling_active_flips_the_flag_both_ways(client, victima):
    assert client.post(_url(victima.pk, "toggle-actiu")).json()["is_active"] is False
    victima.refresh_from_db()
    assert victima.is_active is False
    assert client.post(_url(victima.pk, "toggle-actiu")).json()["is_active"] is True


@pytest.mark.django_db
def test_staff_cannot_lock_themselves_out(client, staff):
    """Same trap as the delete case: the is_staff guard below would also
    answer 400, so the message is what proves the self-check ran."""
    r = client.post(_url(staff.pk, "toggle-actiu"))
    assert r.status_code == 400
    assert "a tu mateix" in str(r.json())
    staff.refresh_from_db()
    assert staff.is_active is True


@pytest.mark.django_db
def test_staff_cannot_deactivate_another_staff(client, db):
    company = Usuari.objects.create_user(
        username="company2", email="c2@example.com", password="x", is_staff=True
    )
    assert client.post(_url(company.pk, "toggle-actiu")).status_code == 400
    company.refresh_from_db()
    assert company.is_active is True


# ── reset 2FA ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_resetting_2fa_removes_every_device(client, victima):
    """Both kinds: wiping only the TOTP would leave the backup codes
    working, which is the opposite of locking the account down."""
    TOTPDevice.objects.create(user=victima, name="tel", confirmed=True)
    StaticDevice.objects.create(user=victima, name="codis", confirmed=True)

    r = client.post(_url(victima.pk, "reset-2fa"))
    assert r.status_code == 200
    assert r.json()["totp_removed"] == 1 and r.json()["static_removed"] == 1
    assert not TOTPDevice.objects.filter(user=victima).exists()
    assert not StaticDevice.objects.filter(user=victima).exists()
    assert StaffAuditLog.objects.filter(action="usuari_reset_2fa").exists()


@pytest.mark.django_db
def test_resetting_2fa_on_a_user_without_devices_is_a_no_op(client, victima):
    r = client.post(_url(victima.pk, "reset-2fa"))
    assert r.status_code == 200 and r.json()["ok"] is True
    assert not StaffAuditLog.objects.filter(action="usuari_reset_2fa").exists()


# ── la porta ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_normal_user_cannot_reach_any_of_this(victima, db):
    """The guards above are all inside the view. The permission class is
    what stops the view from being reached at all."""
    altre = Usuari.objects.create_user(
        username="tafaner", email="t@example.com", password="x"
    )
    c = APIClient()
    c.force_authenticate(user=altre)
    for accio in ("esborrar", "toggle-actiu", "reset-2fa"):
        assert c.post(_url(victima.pk, accio)).status_code == 403, accio
    assert Usuari.objects.filter(pk=victima.pk).exists()
