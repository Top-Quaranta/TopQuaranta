"""Smoke tests for the central transactional-email layer.

Verifies each of the six `notify_*` functions builds an
EmailMultiAlternatives with the expected subject + recipient set.
Content is intentionally NOT asserted — that comes with the Fase 1.5.C
walkthrough rewrite.
"""

from __future__ import annotations

import pytest
from django.core import mail

from comptes import notifications
from comptes.models import Feedback, PropostaArtista, UserArtista, Usuari
from music.models import Artista


@pytest.fixture
def staff_user(db):
    return Usuari.objects.create_user(
        username="staff1",
        email="staff1@topquaranta.cat",
        password="x",
        is_staff=True,
        is_active=True,
    )


@pytest.fixture
def regular_user(db):
    return Usuari.objects.create_user(
        username="user1",
        email="user1@example.com",
        password="x",
        is_staff=False,
        is_active=True,
    )


@pytest.fixture
def artista(db):
    return Artista.objects.create(nom="Test Artist", slug="test-artist", aprovat=True)


@pytest.fixture
def user_artista(db, regular_user, artista):
    return UserArtista.objects.create(
        usuari=regular_user,
        artista=artista,
        sollicitud_text="Soc el manager.",
        estat=UserArtista.ESTAT_PENDENT,
    )


@pytest.fixture
def proposta(db, regular_user):
    return PropostaArtista.objects.create(
        usuari=regular_user,
        nom="Nou Artista",
        justificacio="Fan música en català.",
    )


@pytest.fixture
def feedback(db, regular_user):
    return Feedback.objects.create(
        usuari=regular_user,
        url="https://www.topquaranta.cat/artista/foo",
        target_type=Feedback.TARGET_ARTISTA,
        target_label="Foo",
        missatge="Falta una cançó.",
    )


# ── Admin-side notifications ────────────────────────────────────────


@pytest.mark.django_db
def test_notify_admins_nova_solicitud(staff_user, user_artista):
    notifications.notify_admins_nova_solicitud_gestio(user_artista)
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "nova sol·licitud de gestió" in msg.subject.lower()
    assert "Test Artist" in msg.subject
    assert msg.to == [staff_user.email]


@pytest.mark.django_db
def test_notify_admins_nova_proposta(staff_user, proposta):
    notifications.notify_admins_nova_proposta(proposta)
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "nova proposta" in msg.subject.lower()
    assert "Nou Artista" in msg.subject
    assert msg.to == [staff_user.email]


@pytest.mark.django_db
def test_notify_admins_nou_feedback(staff_user, feedback):
    notifications.notify_admins_nou_feedback(feedback)
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "nou feedback" in msg.subject.lower()
    assert msg.to == [staff_user.email]


# ── User-side notifications ─────────────────────────────────────────


@pytest.mark.django_db
def test_notify_user_solicitud_aprovada(user_artista):
    notifications.notify_user_solicitud_resolta(user_artista, "aprovada")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "verificada" in msg.subject.lower()
    assert "Test Artist" in msg.subject
    assert msg.to == [user_artista.usuari.email]


@pytest.mark.django_db
def test_notify_user_solicitud_rebutjada(user_artista):
    user_artista.motiu_rebuig = "Cal més context."
    notifications.notify_user_solicitud_resolta(user_artista, "rebutjada")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "no acceptada" in msg.subject.lower()
    assert msg.to == [user_artista.usuari.email]


@pytest.mark.django_db
def test_notify_user_proposta_resolta_aprovada(proposta):
    notifications.notify_user_proposta_resolta(proposta, "aprovada")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "acceptada" in msg.subject.lower()
    assert msg.to == [proposta.usuari.email]


@pytest.mark.django_db
def test_notify_user_feedback_resolt(feedback):
    notifications.notify_user_feedback_resolt(feedback)
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "feedback resolt" in msg.subject.lower()
    assert msg.to == [feedback.usuari.email]


@pytest.mark.django_db
def test_notify_user_solicitud_rejects_invalid_accio(user_artista):
    with pytest.raises(ValueError):
        notifications.notify_user_solicitud_resolta(user_artista, "noseque")
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_admin_notify_skips_when_no_staff(regular_user, user_artista):
    """No staff with email → no recipients → no send (but no crash)."""
    # The `staff_user` fixture is not requested; only the regular user
    # exists, so `_staff_emails()` is empty.
    notifications.notify_admins_nova_solicitud_gestio(user_artista)
    assert mail.outbox == []
