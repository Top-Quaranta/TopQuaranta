"""Retroactive gestor-notification command.

Covers: idempotency, --dry-run no-op, --exclude-user-id, the
email_aprovacio_at stamp gating subsequent re-runs.
"""

from __future__ import annotations

import datetime

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from comptes.models import UserArtista, Usuari
from music.models import Artista


@pytest.fixture
def usuari_a(db):
    return Usuari.objects.create_user(
        username="userA", email="a@example.com", password="x", is_active=True
    )


@pytest.fixture
def usuari_b(db):
    return Usuari.objects.create_user(
        username="userB", email="b@example.com", password="x", is_active=True
    )


@pytest.fixture
def artista_a(db):
    return Artista.objects.create(nom="Artista A", slug="artista-a", aprovat=True)


@pytest.fixture
def artista_b(db):
    return Artista.objects.create(nom="Artista B", slug="artista-b", aprovat=True)


@pytest.fixture
def approved_ua_unnotified(db, usuari_a, artista_a):
    """Verified manager without an email_aprovacio_at stamp — exactly
    the population the command targets."""
    return UserArtista.objects.create(
        usuari=usuari_a,
        artista=artista_a,
        verificat=True,
        estat=UserArtista.ESTAT_APROVAT,
        sollicitud_text="Sóc l'artista",
        email_aprovacio_at=None,
    )


@pytest.fixture
def approved_ua_already_notified(db, usuari_b, artista_b):
    """Verified manager who's already received the email."""
    return UserArtista.objects.create(
        usuari=usuari_b,
        artista=artista_b,
        verificat=True,
        estat=UserArtista.ESTAT_APROVAT,
        email_aprovacio_at=timezone.now() - datetime.timedelta(days=2),
    )


@pytest.mark.django_db
def test_dry_run_sends_no_email(approved_ua_unnotified):
    call_command("notificar_gestors_retroactiu", "--dry-run")
    assert mail.outbox == []
    approved_ua_unnotified.refresh_from_db()
    assert approved_ua_unnotified.email_aprovacio_at is None


@pytest.mark.django_db
def test_real_run_sends_and_stamps(approved_ua_unnotified):
    call_command("notificar_gestors_retroactiu")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [approved_ua_unnotified.usuari.email]
    approved_ua_unnotified.refresh_from_db()
    assert approved_ua_unnotified.email_aprovacio_at is not None


@pytest.mark.django_db
def test_already_notified_user_is_skipped(approved_ua_already_notified):
    call_command("notificar_gestors_retroactiu")
    assert mail.outbox == []


@pytest.mark.django_db
def test_exclude_user_id_skips_target(approved_ua_unnotified):
    call_command(
        "notificar_gestors_retroactiu",
        "--exclude-user-id",
        str(approved_ua_unnotified.usuari_id),
    )
    assert mail.outbox == []
    approved_ua_unnotified.refresh_from_db()
    assert approved_ua_unnotified.email_aprovacio_at is None


@pytest.mark.django_db
def test_user_without_email_is_skipped(db, artista_a):
    usuari = Usuari.objects.create_user(
        username="noemail", email="", password="x", is_active=True
    )
    UserArtista.objects.create(
        usuari=usuari,
        artista=artista_a,
        verificat=True,
        estat=UserArtista.ESTAT_APROVAT,
    )
    call_command("notificar_gestors_retroactiu")
    assert mail.outbox == []


@pytest.mark.django_db
def test_template_renders_with_real_data(approved_ua_unnotified):
    """End-to-end: the email_user_solicitud_aprovada.html template
    must render without raising. Covers the FAQ + walkthrough copy
    against real artista data."""
    call_command("notificar_gestors_retroactiu")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "verificada" in msg.subject.lower()
    # HTML alternative must mention the artist and the FAQ keywords.
    html = msg.alternatives[0][0]
    assert approved_ua_unnotified.artista.nom in html
    assert "365 dies" in html  # FAQ #1
    assert "Deezer" in html  # FAQ #2
