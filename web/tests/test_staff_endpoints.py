"""Smoke tests for the post-Sprint-C staff endpoints.

These don't replace endpoint-by-endpoint coverage — they're a guard
against the kind of breakage that hits when the package is split or
re-organised. We hit a representative endpoint from each major module
(estat, ranking_list, cancons_list) plus the `IsStaff` gate.

`IsStaff` requires `is_staff` AND `user.is_verified()` (django-otp).
We use `force_authenticate` and short-circuit `is_verified` by
deleting the attr — DRF then treats the user as exempt (the gate
returns True when `is_verified` is None to support test suites that
don't wire OTP middleware).
"""

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="sprint_c_tester",
        email="sc@example.com",
        password="x",
        is_staff=True,
    )
    # Defeat the django-otp gate. The IsStaff permission falls through
    # to True when the user has no `is_verified` attribute (no OTP
    # middleware in tests).
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def anon_client():
    return APIClient()


def test_staff_endpoints_require_auth(anon_client):
    """Anonymous requests must be rejected. Bound to the sprint-C
    refactor: if the IsStaff import wiring breaks, this is the first
    test to fall over."""
    for path in (
        "/api/v1/staff/dashboard/",
        "/api/v1/staff/estat/",
        "/api/v1/staff/ranking/",
        "/api/v1/staff/cancons/",
        "/api/v1/staff/artistes/",
    ):
        r = anon_client.get(path)
        assert r.status_code in (401, 403), (path, r.status_code)


def test_staff_estat_returns_full_payload(staff_client):
    """Estat is the dashboard's data source. It composes counts from
    every module — if any helper is mis-imported across the package
    boundary the call 500s. We only assert the top-level shape."""
    r = staff_client.get("/api/v1/staff/estat/")
    assert r.status_code == 200, r.content
    data = r.json()
    for key in (
        "bd",
        "flux",
        "whisper",
        "musicbrainz",
        "homonimia",
        "ranking",
        "senyal",
        "comunitat",
        "ml",
        "crons",
    ):
        assert key in data, f"Missing top-level key: {key}"
    assert "casos_sospitosos" in data["homonimia"]
    assert "casos" in data["homonimia"]


def test_staff_top_list_responds(staff_client):
    """Ranking list. Empty DB → empty entries; 200 either way."""
    r = staff_client.get("/api/v1/staff/ranking/?territori=CAT")
    assert r.status_code == 200, r.content
    data = r.json()
    assert "entries" in data
    assert data["territori"] == "CAT"


def test_staff_cancons_list_responds(staff_client):
    """Cançons list with default filters. Empty DB → empty results."""
    r = staff_client.get("/api/v1/staff/cancons/")
    assert r.status_code == 200, r.content
    data = r.json()
    assert "results" in data
    assert "total" in data


def test_staff_artistes_list_responds(staff_client):
    """Artistes list — exercises the cross-module import chain
    (artistes → pendents._artista_card → estat._homonym_suspects_qs)."""
    r = staff_client.get("/api/v1/staff/artistes/")
    assert r.status_code == 200, r.content
    data = r.json()
    assert "results" in data


def test_legacy_staff_views_shim_still_exposes_names():
    """Anything that did `from web.api import staff_views` must keep
    finding the old names. Guards against a future cleanup that
    removes the shim before everyone has migrated."""
    from web.api import staff_views

    for attr in ("dashboard", "estat", "top_list", "IsStaff"):
        assert hasattr(staff_views, attr), attr
