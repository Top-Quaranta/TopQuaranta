"""Sprint J — RGPD endpoint coverage.

Confirms registration consent gates are enforced + the data export
+ newsletter unsubscribe token round-trip.
"""

from datetime import timedelta

import pytest
from django.core import mail, signing
from django.utils import timezone
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _outbox_locmem(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    yield
    mail.outbox = []


@pytest.fixture
def anon():
    return APIClient()


# ── Registration consent gating ────────────────────────────────────────


def test_register_requires_terms_acceptance(db, anon):
    r = anon.post(
        "/api/v1/auth/register/",
        {
            "email": "x@example.com",
            "password1": "Wa3ldaP9!q",
            "password2": "Wa3ldaP9!q",
            "edat_min": True,
        },
        format="json",
    )
    assert r.status_code == 400
    assert "accepta_termes" in r.json()["errors"]


def test_register_requires_age_confirmation(db, anon):
    r = anon.post(
        "/api/v1/auth/register/",
        {
            "email": "y@example.com",
            "password1": "Wa3ldaP9!q",
            "password2": "Wa3ldaP9!q",
            "accepta_termes": True,
        },
        format="json",
    )
    assert r.status_code == 400
    assert "edat_min" in r.json()["errors"]


def test_register_records_consent(db, anon, django_user_model):
    r = anon.post(
        "/api/v1/auth/register/",
        {
            "email": "z@example.com",
            "password1": "Wa3ldaP9!q",
            "password2": "Wa3ldaP9!q",
            "accepta_termes": True,
            "edat_min": True,
            "vol_newsletter": True,
        },
        format="json",
    )
    assert r.status_code == 201
    u = django_user_model.objects.get(email="z@example.com")
    perfil = u.perfil
    assert perfil.consent_termes_at is not None
    assert perfil.consent_termes_versio == "2026-04-26"
    assert perfil.vol_newsletter is True
    assert perfil.consent_newsletter_at is not None


def test_register_newsletter_default_off(db, anon, django_user_model):
    r = anon.post(
        "/api/v1/auth/register/",
        {
            "email": "w@example.com",
            "password1": "Wa3ldaP9!q",
            "password2": "Wa3ldaP9!q",
            "accepta_termes": True,
            "edat_min": True,
        },
        format="json",
    )
    assert r.status_code == 201
    u = django_user_model.objects.get(email="w@example.com")
    assert u.perfil.vol_newsletter is False
    assert u.perfil.consent_newsletter_at is None


# ── Data export ────────────────────────────────────────────────────────


def test_exportar_dades_emails_user(db, django_user_model):
    u = django_user_model.objects.create_user(
        username="exp", email="exp@example.com", password="x"
    )
    c = APIClient()
    c.force_authenticate(user=u)
    r = c.post("/api/v1/compte/exportar-dades/")
    assert r.status_code == 200
    assert r.json()["email"] == "exp@example.com"
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "exp@example.com" in msg.to
    # Attachment present?
    assert any(name.endswith(".json") for name, _, _ in msg.attachments)


def test_exportar_dades_requires_auth(db, anon):
    r = anon.post("/api/v1/compte/exportar-dades/")
    assert r.status_code in (401, 403)


# ── Newsletter unsubscribe via token ──────────────────────────────────


def test_baixa_newsletter_with_valid_token(db, django_user_model):
    u = django_user_model.objects.create_user(
        username="nl", email="nl@example.com", password="x"
    )
    perfil = u.perfil
    perfil.vol_newsletter = True
    perfil.consent_newsletter_at = timezone.now()
    perfil.save()
    token = signing.dumps({"u": u.pk}, salt="newsletter-baixa")

    c = APIClient()
    r = c.get(f"/api/v1/compte/baixa-newsletter/?token={token}")
    assert r.status_code == 200
    perfil.refresh_from_db()
    assert perfil.vol_newsletter is False


def test_baixa_newsletter_rejects_garbage_token(db):
    c = APIClient()
    r = c.get("/api/v1/compte/baixa-newsletter/?token=not-a-real-token")
    assert r.status_code == 400


def test_baixa_newsletter_rejects_token_for_other_salt(db, django_user_model):
    u = django_user_model.objects.create_user(
        username="nl2", email="nl2@example.com", password="x"
    )
    # Token signed with the wrong salt is invalid even if the payload looks right.
    bad = signing.dumps({"u": u.pk}, salt="some-other-salt")
    c = APIClient()
    r = c.get(f"/api/v1/compte/baixa-newsletter/?token={bad}")
    assert r.status_code == 400
