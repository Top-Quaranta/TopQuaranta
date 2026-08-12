"""The "No en té" answer on the Instagram queue.

Same third state as the YouTube one, for the same reason: plenty of small
artists genuinely have no Instagram, and without a way to say so they come
back in the queue on every pass and get re-checked by hand forever.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from music.models import Artista


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="ig_revisat_tester",
        email="ig@example.com",
        password="x",
        is_staff=True,
    )
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def artista():
    return Artista.objects.create(nom="Sense IG", lastfm_nom="Sense IG", aprovat=True)


def _noms(res):
    return [r["nom"] for r in res.json()["results"]]


@pytest.mark.django_db
def test_pendent_drops_the_artist_once_reviewed(staff_client, artista):
    assert "Sense IG" in _noms(
        staff_client.get("/api/v1/staff/artistes/?instagram=pendent")
    )

    r = staff_client.patch(
        f"/api/v1/staff/artistes/{artista.pk}/",
        {"instagram_revisat": True},
        format="json",
    )
    assert r.status_code == 200

    assert "Sense IG" not in _noms(
        staff_client.get("/api/v1/staff/artistes/?instagram=pendent")
    )


@pytest.mark.django_db
def test_filling_the_url_counts_as_reviewing(staff_client, artista):
    """The operator shouldn't have to say "done" twice."""
    staff_client.patch(
        f"/api/v1/staff/artistes/{artista.pk}/",
        {"instagram_url": "https://www.instagram.com/algu/"},
        format="json",
    )
    artista.refresh_from_db()
    assert artista.instagram_revisat is True


@pytest.mark.django_db
def test_instagram_no_keeps_its_old_meaning(staff_client, artista):
    """`instagram=no` is "has no URL", full stop — reviewing doesn't hide
    the artist from it, so existing callers don't shift under us."""
    artista.instagram_revisat = True
    artista.save(update_fields=["instagram_revisat"])

    assert "Sense IG" in _noms(staff_client.get("/api/v1/staff/artistes/?instagram=no"))
