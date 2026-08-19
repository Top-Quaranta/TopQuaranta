"""Vídeo de YouTube posat a mà des de la fitxa de la cançó.

La promesa: quan el correu diari diu «busca el vídeo d'aquesta cançó»,
hi ha on desar la resposta i el mesurador la recull la nit següent. Sense
això la llista de recerques demanaria feina que no es pot entregar.

Store-and-trust igual que Spotify: es valida el **format** i no es gasta
ni una unitat de quota comprovant-ho — la quota és el recurs que raciona
tota la integració, i qui enganxa l'enllaç està mirant el vídeo.

Dues destinacions, decidides pel que la cançó ja té:
  · sense Art Track → passa a ser l'Art Track (`youtube_video_id`);
  · amb Art Track   → s'afig com a carril (`CancoYouTubeVideo`), que és
    el que és un videoclip del canal propi.

I la tercera resposta: «revisada, no en té», que és final i és l'única
cosa que trau una cançó de la cua sense vídeo.

# Spec: docs/architecture/web.md
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from music.models import Album, Artista, Canco, CancoYouTubeVideo

VIDEO_A = "dQw4w9WgXcQ"
VIDEO_B = "kJQP7kiw5Fk"


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="manual_youtube_tester",
        email="my@example.com",
        password="x",
        is_staff=True,
    )
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_canco(**kw):
    a = Artista.objects.create(nom="EXEMPLE YT", lastfm_nom="EXEMPLE YT")
    al = Album.objects.create(artista=a, nom="EXEMPLE YT Al")
    return Canco.objects.create(
        artista=a, album=al, nom="EXEMPLE YT C", verificada=True, activa=True, **kw
    )


@pytest.mark.django_db
def test_a_pasted_link_becomes_the_art_track_and_closes_the_task(staff_client):
    """La cançó passa a ser mesurable i deixa de sortir a la cua.

    Marcar-la revisada no és un extra: si el vídeo es guardara sense
    tancar la tasca, el correu de demà tornaria a demanar-la.
    """
    c = _make_canco()
    r = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/",
        {"youtube_url": f"https://www.youtube.com/watch?v={VIDEO_A}&t=42s"},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.json()["youtube"]["video_id"] == VIDEO_A

    c.refresh_from_db()
    assert c.youtube_video_id == VIDEO_A
    assert c.youtube_match == Canco.MATCH_MANUAL
    assert c.youtube_matched_at is not None
    assert c.youtube_revisat is True


@pytest.mark.django_db
def test_a_second_video_is_an_extra_lane_not_a_replacement(staff_client):
    """Un videoclip no substitueix l'Art Track, s'hi suma.

    El senyal d'una cançó és la suma dels seus carrils; sobreescriure
    l'Art Track amb el videoclip perdria el públic que ja mesuràvem.
    """
    c = _make_canco(youtube_video_id=VIDEO_A)
    r = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/",
        {"youtube_url": f"https://youtu.be/{VIDEO_B}"},
        format="json",
    )
    assert r.status_code == 200, r.content

    c.refresh_from_db()
    assert c.youtube_video_id == VIDEO_A, "l'Art Track s'ha perdut"
    assert list(c.youtube_videos.values_list("video_id", flat=True)) == [VIDEO_B]


@pytest.mark.django_db
def test_the_same_video_twice_does_not_duplicate_a_lane(staff_client):
    c = _make_canco(youtube_video_id=VIDEO_A)
    for _ in range(2):
        staff_client.patch(
            f"/api/v1/staff/cancons/{c.pk}/",
            {"youtube_url": VIDEO_B},
            format="json",
        )
    assert CancoYouTubeVideo.objects.filter(canco=c, video_id=VIDEO_B).count() == 1


@pytest.mark.django_db
def test_a_channel_link_is_refused_with_a_message_that_names_the_mistake(staff_client):
    """El canal va a la fitxa de l'artista, i l'error ho ha de dir.

    Guardar un id de canal on va un vídeo no falla de seguida: falla
    cada nit, en silenci, tornant zero visualitzacions.
    """
    c = _make_canco()
    r = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/",
        {"youtube_url": "https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx"},
        format="json",
    )
    assert r.status_code == 400
    assert "canal" in r.json()["error"].lower()

    c.refresh_from_db()
    assert c.youtube_video_id == ""


def test_every_shape_youtube_hands_out_is_accepted():
    """La persona copia el que li dona el botó «Comparteix», no un id.

    YouTube reparteix cinc formes distintes del mateix vídeo segons on
    es clique; exigir-ne una és fer que l'operació falle per una cosa
    que el codi pot resoldre sol.
    """
    from web.api.staff._youtube_url import YoutubeUrlError, parse_video_id

    for brut in (
        f"https://www.youtube.com/watch?v={VIDEO_A}",
        f"https://www.youtube.com/watch?v={VIDEO_A}&list=PLxx&index=2",
        f"https://youtu.be/{VIDEO_A}?si=abc",
        f"https://www.youtube.com/shorts/{VIDEO_A}",
        f"https://www.youtube.com/embed/{VIDEO_A}",
        f"  {VIDEO_A}  ",
    ):
        assert parse_video_id(brut) == VIDEO_A, brut

    for dolent in ("", "https://www.youtube.com/playlist?list=PLxx", "no-soc-un-id"):
        with pytest.raises(YoutubeUrlError):
            parse_video_id(dolent)


@pytest.mark.django_db
def test_reviewed_without_a_video_is_a_valid_final_answer(staff_client):
    """Hi ha cançons que de veres no són a YouTube.

    Sense aquest tercer estat la cua no distingeix «ningú ho ha mirat»
    de «mirat, no n'hi ha» i repeteix les mateixes files per sempre.
    """
    c = _make_canco()
    r = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/",
        {"youtube_revisat": True},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.json()["youtube"]["revisat"] is True

    c.refresh_from_db()
    assert c.youtube_revisat is True
    assert c.youtube_video_id == "", "revisat no vol dir que en tinga"


@pytest.mark.django_db
def test_clearing_gives_the_song_back_to_automatic_discovery(staff_client):
    c = _make_canco(youtube_video_id=VIDEO_A, youtube_match=Canco.MATCH_MANUAL)
    r = staff_client.patch(
        f"/api/v1/staff/cancons/{c.pk}/", {"youtube_url": ""}, format="json"
    )
    assert r.status_code == 200, r.content

    c.refresh_from_db()
    assert c.youtube_video_id == ""
    assert c.youtube_match == ""
    assert c.youtube_matched_at is None
