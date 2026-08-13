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


def _amb_canco_viva(a):
    """The queues now require a live song; fixtures must qualify."""
    from datetime import date, timedelta

    from music.models import Album, Canco

    alb = Album.objects.create(
        artista=a, nom="Fixture", data_llancament=date.today() - timedelta(days=5)
    )
    Canco.objects.create(
        artista=a,
        album=alb,
        nom=f"Viva {a.nom}",
        data_llancament=date.today() - timedelta(days=5),
        verificada=True,
        activa=True,
    )
    return a


@pytest.fixture
def artista():
    return _amb_canco_viva(
        Artista.objects.create(nom="Sense IG", lastfm_nom="Sense IG", aprovat=True)
    )


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

    a = _amb_canco_viva(
        Artista.objects.create(
            nom="Suu",
            lastfm_nom="Suu",
            aprovat=True,
            instagram_url="https://www.instagram.com/tontaca13/",
            instagram_revisat=True,
        )
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
    a = _amb_canco_viva(
        Artista.objects.create(
            nom="Sellen",
            lastfm_nom="Sellen",
            aprovat=True,
            instagram_suggerit="john_sellen",
        )
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


@pytest.mark.django_db
def test_the_queue_hides_artists_with_no_live_song(staff_client):
    """An approved artist whose songs are all gone (or who never had any)
    has nothing a handle would be used for — no song to tag, no post to
    appear in. 1.500 of the 1.727 historic rows were this."""
    from datetime import date, timedelta

    from music.models import Album, Canco

    sense_res = Artista.objects.create(nom="Fòssil", lastfm_nom="Fòssil", aprovat=True)
    amb_viva = Artista.objects.create(nom="Actiu", lastfm_nom="Actiu", aprovat=True)
    alb = Album.objects.create(
        artista=amb_viva, nom="X", data_llancament=date.today() - timedelta(days=3)
    )
    Canco.objects.create(
        artista=amb_viva,
        album=alb,
        nom="T",
        data_llancament=date.today() - timedelta(days=3),
        verificada=True,
        activa=True,
    )

    noms = _noms(staff_client.get("/api/v1/staff/artistes/?instagram=pendent"))
    assert "Actiu" in noms
    assert "Fòssil" not in noms
    # …but `instagram=no` keeps its old meaning, untouched.
    assert "Fòssil" in _noms(staff_client.get("/api/v1/staff/artistes/?instagram=no"))


@pytest.mark.django_db
def test_ties_break_by_newest_song(staff_client):
    """Same tops (0), same live-song count (1): the artist who released
    THIS WEEK goes first — they are about to appear in the "nous singles"
    post, and that publication is the one chance to tag them."""
    from datetime import date, timedelta

    from music.models import Album, Canco

    def _mk(nom, dies):
        a = Artista.objects.create(nom=nom, lastfm_nom=nom, aprovat=True)
        alb = Album.objects.create(
            artista=a, nom="X", data_llancament=date.today() - timedelta(days=dies)
        )
        Canco.objects.create(
            artista=a,
            album=alb,
            nom=f"T {nom}",
            data_llancament=date.today() - timedelta(days=dies),
            verificada=True,
            activa=True,
        )
        return a

    _mk("Veterania", 300)
    _mk("Acabat de Traure", 2)

    res = staff_client.get(
        "/api/v1/staff/artistes/?aprovat=1&instagram=pendent&include_n_top=1&sort=-n_top"
    )
    noms = _noms(res)
    assert noms.index("Acabat de Traure") < noms.index("Veterania")


@pytest.mark.django_db
def test_a_dismissed_suggestion_is_remembered(staff_client):
    """Clearing the field alone was NOT enough: the nightly seeder found
    the same handle at the same source and put it straight back — caught
    the morning after day one."""
    a = _amb_canco_viva(
        Artista.objects.create(
            nom="Repetit",
            lastfm_nom="Repetit",
            aprovat=True,
            instagram_suggerit="compte_dolent",
        )
    )

    staff_client.patch(
        f"/api/v1/staff/artistes/{a.pk}/",
        {"instagram_suggerit": ""},
        format="json",
    )

    a.refresh_from_db()
    assert a.instagram_suggerit == ""
    assert a.instagram_suggerits_descartats == ["compte_dolent"]


@pytest.mark.django_db
def test_accepting_is_not_dismissing(staff_client):
    """The accept path clears the suggestion too — but an accepted handle
    must not land on the refused list."""
    a = _amb_canco_viva(
        Artista.objects.create(
            nom="Acceptat",
            lastfm_nom="Acceptat",
            aprovat=True,
            instagram_suggerit="compte_bo",
        )
    )

    staff_client.patch(
        f"/api/v1/staff/artistes/{a.pk}/",
        {"instagram_url": "https://www.instagram.com/compte_bo/"},
        format="json",
    )

    a.refresh_from_db()
    assert a.instagram_suggerit == ""
    assert a.instagram_suggerits_descartats == []
