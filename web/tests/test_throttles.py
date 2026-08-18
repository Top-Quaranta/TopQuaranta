"""The rate limits must actually limit.

All six were declared as `rest_framework.throttling.ScopedRateThrottle`
subclasses setting `scope = "..."`. That class reads the scope from the
**view** (`view.throttle_scope`) and returns True — allow — when it is
missing, overwriting the class attribute on every call. No view in this
project ever set `throttle_scope`, so from the day they were added (the
May-2026 audit) until 2026-08-15, every one of them was inert: wired up,
invoked on each request, limiting nothing.

The bug was invisible from the outside — the throttle appears in
`throttle_classes`, the settings list the rates, and nothing errors. It
took counting responses to see it.
"""

from __future__ import annotations

import uuid

import pytest
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from web.api.utils import ScopedThrottle


# `uuid4` i no `id(monkeypatch)`: CPython reutilitza els id dels objectes
# alliberats, i dues instàncies de LocMemCache amb el MATEIX nom
# comparteixen magatzem. Amb id() dues proves podien acabar compartint
# comptador — en local no passava i a CI sí, perquè l'ordre de les proves
# és aleatori (2026-08-19).
@pytest.fixture(autouse=True)
def _throttle_cache(monkeypatch):
    """DRF keeps throttle history in the `default` cache, which this
    project points at a database table created by `createcachetable`, not
    by a migration — so it is absent from the test DB and every write is
    a silent no-op. Give the throttles a real cache of their own."""
    monkeypatch.setattr(
        SimpleRateThrottle, "cache", LocMemCache(f"throttle-{uuid.uuid4()}", {})
    )


def test_no_throttle_relies_on_a_view_attribute_nobody_sets():
    """The guard for the whole class of bug: any throttle inheriting
    DRF's ScopedRateThrottle needs `throttle_scope` ON THE VIEW, which
    we never set. Ours must inherit `ScopedThrottle` instead."""
    from rest_framework.throttling import ScopedRateThrottle

    from web.api import auth_views
    from web.api.compte_views import _common

    sospitosos = []
    for mod in (auth_views, _common):
        for nom in dir(mod):
            obj = getattr(mod, nom)
            if (
                isinstance(obj, type)
                and issubclass(obj, ScopedRateThrottle)
                and obj is not ScopedRateThrottle
            ):
                sospitosos.append(f"{mod.__name__}.{nom}")
    assert not sospitosos, (
        "Aquests limitadors llegeixen view.throttle_scope, que no definim "
        f"enlloc, i per tant deixen passar tot: {sospitosos}. "
        "Han d'heretar web.api.utils.ScopedThrottle."
    )


def test_every_throttle_declares_a_scope_with_a_configured_rate(settings):
    """A scope with no rate in settings is the same silence by another
    route: `get_rate()` would raise or the limit would be unbounded."""
    from web.api import auth_views
    from web.api.compte_views import _common

    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    trobats = 0
    for mod in (auth_views, _common):
        for nom in dir(mod):
            obj = getattr(mod, nom)
            if (
                isinstance(obj, type)
                and issubclass(obj, ScopedThrottle)
                and obj is not ScopedThrottle
            ):
                trobats += 1
                assert obj.scope, f"{nom} sense scope"
                assert obj.scope in rates, f"{nom}: scope '{obj.scope}' sense rate"
    assert trobats >= 6, trobats


@pytest.mark.django_db
def test_the_login_throttle_stops_credential_guessing(django_user_model):
    """`auth_login` is 5/min per IP. It exists because django-axes counts
    failures per ACCOUNT: without it, someone spraying one password
    across many accounts from one IP trips nothing."""
    django_user_model.objects.create_user(
        username="t", email="t@example.com", password="x", is_active=True
    )
    c = APIClient()
    codis = [
        c.post(
            "/api/v1/auth/login/",
            {"email": f"victima{i}@example.com", "password": "endevina"},
            format="json",
            REMOTE_ADDR="10.0.0.99",
        ).status_code
        for i in range(7)
    ]
    assert 429 in codis, codis
    assert codis.index(429) <= 5, codis


@pytest.mark.django_db
def test_the_login_throttle_is_per_ip(django_user_model):
    """One abuser must not lock the rest of the world out."""
    django_user_model.objects.create_user(
        username="u", email="u@example.com", password="la-contrasenya-9", is_active=True
    )
    c = APIClient()
    for i in range(7):
        c.post(
            "/api/v1/auth/login/",
            {"email": f"v{i}@example.com", "password": "no"},
            format="json",
            REMOTE_ADDR="10.0.0.98",
        )
    ok = APIClient().post(
        "/api/v1/auth/login/",
        {"email": "u@example.com", "password": "la-contrasenya-9"},
        format="json",
        REMOTE_ADDR="10.0.0.97",
    )
    assert ok.status_code == 200, ok.content


@pytest.mark.django_db
def test_registration_is_rate_limited(settings):
    """5/hour per IP. Every registration sends a verification email, and
    the Brevo free tier is 300/day: a spray from one IP can burn the
    project's whole mail budget in minutes. The rate was configured in
    May-2026 and the class to use it was never written."""
    c = APIClient()
    codis = []
    for i in range(7):
        codis.append(
            c.post(
                "/api/v1/auth/register/",
                {
                    "email": f"nou{i}@example.com",
                    "password1": "una-contrasenya-llarga-9",
                    "password2": "una-contrasenya-llarga-9",
                    "accepta_termes": True,
                },
                format="json",
                REMOTE_ADDR="10.0.0.96",
            ).status_code
        )
    assert 429 in codis, codis
