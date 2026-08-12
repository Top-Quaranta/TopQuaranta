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


@pytest.mark.django_db
def test_a_refused_handle_comes_back_to_the_queue(staff_client):
    """Meta refusing a handle must empty the field and re-open the artist.

    The value is worthless to us AND public — it rides the artist page and
    the JSON-LD `sameAs`, so a renamed account leaves a dead link in
    Google's structured data. Keeping it "reviewed" would park the artist
    in a list nobody visits.
    """
    from django.utils import timezone

    from social.management.commands.publicar_social import _marca_handles_rebutjats

    a = Artista.objects.create(
        nom="Suu",
        lastfm_nom="Suu",
        aprovat=True,
        instagram_url="https://www.instagram.com/tontaca13/",
        instagram_revisat=True,
    )

    _marca_handles_rebutjats(["tontaca13"])

    a.refresh_from_db()
    assert a.instagram_url == ""
    # The old value survives: Meta's error also fires for merely-private
    # accounts, which are still a valid human link.
    assert a.instagram_rebutjat_url == "https://www.instagram.com/tontaca13/"
    assert a.instagram_rebutjat_at is not None
    assert a.instagram_revisat is False
    assert "Suu" in _noms(staff_client.get("/api/v1/staff/artistes/?instagram=pendent"))
    del timezone


@pytest.mark.django_db
def test_setting_a_new_url_clears_the_refusal(staff_client):
    a = Artista.objects.create(
        nom="Suu2",
        lastfm_nom="Suu2",
        aprovat=True,
        instagram_rebutjat_url="https://www.instagram.com/tontaca13/",
    )
    from django.utils import timezone

    a.instagram_rebutjat_at = timezone.now()
    a.save(update_fields=["instagram_rebutjat_at"])

    staff_client.patch(
        f"/api/v1/staff/artistes/{a.pk}/",
        {"instagram_url": "https://www.instagram.com/suu_music/"},
        format="json",
    )

    a.refresh_from_db()
    assert a.instagram_rebutjat_at is None
    assert a.instagram_rebutjat_url == ""
    assert a.instagram_revisat is True


@pytest.mark.django_db
def test_accepting_a_url_consumes_the_suggestion(staff_client):
    """The suggestion is provisional scaffolding: once a URL lands
    (accepted or typed), keeping it around would re-suggest a decision
    that is already made."""
    a = Artista.objects.create(
        nom="Sobre Mi Gata",
        lastfm_nom="Sobre Mi Gata",
        aprovat=True,
        instagram_suggerit="sobremigata",
    )

    r = staff_client.patch(
        f"/api/v1/staff/artistes/{a.pk}/",
        {"instagram_url": "https://www.instagram.com/sobremigata/"},
        format="json",
    )
    assert r.status_code == 200

    a.refresh_from_db()
    assert a.instagram_url == "https://www.instagram.com/sobremigata/"
    assert a.instagram_suggerit == ""
    assert a.instagram_revisat is True


@pytest.mark.django_db
def test_dismissing_a_suggestion_keeps_the_artist_pending(staff_client):
    """Rejecting the candidate answers "not this handle", not "has no
    Instagram" — the row must stay in the queue."""
    a = Artista.objects.create(
        nom="Sellen",
        lastfm_nom="Sellen",
        aprovat=True,
        instagram_suggerit="john_sellen",
    )

    staff_client.patch(
        f"/api/v1/staff/artistes/{a.pk}/",
        {"instagram_suggerit": ""},
        format="json",
    )

    a.refresh_from_db()
    assert a.instagram_suggerit == ""
    assert a.instagram_revisat is False
    assert "Sellen" in _noms(
        staff_client.get("/api/v1/staff/artistes/?instagram=pendent")
    )
