"""Who the newsletter actually goes to.

Registration sets `vol_newsletter=True` at once, while the account is
still `is_active=False` pending email confirmation. The recipient query
filtered only on `vol_newsletter`, so an unconfirmed address received
mail — meaning anyone could sign a third party up for it, and the Brevo
free tier (300/day) would be spent on addresses nobody agreed to.

The staff dashboard's subscriber count already filtered `is_active`, so
the number shown and the list actually mailed disagreed (audit
2026-08-15; one recipient at the time, none unconfirmed).
"""

from __future__ import annotations

import pytest

from comptes.models import Usuari


def _amb_newsletter(username, *, actiu):
    u = Usuari.objects.create_user(
        username=username, email=f"{username}@example.com", password="x"
    )
    u.is_active = actiu
    u.save(update_fields=["is_active"])
    perfil = u.perfil
    perfil.vol_newsletter = True
    perfil.save(update_fields=["vol_newsletter"])
    return u


def _destinataris():
    """The production definition itself — never a copy of it. A test that
    rebuilds the query only proves Django can filter."""
    from comptes.newsletter import destinataris

    return set(destinataris().values_list("username", flat=True))


@pytest.mark.django_db
def test_an_unconfirmed_address_is_not_mailed():
    _amb_newsletter("confirmat", actiu=True)
    _amb_newsletter("sense_confirmar", actiu=False)
    assert _destinataris() == {"confirmat"}


@pytest.mark.django_db
def test_the_dashboard_count_matches_the_send_list():
    """They disagreed before: the panel filtered `is_active`, the send
    did not. A subscriber count you can't trust is worse than none."""
    from comptes.models import PerfilUsuari as P

    _amb_newsletter("a", actiu=True)
    _amb_newsletter("b", actiu=True)
    _amb_newsletter("c", actiu=False)

    panell = P.objects.filter(vol_newsletter=True, usuari__is_active=True).count()
    assert panell == len(_destinataris()) == 2
