"""Staff endpoints for IG collaborator invitations (ADR-0015 §5.5).

Covers the registry list, the manual-acceptance action (the only
manual resolution — there is deliberately no manual reject), its
idempotency, the audit trail, and the IsStaff gate.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from music.models import Artista, StaffAuditLog
from social.models import InvitacioColaboracioIG as Inv


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="collab_tester",
        email="collab@example.com",
        password="x",
        is_staff=True,
    )
    # Defeat the django-otp gate (same pattern as test_staff_endpoints).
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _invite(nom, username, *, dies=1, estat=Inv.ESTAT_PENDENT):
    artista = Artista.objects.create(nom=nom, lastfm_nom=nom, aprovat=True)
    return Inv.objects.create(
        artista=artista,
        username_snapshot=username,
        ig_media_id="18000000000000001",
        tipus_publicacio="top_territorial",
        data_invitacio=timezone.now() - timedelta(days=dies),
        estat=estat,
    )


def test_invitacions_require_staff(db):
    anon = APIClient()
    assert anon.get("/api/v1/staff/social/invitacions/").status_code in (401, 403)
    assert anon.post(
        "/api/v1/staff/social/invitacions/acceptar/", {"id": 1}
    ).status_code in (401, 403)


@pytest.mark.django_db
def test_invitacions_list(staff_client):
    inv = _invite("EXEMPLE A", "handle_a", dies=2)
    _invite("EXEMPLE B", "handle_b", dies=1)
    res = staff_client.get("/api/v1/staff/social/invitacions/")
    assert res.status_code == 200
    rows = res.json()["invitacions"]
    assert len(rows) == 2
    # Newest first.
    assert rows[0]["username"] == "handle_b"
    r = rows[1]
    assert r["id"] == inv.id
    assert r["artista_nom"] == "EXEMPLE A"
    assert r["tipus"] == "top_territorial"
    assert r["estat"] == Inv.ESTAT_PENDENT
    assert r["data_resolucio"] is None


@pytest.mark.django_db
def test_marcar_acceptada(staff_client):
    inv = _invite("EXEMPLE A", "handle_a")
    res = staff_client.post(
        "/api/v1/staff/social/invitacions/acceptar/", {"id": inv.id}
    )
    assert res.status_code == 200
    assert res.json()["estat"] == Inv.ESTAT_ACCEPTADA
    inv.refresh_from_db()
    assert inv.estat == Inv.ESTAT_ACCEPTADA
    assert inv.data_resolucio is not None
    # Audit-logged with the previous estat.
    log = StaffAuditLog.objects.get(action="collab_invitacio_acceptada")
    assert log.metadata["username"] == "handle_a"
    assert log.metadata["anterior"] == Inv.ESTAT_PENDENT


@pytest.mark.django_db
def test_marcar_acceptada_idempotent(staff_client):
    inv = _invite("EXEMPLE A", "handle_a", estat=Inv.ESTAT_ACCEPTADA)
    inv.data_resolucio = timezone.now() - timedelta(days=1)
    inv.save(update_fields=["data_resolucio"])
    first = inv.data_resolucio
    res = staff_client.post(
        "/api/v1/staff/social/invitacions/acceptar/", {"id": inv.id}
    )
    assert res.status_code == 200
    inv.refresh_from_db()
    assert inv.data_resolucio == first  # unchanged, no re-stamp
    assert not StaffAuditLog.objects.filter(
        action="collab_invitacio_acceptada"
    ).exists()


@pytest.mark.django_db
def test_marcar_acceptada_from_caducada(staff_client):
    """Observed truth wins over the automatic expiry: a late-observed
    acceptance can still be recorded on a caducada row."""
    inv = _invite("EXEMPLE A", "handle_a", dies=20, estat=Inv.ESTAT_CADUCADA)
    res = staff_client.post(
        "/api/v1/staff/social/invitacions/acceptar/", {"id": inv.id}
    )
    assert res.status_code == 200
    inv.refresh_from_db()
    assert inv.estat == Inv.ESTAT_ACCEPTADA
    log = StaffAuditLog.objects.get(action="collab_invitacio_acceptada")
    assert log.metadata["anterior"] == Inv.ESTAT_CADUCADA


@pytest.mark.django_db
def test_marcar_acceptada_unknown_id(staff_client):
    res = staff_client.post("/api/v1/staff/social/invitacions/acceptar/", {"id": 99999})
    assert res.status_code == 404
