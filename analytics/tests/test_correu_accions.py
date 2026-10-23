"""Un clic des del correu aprova o rebutja una cançó — i res més.

La promesa: l'enllaç del correu fa exactament el que faria l'staff al
panell, només per a qui té la sessió de l'staff oberta, només per a la
cançó i l'acció que l'enllaç signa. Qui no té sessió va al login i no
canvia res; un enllaç manipulat no canvia res.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime

import pytest
from django.test import Client

from analytics.management.commands import enviar_informe_youtube as cmd
from comptes.models import Usuari
from music.models import Album, Artista, Canco, HistorialRevisio
from web.api.staff.correu import enllac_accio

AVUI = datetime.date(2026, 10, 23)


def _canco(nom="Oversize"):
    a, _ = Artista.objects.get_or_create(
        nom="Gioba Fellini", defaults={"lastfm_nom": "Gioba Fellini", "aprovat": True}
    )
    album, _ = Album.objects.get_or_create(
        artista=a, nom="Divertimento", defaults={"data_llancament": AVUI}
    )
    return Canco.objects.create(
        artista=a,
        album=album,
        nom=nom,
        data_llancament=AVUI,
        verificada=False,
        activa=True,
        ml_classe="A",
        ml_confianca=0.96,
    )


def _staff_client():
    u = Usuari.objects.create_user(
        email="staff@example.test", password="x", username="staff", is_staff=True
    )
    c = Client()
    c.force_login(u)
    return c


@pytest.mark.django_db
def test_one_click_approves_and_the_row_links_are_the_ones_the_view_honours(
    monkeypatch,
):
    canco = _canco()
    monkeypatch.setattr(
        cmd, "flux_cancons", lambda today: {"target_verificacio_setmanal": 7}
    )
    row = cmd._pendents(AVUI)["files"][0]
    resp = _staff_client().get(row["aprovar"])
    assert resp.status_code == 200
    canco.refresh_from_db()
    assert canco.verificada and canco.activa
    assert "Aprovada" in resp.content.decode()


@pytest.mark.django_db
def test_one_click_rejects_only_that_song():
    canco = _canco()
    germana = _canco("Bestofme")
    resp = _staff_client().get(enllac_accio(canco.pk, "rebutjar"))
    assert resp.status_code == 200
    canco.refresh_from_db()
    germana.refresh_from_db()
    assert not canco.activa and not canco.verificada
    assert germana.activa  # «desvincular_canco», never the album or artist
    assert (
        HistorialRevisio.objects.filter(canco_nom="Oversize").latest("pk").motiu
        == "desvincular_canco"
    )


@pytest.mark.django_db
def test_without_a_staff_session_nothing_happens():
    canco = _canco()
    link = enllac_accio(canco.pk, "aprovar")
    anon = Client().get(link)
    assert anon.status_code == 302 and anon.url.startswith("/compte/accedir?next=")
    u = Usuari.objects.create_user(email="u@example.test", password="x", username="u")
    c = Client()
    c.force_login(u)
    assert c.get(link).status_code == 403
    canco.refresh_from_db()
    assert not canco.verificada


@pytest.mark.django_db
def test_a_link_cannot_be_bent_to_another_song_or_another_action():
    canco = _canco()
    altra = _canco("Bestofme")
    link = enllac_accio(canco.pk, "aprovar")
    token = link.rstrip("/").rsplit("/", 1)[1]
    c = _staff_client()
    assert (
        c.get(f"/api/v1/staff/correu/canco/{altra.pk}/aprovar/{token}/").status_code
        == 400
    )
    assert (
        c.get(f"/api/v1/staff/correu/canco/{canco.pk}/rebutjar/{token}/").status_code
        == 400
    )
    canco.refresh_from_db()
    altra.refresh_from_db()
    assert not canco.verificada and not altra.verificada and canco.activa
