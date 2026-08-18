"""The 2FA challenge must not be free to guess.

`dos_fa_verificar` accepts a TOTP code **or** a single-use backup code,
and the `auth_2fa` rate configured in the May-2026 audit never applied to
it: that rate is a DRF throttle and this is a plain Django view. So the
one screen in the project that loops over backup codes was the one with
no limit on attempts (found 2026-08-15).

Identity is the user, not the IP: whoever reaches this screen has already
passed the password, so someone with a stolen session cookie is one user
however many IPs they rotate through.
"""

from __future__ import annotations

import uuid

import pytest
from django.core.cache.backends.locmem import LocMemCache
from django_otp.plugins.otp_totp.models import TOTPDevice

from comptes.models import Usuari

URL = "/compte/2fa/verificar/"


# `uuid4` i no `id(monkeypatch)`: CPython reutilitza els id dels objectes
# alliberats, i dues instàncies de LocMemCache amb el MATEIX nom
# comparteixen magatzem. Amb id() dues proves podien acabar compartint
# comptador — en local no passava i a CI sí, perquè l'ordre de les proves
# és aleatori (2026-08-19).
@pytest.fixture(autouse=True)
def _cache(monkeypatch):
    """The `default` cache is a PostgreSQL table created by
    `createcachetable`, not by a migration, so it is absent from the test
    DB and every write there is a silent no-op. Give the limiter a real
    cache or it cannot be tested at all."""
    monkeypatch.setattr(
        "comptes.ratelimit.cache", LocMemCache(f"rl-{uuid.uuid4()}", {})
    )


def _usuari(client, username="amb2fa"):
    u = Usuari.objects.create_user(
        username=username, email=f"{username}@example.com", password="x"
    )
    TOTPDevice.objects.create(user=u, name="tel", confirmed=True)
    client.force_login(u)
    return u


@pytest.mark.django_db
def test_guessing_is_cut_off_after_the_configured_number_of_tries(client):
    _usuari(client)
    codis = [client.post(URL, {"token": f"00000{i}"}).status_code for i in range(12)]
    assert 429 in codis, codis
    # 10/min: the eleventh is the first refusal.
    assert codis.index(429) == 10, codis


@pytest.mark.django_db
def test_the_limit_is_per_user_not_global(client, django_user_model):
    """One person burning their attempts must not lock everybody else out
    of their own account."""
    _usuari(client, "primer")
    for i in range(12):
        client.post(URL, {"token": f"00000{i}"})

    from django.test import Client

    altre = Client()
    _usuari(altre, "segon")
    assert altre.post(URL, {"token": "123456"}).status_code == 200


@pytest.mark.django_db
def test_looking_at_the_page_does_not_burn_attempts(client):
    """Only POSTs count. Otherwise a reload or a back button would spend
    somebody's budget without them typing anything."""
    _usuari(client)
    for _ in range(20):
        assert client.get(URL).status_code == 200
    assert client.post(URL, {"token": "000000"}).status_code == 200


@pytest.mark.django_db
def test_a_broken_cache_does_not_lock_people_out(client, monkeypatch):
    """Fail open, deliberately: the password is still required to reach
    this screen, so a cache outage must not become an account lockout."""

    class _Trencat:
        def add(self, *a, **k):
            raise RuntimeError("cache mort")

        def incr(self, *a, **k):
            raise RuntimeError("cache mort")

        def set(self, *a, **k):
            raise RuntimeError("cache mort")

    monkeypatch.setattr("comptes.ratelimit.cache", _Trencat())
    _usuari(client)
    for i in range(15):
        assert client.post(URL, {"token": f"00000{i}"}).status_code == 200
