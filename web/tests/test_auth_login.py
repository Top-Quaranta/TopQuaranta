"""Login, logout and the brute-force defences around them.

A 2026-08-15 audit found the whole login path untested: `login_view`,
`logout_view`, the `auth_login` 5/min throttle and the django-axes
lockout — the two security controls added in the May-2026 audit — had no
test in the repository. Registration was well covered; the door itself
was not.

About the throttle tests: DRF keeps its per-IP history in the `default`
cache, which this project points at a **database table** (`django_cache`).
That table is created by `createcachetable`, not by a migration, so it is
absent from the test database and every cache write there is a silent
no-op — which is why a throttle test written the obvious way sees seven
attempts sail through. It exists and works in production (table present,
272 live entries when checked on 2026-08-15); it is only untestable
against the default cache. So these tests give the throttle a real
in-memory cache of its own.
"""

from __future__ import annotations

import pytest
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

LOGIN = "/api/v1/auth/login/"
LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/auth/me/"

PASS = "una-contrasenya-prou-llarga-9"


@pytest.fixture(autouse=True)
def _throttle_cache(monkeypatch):
    """A private in-memory cache per test: real throttling, no bleed."""
    monkeypatch.setattr(
        SimpleRateThrottle, "cache", LocMemCache(f"throttle-{id(monkeypatch)}", {})
    )


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(
        username="login_tester",
        email="Login.Tester@Example.com",  # deliberately mixed case
        password=PASS,
        is_active=True,
    )


def _post(client, email, password, ip="10.0.0.1"):
    return client.post(
        LOGIN, {"email": email, "password": password}, format="json", REMOTE_ADDR=ip
    )


@pytest.mark.django_db
def test_login_succeeds_and_opens_a_session(user):
    c = APIClient()
    r = _post(c, "login.tester@example.com", PASS)
    assert r.status_code == 200, r.content

    # The session is real: /me/ now answers as this user, not anonymous.
    me = c.get(ME)
    assert me.status_code == 200
    assert me.json().get("email", "").lower() == "login.tester@example.com"


@pytest.mark.django_db
def test_email_lookup_is_case_insensitive(user):
    """Stored mixed-case, typed lowercase. `Usuari.USERNAME_FIELD` is
    `username`, so login goes through an `email__iexact` lookup — an
    exact-match regression would lock out anyone who signed up with a
    capital letter."""
    assert _post(APIClient(), "LOGIN.TESTER@EXAMPLE.COM", PASS).status_code == 200


@pytest.mark.django_db
def test_a_wrong_password_is_401_and_opens_no_session(user):
    c = APIClient()
    assert _post(c, "login.tester@example.com", "el-que-no-toca").status_code == 401
    assert c.get(ME).json().get("email") in (None, "")


@pytest.mark.django_db
def test_an_unknown_email_is_401_not_404(user):
    """Same shape and status as a wrong password: answering differently
    turns the endpoint into an account-enumeration oracle."""
    dolent = _post(APIClient(), "no.existeix@example.com", PASS)
    assert dolent.status_code == 401
    assert (
        dolent.json()
        == _post(APIClient(), "login.tester@example.com", "malament").json()
    )


@pytest.mark.django_db
def test_missing_credentials_are_refused(user):
    assert _post(APIClient(), "", "").status_code == 400
    assert _post(APIClient(), "login.tester@example.com", "").status_code == 400


@pytest.mark.django_db
def test_logout_closes_the_session(user):
    c = APIClient()
    assert _post(c, "login.tester@example.com", PASS).status_code == 200
    assert c.post(LOGOUT, {}, format="json").status_code == 200
    assert c.get(ME).json().get("email") in (None, "")


@pytest.mark.django_db
def test_the_throttle_stops_credential_guessing(user):
    """`auth_login` is 5/min per IP. It exists because axes only counts
    failures per account: without it, an attacker spraying ONE password
    across many accounts from one IP never trips anything."""
    c = APIClient()
    codis = [
        _post(c, f"victima{i}@example.com", "endevina", ip="10.0.0.99").status_code
        for i in range(7)
    ]
    assert 429 in codis, codis
    # …and it stops the guessing, not just the counting: the burst must
    # be cut before all seven attempts are evaluated.
    assert codis.index(429) <= 5, codis


@pytest.mark.django_db
def test_the_throttle_does_not_lock_a_different_ip(user):
    """Per-IP: one abuser must not lock the rest of the world out."""
    c = APIClient()
    for i in range(7):
        _post(c, f"victima{i}@example.com", "endevina", ip="10.0.0.98")

    assert (
        _post(APIClient(), "login.tester@example.com", PASS, ip="10.0.0.97").status_code
        == 200
    )
