"""The staff PATCH that sets `Artista.youtube_canal_oficial`.

YouTube stopped surfacing the `UC…` id anywhere in its interface, so a
handle is what an operator can actually copy out of the address bar.
Demanding the id made the queue unusable (caught 2026-08-12 filling in
Malifeta). `channels.list?forHandle=` resolves it for ONE quota unit.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from ingesta.clients import youtube as yt
from music.models import Artista

CANAL = "UCZ_RdKPMxRUQv4j3XX8Hsjg"


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="canal_yt_tester", email="cy@example.com", password="x", is_staff=True
    )
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def artista():
    return Artista.objects.create(nom="Malifeta", lastfm_nom="Malifeta", aprovat=True)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "entrada",
    [
        CANAL,
        f"https://www.youtube.com/channel/{CANAL}",
        "https://www.youtube.com/@malifeta",
        "@malifeta",
    ],
)
def test_accepts_every_shape_an_operator_can_copy(staff_client, artista, entrada):
    with patch.object(
        yt, "channel_info", return_value={"id": CANAL, "title": "MALIFETA"}
    ):
        r = staff_client.patch(
            f"/api/v1/staff/artistes/{artista.pk}/",
            {"youtube_canal_oficial": entrada, "youtube_canal_revisat": True},
            format="json",
        )
    assert r.status_code == 200, r.content
    artista.refresh_from_db()
    assert artista.youtube_canal_oficial == CANAL
    assert artista.youtube_canal_revisat is True


@pytest.mark.django_db
def test_an_unknown_handle_is_refused_with_a_readable_message(staff_client, artista):
    """A 400 the operator can read beats a channel id pointing nowhere."""
    with patch.object(yt, "channel_info", return_value=None):
        r = staff_client.patch(
            f"/api/v1/staff/artistes/{artista.pk}/",
            {"youtube_canal_oficial": "@no-existeix"},
            format="json",
        )
    assert r.status_code == 400
    assert "no coneix" in r.json()["error"]
    artista.refresh_from_db()
    assert artista.youtube_canal_oficial == ""


@pytest.mark.django_db
def test_no_en_te_needs_no_resolution(staff_client, artista):
    """The "no en té" button sends an empty value; it must not hit the API."""
    with patch.object(yt, "channel_info") as m:
        r = staff_client.patch(
            f"/api/v1/staff/artistes/{artista.pk}/",
            {"youtube_canal_oficial": "", "youtube_canal_revisat": True},
            format="json",
        )
    assert r.status_code == 200
    m.assert_not_called()
    artista.refresh_from_db()
    assert artista.youtube_canal_revisat is True
    assert artista.youtube_canal_oficial == ""


@pytest.mark.django_db
def test_refuses_the_auto_generated_topic_channel(staff_client, artista):
    """Searching an artist surfaces both channels and the "- Topic" one
    often ranks first, so pasting it is an easy mistake. Accepting it
    would count the Art Track twice and lose the videoclip lane — the
    only lane this field exists to add."""
    with patch.object(
        yt,
        "channel_info",
        return_value={"id": "UCoYEPFahaDY_6-VUEOeQ_IA", "title": "Malifeta - Topic"},
    ):
        r = staff_client.patch(
            f"/api/v1/staff/artistes/{artista.pk}/",
            {"youtube_canal_oficial": "https://www.youtube.com/@malifeta"},
            format="json",
        )
    assert r.status_code == 400
    assert "automàtic" in r.json()["error"]
    artista.refresh_from_db()
    assert artista.youtube_canal_oficial == ""


@pytest.mark.django_db
def test_refuses_the_localised_topic_channel_too(staff_client, artista):
    """A Catalan browser shows "- Tema"; same channel, same refusal."""
    with patch.object(
        yt, "channel_info", return_value={"id": "UCx", "title": "Malifeta - Tema"}
    ):
        r = staff_client.patch(
            f"/api/v1/staff/artistes/{artista.pk}/",
            {"youtube_canal_oficial": "@malifeta"},
            format="json",
        )
    assert r.status_code == 400
