"""El gestor sap quan al seu artista li entren cançons pendents.

La promesa: un correu per gestor i artista amb les cançons pendents
creades des de l'últim avís; el stamp `avis_novetats_at` avança només
quan s'envia, així que un segon pas no repeteix res i sense cançons
noves no s'envia res. Sense `--send` només informa.

# Spec: docs/architecture/comptes.md
"""

from __future__ import annotations

import datetime

import pytest
from django.core import mail
from django.core.management import call_command

from comptes.models import UserArtista, Usuari
from music.models import Album, Artista, Canco

AVUI = datetime.date(2026, 10, 23)


def _gestor_amb_artista():
    u = Usuari.objects.create_user(
        email="samu@example.test", password="x", username="samu"
    )
    a = Artista.objects.create(nom="SAMU", lastfm_nom="SAMU", aprovat=True)
    ua = UserArtista.objects.create(
        usuari=u, artista=a, verificat=True, estat=UserArtista.ESTAT_APROVAT
    )
    return ua


def _canco(artista, nom, *, verificada=False):
    album, _ = Album.objects.get_or_create(
        artista=artista, nom="Eclipsi sensorial", defaults={"data_llancament": AVUI}
    )
    return Canco.objects.create(
        artista=artista,
        album=album,
        nom=nom,
        data_llancament=AVUI,
        verificada=verificada,
        activa=True,
    )


@pytest.mark.django_db
def test_one_mail_with_the_new_pending_songs_and_the_stamp_moves_only_on_send():
    ua = _gestor_amb_artista()
    _canco(ua.artista, "Inigualable")
    _canco(ua.artista, "Correfoc")
    _canco(ua.artista, "Ja aprovada", verificada=True)

    call_command("avisar_gestors_novetats")  # dry-run
    assert mail.outbox == []
    ua.refresh_from_db()
    assert ua.avis_novetats_at is None

    call_command("avisar_gestors_novetats", "--send")
    assert len(mail.outbox) == 1
    m = mail.outbox[0]
    assert m.to == ["samu@example.test"]
    assert "2 cançons noves pendents" in m.subject
    html = m.alternatives[0][0]
    assert "Inigualable" in html and "Correfoc" in html and "Ja aprovada" not in html
    assert "/compte/artista/samu/" in html
    ua.refresh_from_db()
    assert ua.avis_novetats_at is not None


@pytest.mark.django_db
def test_a_second_run_sends_nothing_until_a_newer_song_arrives():
    ua = _gestor_amb_artista()
    _canco(ua.artista, "Inigualable")
    call_command("avisar_gestors_novetats", "--send")
    assert len(mail.outbox) == 1

    call_command("avisar_gestors_novetats", "--send")
    assert len(mail.outbox) == 1  # nothing new → nothing sent

    # A song created after the stamp is the next mail; the old one is not.
    _canco(ua.artista, "Última pregunta")
    call_command("avisar_gestors_novetats", "--send")
    assert len(mail.outbox) == 2
    html = mail.outbox[1].alternatives[0][0]
    assert "Última pregunta" in html and "Inigualable" not in html


@pytest.mark.django_db
def test_only_verified_active_gestors_are_mailed():
    ua = _gestor_amb_artista()
    _canco(ua.artista, "Inigualable")
    # `verificat` is the edit-rights gate everywhere else too; a row
    # that lost it must not be mailed whatever `estat` still says.
    UserArtista.objects.filter(pk=ua.pk).update(verificat=False)
    call_command("avisar_gestors_novetats", "--send")
    assert mail.outbox == []
