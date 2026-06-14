"""Guards for the "has entrat al top" manager alert (Fase 2 D1)."""

from __future__ import annotations

import datetime

import pytest
from django.core import mail, signing
from django.core.management import call_command
from django.test import Client

from comptes.models import AvisTopEnviat, PerfilUsuari, UserArtista, Usuari
from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal


def _monday(d: datetime.date) -> datetime.date:
    return d - datetime.timedelta(days=d.weekday())


@pytest.fixture
def setup(db):
    setmana = _monday(datetime.date(2026, 6, 8))
    prev = setmana - datetime.timedelta(days=7)
    a = Artista.objects.create(nom="Puja Amunt", slug="puja-amunt", aprovat=True)
    al_a = Album.objects.create(nom="Al A", slug="al-a", artista=a)
    c = Canco.objects.create(
        nom="Cançó Nova",
        slug="canco-nova",
        artista=a,
        album=al_a,
        verificada=True,
        activa=True,
    )
    other = Artista.objects.create(nom="Altre", slug="altre", aprovat=True)
    al_o = Album.objects.create(nom="Al O", slug="al-o", artista=other)
    c_other = Canco.objects.create(
        nom="Vella",
        slug="vella",
        artista=other,
        album=al_o,
        verificada=True,
        activa=True,
    )
    # prev week: only the other cançó → `a` is a NEW entry this week.
    TopSetmanal.objects.create(
        territori="PPCC", setmana=prev, posicio=1, score_setmanal=1.0, canco=c_other
    )
    TopSetmanal.objects.create(
        territori="PPCC", setmana=setmana, posicio=1, score_setmanal=2.0, canco=c
    )
    u = Usuari.objects.create(username="gestor", email="gestor@example.com")
    PerfilUsuari.objects.update_or_create(usuari=u, defaults={"vol_avis_top": True})
    UserArtista.objects.create(usuari=u, artista=a, verificat=True, estat="aprovat")
    return {"setmana": setmana, "artista": a, "user": u}


@pytest.mark.django_db
def test_dry_run_sends_nothing(setup):
    mail.outbox.clear()
    call_command("enviar_avisos_top", setmana=setup["setmana"].isoformat())
    assert len(mail.outbox) == 0
    assert AvisTopEnviat.objects.count() == 0


@pytest.mark.django_db
def test_send_emails_and_is_idempotent(setup):
    mail.outbox.clear()
    call_command("enviar_avisos_top", setmana=setup["setmana"].isoformat(), send=True)
    assert len(mail.outbox) == 1
    assert "gestor@example.com" in mail.outbox[0].to
    assert AvisTopEnviat.objects.filter(
        artista=setup["artista"], setmana=setup["setmana"]
    ).exists()
    # Re-run: idempotent, no second email.
    call_command("enviar_avisos_top", setmana=setup["setmana"].isoformat(), send=True)
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_opt_out_manager_not_emailed(setup):
    PerfilUsuari.objects.filter(usuari=setup["user"]).update(vol_avis_top=False)
    mail.outbox.clear()
    call_command("enviar_avisos_top", setmana=setup["setmana"].isoformat(), send=True)
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_unsub_endpoint_flips_preference(setup):
    token = signing.dumps({"u": setup["user"].pk}, salt="avis-top-baixa")
    r = Client().get(f"/api/v1/compte/baixa-avis-top/?token={token}")
    assert r.status_code == 200
    assert PerfilUsuari.objects.get(usuari=setup["user"]).vol_avis_top is False
