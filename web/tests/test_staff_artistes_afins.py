"""The «artistes afins» view shows who has engaged with us, and only them."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from comptes.models import UserArtista
from music.models import Artista
from social.models import InvitacioColaboracioIG

URL = "/api/v1/staff/artistes/afins/"


def _invita(artista, media, estat):
    InvitacioColaboracioIG.objects.create(
        artista=artista,
        username_snapshot="x",
        ig_media_id=media,
        tipus_publicacio="top",
        data_invitacio=timezone.make_aware(datetime.datetime(2026, 11, 1)),
        estat=estat,
    )


@pytest.mark.django_db
def test_nomes_ixen_els_que_han_respost_i_el_mes_afi_va_primer(django_user_model):
    staff = django_user_model.objects.create_user(
        username="s", email="s@example.com", password="x", is_staff=True
    )
    accepta = Artista.objects.create(nom="Accepta", slug="accepta", aprovat=True)
    gestionat = Artista.objects.create(nom="Gestionat", slug="gestionat", aprovat=True)
    callat = Artista.objects.create(nom="Callat", slug="callat", aprovat=True)
    _invita(accepta, "m1", InvitacioColaboracioIG.ESTAT_ACCEPTADA)
    _invita(accepta, "m2", InvitacioColaboracioIG.ESTAT_CADUCADA)
    _invita(callat, "m3", InvitacioColaboracioIG.ESTAT_CADUCADA)
    UserArtista.objects.create(
        usuari=staff, artista=gestionat, estat=UserArtista.ESTAT_APROVAT
    )

    c = APIClient()
    c.force_authenticate(user=staff)
    files = c.get(URL).json()["results"]

    assert [f["nom"] for f in files] == ["Accepta", "Gestionat"]
    assert files[0]["collabs_acceptades"] == 1
    assert files[0]["collabs_convidades"] == 2
    assert files[1]["te_gestor"] is True


@pytest.mark.django_db
def test_no_es_public():
    assert APIClient().get(URL).status_code in (401, 403)
