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
#
# Property asserted throughout (not subject copy): the RECIPIENT SET is
# the promise — admin mails go to every active staff address and to
# nobody else (a second staff user is added, an inactive staff and a
# non-staff user are decoys); user mails go to the submitter only. Each
# mail must name the entity it is about somewhere (subject or body).


@pytest.fixture
def staff_user_2(db):
    return Usuari.objects.create_user(
        username="staff2", email="staff2@topquaranta.cat", password="x", is_staff=True
    )


@pytest.fixture
def decoys(db):
    Usuari.objects.create_user(
        username="staff_off",
        email="staff-off@topquaranta.cat",
        password="x",
        is_staff=True,
        is_active=False,
    )
    Usuari.objects.create_user(
        username="plain", email="plain@example.com", password="x", is_staff=False
    )


def _html(msg):
    return msg.alternatives[0][0] if msg.alternatives else ""


def _mentions(msg, needle):
    return needle in msg.subject or needle in _html(msg)


def _staff_set(*users):
    return {u.email for u in users}


@pytest.mark.django_db
def test_notify_admins_nova_solicitud(staff_user, staff_user_2, decoys, user_artista):
    notifications.notify_admins_nova_solicitud_gestio(user_artista)
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert set(msg.to) == _staff_set(staff_user, staff_user_2)
    assert _mentions(msg, user_artista.artista.nom)
    assert user_artista.usuari.email in _html(msg)  # staff can see who asked


@pytest.mark.django_db
def test_notify_admins_nova_proposta(staff_user, staff_user_2, decoys, proposta):
    notifications.notify_admins_nova_proposta(proposta)
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert set(msg.to) == _staff_set(staff_user, staff_user_2)
    assert _mentions(msg, proposta.nom)
    assert proposta.usuari.email in _html(msg)


@pytest.mark.django_db
def test_notify_admins_nou_feedback(staff_user, staff_user_2, decoys, feedback):
    notifications.notify_admins_nou_feedback(feedback)
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert set(msg.to) == _staff_set(staff_user, staff_user_2)
    assert _mentions(msg, feedback.target_label)
    assert feedback.missatge in _html(msg)


# ── User-side notifications ─────────────────────────────────────────


@pytest.mark.django_db
def test_notify_user_solicitud_aprovada(staff_user, user_artista):
    """Recipient = the submitter only (staff exists but is not copied);
    the mail names the artist and carries the gestió link, and the
    approval stamp is set."""
    notifications.notify_user_solicitud_resolta(user_artista, "aprovada")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == [user_artista.usuari.email]
    assert _mentions(msg, user_artista.artista.nom)
    assert f"/compte/artista/{user_artista.artista.pk}/editar" in _html(msg)
    user_artista.refresh_from_db()
    assert user_artista.email_aprovacio_at is not None


@pytest.mark.django_db
def test_notify_user_solicitud_rebutjada(staff_user, user_artista):
    """Recipient = the submitter only; the rejection reason reaches
    them; the mail is the rejection one (no gestió link, no approval
    stamp) — distinguishes the two `accio` branches without copy pins."""
    user_artista.motiu_rebuig = "Cal més context QX."
    notifications.notify_user_solicitud_resolta(user_artista, "rebutjada")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == [user_artista.usuari.email]
    assert _mentions(msg, user_artista.artista.nom)
    assert "Cal més context QX." in _html(msg)
    assert f"/compte/artista/{user_artista.artista.pk}/editar" not in _html(msg)
    user_artista.refresh_from_db()
    assert user_artista.email_aprovacio_at is None


@pytest.mark.django_db
def test_notify_user_proposta_resolta_aprovada(staff_user, proposta):
    """Recipient = the proposer only; the mail names the proposed artist
    and differs from the rejection branch (aprovada offers the gestió
    request link, rebutjada does not)."""
    notifications.notify_user_proposta_resolta(proposta, "aprovada")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == [proposta.usuari.email]
    assert _mentions(msg, proposta.nom)
    assert "/compte/artista/gestio" in _html(msg)
    mail.outbox.clear()
    notifications.notify_user_proposta_resolta(proposta, "rebutjada")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [proposta.usuari.email]
    assert "/compte/artista/gestio" not in _html(mail.outbox[0])


@pytest.mark.django_db
def test_notify_user_feedback_resolt(staff_user, feedback):
    """Recipient = the reporter only; the mail names what was reported
    and relays the staff notes."""
    feedback.notes_staff = "Ja està afegida QX."
    notifications.notify_user_feedback_resolt(feedback)
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == [feedback.usuari.email]
    assert _mentions(msg, feedback.target_label)
    assert "Ja està afegida QX." in _html(msg)


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
