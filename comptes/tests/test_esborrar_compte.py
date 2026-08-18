"""Self-deletion of an account: irreversible, and it was untested.

`comptes.views.esborrar_compte` does a hard `user.delete()`. The only
things between a stranger and someone else's account are a signed token
and an `is_staff` refusal, and a 2026-08-15 audit found neither exercised
anywhere. There is nothing to undo a mistake here — no soft delete, no
grace period — so this is the one flow whose guards must be pinned.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from comptes.models import Usuari


def _url(user, token=None):
    return reverse(
        "comptes:esborrar_compte",
        args=[
            urlsafe_base64_encode(force_bytes(user.pk)),
            token or default_token_generator.make_token(user),
        ],
    )


@pytest.fixture
def user(db):
    return Usuari.objects.create_user(
        username="a_esborrar", email="fora@example.com", password="x"
    )


@pytest.mark.django_db
def test_a_valid_token_deletes_the_account(client, user):
    pk = user.pk
    r = client.post(_url(user))
    assert r.status_code == 200
    assert not Usuari.objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_get_only_confirms_and_deletes_nothing(client, user):
    """The confirmation page must be safe to open: a link preview, an
    antivirus fetching URLs or a mail client prefetching would otherwise
    wipe the account before the person read the page."""
    r = client.get(_url(user))
    assert r.status_code == 200
    assert Usuari.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_a_forged_token_deletes_nothing(client, user):
    r = client.post(_url(user, token="no-es-un-token-valid"))
    assert r.status_code == 400
    assert Usuari.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_someone_elses_token_does_not_delete_you(client, user):
    """The uid and the token must belong to the same person: the token
    generator is keyed on the user, so pairing A's uid with B's token
    must fail rather than delete A."""
    altre = Usuari.objects.create_user(
        username="altre", email="altre@example.com", password="x"
    )
    url = reverse(
        "comptes:esborrar_compte",
        args=[
            urlsafe_base64_encode(force_bytes(user.pk)),
            default_token_generator.make_token(altre),
        ],
    )
    assert client.post(url).status_code == 400
    assert Usuari.objects.filter(pk=user.pk).exists()
    assert Usuari.objects.filter(pk=altre.pk).exists()


@pytest.mark.django_db
def test_a_staff_account_is_refused_even_with_a_valid_token(client, db):
    """Belt and braces in the view, and worth pinning: staff own the
    catalogue, the social credentials and everyone else's data."""
    staff = Usuari.objects.create_user(
        username="jefa", email="jefa@example.com", password="x", is_staff=True
    )
    assert client.post(_url(staff)).status_code == 400
    assert Usuari.objects.filter(pk=staff.pk).exists()


@pytest.mark.django_db
def test_the_token_is_single_use(client, user):
    """`default_token_generator` keys on the password hash and
    `last_login`, so a link that already deleted the account cannot be
    replayed against a re-registered one with the same pk."""
    url = _url(user)
    assert client.post(url).status_code == 200
    # Same pk, new account: the old link must not touch it.
    nou = Usuari.objects.create_user(
        username="reregistrat", email="fora@example.com", password="y"
    )
    client.post(url)
    assert Usuari.objects.filter(pk=nou.pk).exists()
