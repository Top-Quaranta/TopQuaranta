"""Un clic des del correu aprova una cançó — i res més.

La promesa: l'enllaç «Aprovar» del correu fa exactament el que faria
l'staff al panell, només per a qui té la sessió de l'staff oberta,
només per a la cançó que l'enllaç signa. Rebutjar no és un clic: té una
segona decisió dins (cançó, àlbum o artista), així que eixe botó porta
a la fila del panell. Qui no té sessió va al login i no canvia res; un
enllaç manipulat no canvia res.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime

import pytest
from django.template.loader import render_to_string
from django.test import Client

from analytics.management.commands import enviar_informe_youtube as cmd
from comptes.models import Usuari
from music.models import Album, Artista, Canco
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


def _row(monkeypatch):
    monkeypatch.setattr(
        cmd, "flux_cancons", lambda today: {"target_verificacio_setmanal": 7}
    )
    return cmd._pendents(AVUI)["files"][0]


@pytest.mark.django_db
def test_one_click_approves_and_the_row_link_is_the_one_the_view_honours(
    monkeypatch,
):
    canco = _canco()
    resp = _staff_client().get(_row(monkeypatch)["aprovar"])
    assert resp.status_code == 200
    canco.refresh_from_db()
    assert canco.verificada and canco.activa
    assert "Aprovada" in resp.content.decode()


@pytest.mark.django_db
def test_rejecting_is_never_one_click_it_goes_to_the_panel_row(monkeypatch):
    canco = _canco()
    row = _row(monkeypatch)
    assert "rebutjar" not in row
    assert row["on"].startswith("/staff/cancons?")
    assert str(canco.artista_id) in row["on"]
    html = render_to_string("analytics/informe_youtube.html", cmd.build_context(AVUI))
    # The token carries a timestamp, so compare the path up to it.
    assert html.count(f"/correu/canco/{canco.pk}/aprovar/") == 1
    assert f"/correu/canco/{canco.pk}/rebutjar/" not in html
    token = row["aprovar"].rstrip("/").rsplit("/", 1)[1]
    resp = _staff_client().get(
        f"/api/v1/staff/correu/canco/{canco.pk}/rebutjar/{token}/"
    )
    assert resp.status_code == 400
    canco.refresh_from_db()
    assert canco.activa and not canco.verificada


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
def test_a_link_cannot_be_bent_to_another_song():
    canco = _canco()
    altra = _canco("Bestofme")
    token = enllac_accio(canco.pk, "aprovar").rstrip("/").rsplit("/", 1)[1]
    resp = _staff_client().get(
        f"/api/v1/staff/correu/canco/{altra.pk}/aprovar/{token}/"
    )
    assert resp.status_code == 400
    canco.refresh_from_db()
    altra.refresh_from_db()
    assert not canco.verificada and not altra.verificada
