"""The OTP half of `IsStaff` — the branch no test had ever executed.

A 2026-08-15 audit replaced the whole OTP check in
`web/api/staff/_common.py` with `return True` and **every test in
`web/tests/` and `comptes/tests/` still passed**. The cause is
structural, not an oversight in one file: staff fixtures authenticate
with `force_authenticate`, which never runs django-otp's middleware, so
`user.is_verified` does not exist, `getattr(..., None)` returns None and
the permission short-circuits to allowed. The `del user.is_verified` that
14 fixtures perform to "defeat the gate" is a placebo — it deletes an
attribute that was never attached.

So the gate is honest in production (the middleware does attach it) and
unreachable from the suite. These tests attach `is_verified` themselves,
which is exactly what the middleware does, and pin all three states.

The staff panel is where artists get merged, users get deleted and
social credentials get written; 2FA is the only thing between a stolen
session cookie and all of that.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

ENDPOINT = "/api/v1/staff/artistes/"


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(
        username="otp_gate_staff",
        email="otp@example.com",
        password="x",
        is_staff=True,
    )


@pytest.mark.django_db
def test_staff_without_a_verified_otp_session_is_refused(staff):
    """The branch that was unreachable: OTP present and NOT satisfied."""
    staff.is_verified = lambda: False
    assert _client(staff).get(ENDPOINT).status_code == 403


@pytest.mark.django_db
def test_staff_with_a_verified_otp_session_is_allowed(staff):
    staff.is_verified = lambda: True
    assert _client(staff).get(ENDPOINT).status_code == 200


@pytest.mark.django_db
def test_no_otp_middleware_means_no_otp_requirement(staff):
    """Deliberate, and the reason the gate was invisible: with no
    middleware attached there is nothing to ask, so the permission falls
    back to is_staff alone. Pinned so nobody 'fixes' it into a deny and
    locks the panel out wherever the middleware isn't wired."""
    assert not hasattr(staff, "is_verified")
    assert _client(staff).get(ENDPOINT).status_code == 200


@pytest.mark.django_db
def test_a_verified_otp_session_does_not_make_a_normal_user_staff(
    db, django_user_model
):
    """OTP is a second factor, never a promotion."""
    normal = django_user_model.objects.create_user(
        username="otp_gate_normal", email="n@example.com", password="x"
    )
    normal.is_verified = lambda: True
    assert _client(normal).get(ENDPOINT).status_code == 403


@pytest.mark.django_db
def test_anonymous_is_refused():
    assert APIClient().get(ENDPOINT).status_code in (401, 403)
