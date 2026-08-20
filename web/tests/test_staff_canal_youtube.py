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
@pytest.mark.parametrize(
    "titol", ["Malifeta - Topic", "Malifeta - Tema"], ids=["anglés", "català"]
)
def test_a_topic_channel_is_refused_when_we_already_have_one(
    staff_client, artista, titol
):
    """The classic mix-up: searching an artist surfaces both channels and
    the "- Topic" one often ranks first. When discovery already found it,
    pasting it here would count the Art Track twice and lose the
    videoclip lane — the only lane this field exists to add."""
    artista.youtube_channel_id = "UCjaTeniemUnTopicHere00"
    artista.save(update_fields=["youtube_channel_id"])

    with patch.object(
        yt,
        "channel_info",
        return_value={"id": "UCoYEPFahaDY_6-VUEOeQ_IA", "title": titol},
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
def test_a_topic_channel_is_adopted_when_discovery_missed_it(staff_client, artista):
    """`search.list` buries brand-new and tiny channels: DUPLICATS had a
    perfectly good Topic channel with 4 videos that discovery never saw,
    and there was nowhere in the panel to supply it — it had to be fixed
    from a shell (2026-08-14). Now the operator can paste it, and it
    lands in the lane it belongs to.

    Matching happens immediately and that is not an optimisation: the
    nightly queue only visits artists whose `youtube_channel_id` is
    empty, so storing it without matching would freeze the artist with a
    channel and no songs — exactly the DUPLICATS state.
    """
    from datetime import date, timedelta

    from music.models import Album, Canco

    alb = Album.objects.create(
        artista=artista, nom="X", data_llancament=date.today() - timedelta(days=10)
    )
    canco = Canco.objects.create(
        artista=artista,
        album=alb,
        nom="Khimera",
        data_llancament=date.today() - timedelta(days=10),
        verificada=True,
        activa=True,
    )

    with (
        patch.object(
            yt,
            "channel_info",
            return_value={
                "id": "UCYPU3FvPV5Hm6mmi2CVaR6A",
                "title": "Malifeta - Topic",
            },
        ),
        patch.object(yt, "uploads_playlist", return_value="UUYPU3FvPV5Hm6mmi2CVaR6A"),
        patch.object(
            yt,
            "playlist_videos",
            return_value=[{"video_id": "ay5vSouZZsk", "title": "Khimera"}],
        ),
    ):
        r = staff_client.patch(
            f"/api/v1/staff/artistes/{artista.pk}/",
            {
                "youtube_canal_oficial": "https://www.youtube.com/@malifeta",
                # Exactly what the staff page sends.
                "youtube_canal_revisat": True,
            },
            format="json",
        )

    assert r.status_code == 200
    assert "automàtic" in r.json()["avis"]

    # …and the artist STAYS in the queue: the videoclip channel, which is
    # what that queue exists for, is still missing. The panel sends
    # `youtube_canal_revisat: true` in the same PATCH, so dropping only
    # the channel field marked it done and the row vanished (caught by
    # Miquel on Xafogor, minutes after this shipped).
    artista.refresh_from_db()
    assert artista.youtube_canal_revisat is False

    artista.refresh_from_db()
    assert artista.youtube_channel_id == "UCYPU3FvPV5Hm6mmi2CVaR6A"
    assert artista.youtube_uploads_playlist == "UUYPU3FvPV5Hm6mmi2CVaR6A"
    # The videoclip field stays empty: a Topic channel is not it.
    assert artista.youtube_canal_oficial == ""

    canco.refresh_from_db()
    assert canco.youtube_video_id == "ay5vSouZZsk"
    assert canco.youtube_match == Canco.MATCH_EXACTE


@pytest.mark.django_db
def test_percent_encoded_handle_reaches_youtube_intact(staff_client, artista):
    """Copiar la barra d'adreces d'un canal amb accent dóna
    `@ComboAvan%C3%A7at`, no `@ComboAvançat`. El `%` no és part del
    handle, així que la regex tallava a `@ComboAvan` i YouTube responia
    que no el coneix — l'operador havia d'arreglar-ho a mà (Miquel,
    2026-08-20).

    S'afirma el handle que arriba a YouTube, no el que es desa: el que
    es desa és l'id, i un id mockejat passaria igual amb el handle
    trencat."""
    with patch.object(
        yt, "channel_info", return_value={"id": CANAL, "title": "Combo Avançat"}
    ) as spy:
        r = staff_client.patch(
            f"/api/v1/staff/artistes/{artista.pk}/",
            {
                "youtube_canal_oficial": "https://www.youtube.com/@ComboAvan%C3%A7at",
                "youtube_canal_revisat": True,
            },
            format="json",
        )

    assert r.status_code == 200, r.content
    assert spy.call_args.kwargs == {"handle": "ComboAvançat"}
