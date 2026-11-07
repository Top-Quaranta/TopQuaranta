"""FASE B — staff workbench endpoints for SolicitudRevisio.

Covers:
  * Permission perimeter (anon, non-staff, staff).
  * List with filters + pagination shape.
  * Detail inflating Canco + reconsiderada state.
  * marcar-en-revisio / reconsiderar-rebutjada / resoldre flows.
  * Email to gestor on resoldre.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from comptes.models import SolicitudRevisio, UserArtista, Usuari
from music.models import (
    Album,
    Artista,
    ArtistaDeezer,
    Canco,
    HistorialRevisio,
    StaffAuditLog,
)


@pytest.fixture
def artista(db):
    a = Artista.objects.create(nom="Wb Band", slug="wb-band", aprovat=True)
    ArtistaDeezer.objects.create(artista=a, deezer_id=12345, principal=True)
    return a


@pytest.fixture
def gestor(db, artista):
    u = Usuari.objects.create_user(
        username="gwb", email="gwb@example.com", password="x"
    )
    UserArtista.objects.create(
        usuari=u,
        artista=artista,
        sollicitud_text="x" * 25,
        verificat=True,
        estat=UserArtista.ESTAT_APROVAT,
    )
    return u


@pytest.fixture
def staff_user(db):
    return Usuari.objects.create_user(
        username="staffwb",
        email="staff@example.com",
        password="x",
        is_staff=True,
    )


@pytest.fixture
def sollicitud(db, gestor, artista):
    album = Album.objects.create(artista=artista, nom="EP", slug="ep")
    c1 = Canco.objects.create(
        artista=artista,
        album=album,
        nom="T1",
        slug="wb-t1",
        verificada=False,
    )
    c2 = Canco.objects.create(
        artista=artista,
        album=album,
        nom="T2",
        slug="wb-t2",
        verificada=False,
    )
    h = HistorialRevisio.objects.create(
        canco_nom="T-rej",
        album_nom="EP",
        artista_nom=artista.nom,
        artista_deezer_id=12345,
        canco_deezer_id=99,
        canco_isrc="X0000000001",
        decisio="rebutjada",
        motiu="desvincular_canco",
    )
    return SolicitudRevisio.objects.create(
        gestor=gestor,
        artista=artista,
        pendents_ids=[c1.pk, c2.pk],
        rebutjades_snapshot=[
            {
                "historial_pk": h.pk,
                "deezer_id": 99,
                "isrc": "X0000000001",
                "nom": "T-rej",
                "album_nom": "EP",
                "motiu": "desvincular_canco",
            }
        ],
    )


@pytest.fixture
def client_staff(staff_user):
    c = APIClient()
    c.force_authenticate(user=staff_user)
    return c


# ───────────────────────── Permission ─────────────────────────────


def test_list_anon_forbidden(db):
    c = APIClient()
    assert c.get("/api/v1/staff/sollicituds-revisio/").status_code in (401, 403)


def test_list_non_staff_forbidden(db, gestor):
    c = APIClient()
    c.force_authenticate(user=gestor)
    assert c.get("/api/v1/staff/sollicituds-revisio/").status_code == 403


def test_list_staff_ok(client_staff):
    r = client_staff.get("/api/v1/staff/sollicituds-revisio/")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"results", "page", "n_pages", "total"}


# ───────────────────────── List filters ───────────────────────────


def test_list_default_filter_pendent(client_staff, sollicitud):
    sollicitud.estat = SolicitudRevisio.ESTAT_RESOLTA
    sollicitud.save(update_fields=["estat"])
    r = client_staff.get("/api/v1/staff/sollicituds-revisio/")
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_list_filter_by_estat(client_staff, sollicitud):
    sollicitud.estat = SolicitudRevisio.ESTAT_RESOLTA
    sollicitud.save(update_fields=["estat"])
    r = client_staff.get("/api/v1/staff/sollicituds-revisio/?estat=resolta")
    assert r.status_code == 200
    assert len(r.json()["results"]) == 1


def test_list_filter_by_artista_pk(client_staff, sollicitud, artista):
    r = client_staff.get(f"/api/v1/staff/sollicituds-revisio/?artista_pk={artista.pk}")
    assert r.status_code == 200
    assert len(r.json()["results"]) == 1


# ───────────────────────── Detail ─────────────────────────────────


def test_detall_inflates_pendents_and_rebutjades(client_staff, sollicitud):
    r = client_staff.get(f"/api/v1/staff/sollicituds-revisio/{sollicitud.pk}/")
    assert r.status_code == 200
    body = r.json()
    assert len(body["pendents"]) == 2
    assert all("nom" in p for p in body["pendents"])
    assert len(body["rebutjades"]) == 1
    assert body["rebutjades"][0]["motiu"] == "desvincular_canco"
    assert body["rebutjades"][0]["reconsiderada"] is False
    assert body["rebutjades"][0]["historial_present"] is True


def test_detall_marks_missing_canco(client_staff, sollicitud):
    """Hard-delete a Canco between submission and resolution → it
    appears as `{pk, missing:True}` in the detail."""
    Canco.objects.filter(pk=sollicitud.pendents_ids[0]).delete()
    body = client_staff.get(
        f"/api/v1/staff/sollicituds-revisio/{sollicitud.pk}/"
    ).json()
    missing = [p for p in body["pendents"] if p.get("missing")]
    assert len(missing) == 1


# ───────────────────────── Actions ────────────────────────────────


def test_marcar_en_revisio_flips_estat(client_staff, sollicitud):
    r = client_staff.post(
        f"/api/v1/staff/sollicituds-revisio/{sollicitud.pk}/marcar-en-revisio/"
    )
    assert r.status_code == 200
    assert r.json()["estat"] == "revisada"
    sollicitud.refresh_from_db()
    assert sollicitud.estat == "revisada"


def test_reconsiderar_rebutjada_flips_flag_and_audits(client_staff, sollicitud):
    historial_pk = sollicitud.rebutjades_snapshot[0]["historial_pk"]
    r = client_staff.post(
        f"/api/v1/staff/sollicituds-revisio/{sollicitud.pk}/reconsiderar-rebutjada/",
        {"historial_pk": historial_pk},
        format="json",
    )
    assert r.status_code == 200
    h = HistorialRevisio.objects.get(pk=historial_pk)
    assert h.reconsiderada is True
    assert StaffAuditLog.objects.filter(
        action="rebutjada_reconsiderada", target_id=historial_pk
    ).exists()


def test_reconsiderar_rejects_unrelated_historial(client_staff, sollicitud):
    """Staff can only reconsider a historial pk that's actually in the
    sol·licitud snapshot — defence against crafted requests."""
    other = HistorialRevisio.objects.create(
        canco_nom="other",
        artista_nom="x",
        decisio="rebutjada",
        motiu="desvincular_canco",
    )
    r = client_staff.post(
        f"/api/v1/staff/sollicituds-revisio/{sollicitud.pk}/reconsiderar-rebutjada/",
        {"historial_pk": other.pk},
        format="json",
    )
    assert r.status_code == 400


def test_resoldre_marks_resolt_and_emails_gestor(
    client_staff, sollicitud, staff_user, mailoutbox
):
    r = client_staff.post(
        f"/api/v1/staff/sollicituds-revisio/{sollicitud.pk}/resoldre/",
        {"nota": "Verificades 2, una rebutjada reconsiderada."},
        format="json",
    )
    assert r.status_code == 200
    sollicitud.refresh_from_db()
    assert sollicitud.estat == "resolta"
    assert sollicitud.resolt_per == staff_user
    assert sollicitud.resolt_at is not None
    assert sollicitud.nota_resolucio.startswith("Verificades 2")
    # Email to the gestor.
    assert len(mailoutbox) == 1
    assert sollicitud.gestor.email in mailoutbox[0].to
    assert "resolta" in mailoutbox[0].subject.lower()


def test_resoldre_twice_400(client_staff, sollicitud):
    client_staff.post(f"/api/v1/staff/sollicituds-revisio/{sollicitud.pk}/resoldre/")
    r = client_staff.post(
        f"/api/v1/staff/sollicituds-revisio/{sollicitud.pk}/resoldre/"
    )
    assert r.status_code == 400


# ───────────────────────── Gestor sollicituds endpoint ────────────


def test_gestor_sollicituds_returns_latest_and_count(db, gestor, artista, sollicitud):
    c = APIClient()
    c.force_authenticate(user=gestor)
    r = c.get(f"/api/v1/compte/artista/{artista.slug}/sollicituds/")
    assert r.status_code == 200
    body = r.json()
    assert body["n_total"] == 1
    assert body["ultima"]["pk"] == sollicitud.pk
    assert body["ultima"]["estat"] == "pendent"


def test_gestor_sollicituds_empty(db, gestor, artista):
    c = APIClient()
    c.force_authenticate(user=gestor)
    r = c.get(f"/api/v1/compte/artista/{artista.slug}/sollicituds/")
    assert r.status_code == 200
    body = r.json()
    assert body["n_total"] == 0
    assert body["ultima"] is None


# ─────────────── Aprovar totes (panel + one click from the mail) ───────────────
# Promise: a gestor only asks review for Catalan songs, so approving is one
# action — every pendent song verified, the sol·licitud closed, the gestor
# mailed. The mail link does it only for a staff session and only for the
# sol·licitud it signs.


def _pendents_verificades(s):
    return set(
        Canco.objects.filter(pk__in=s.pendents_ids).values_list("verificada", flat=True)
    )


def test_aprovar_totes_verifies_every_pendent_and_resolves(
    client_staff, sollicitud, mailoutbox
):
    r = client_staff.post(
        f"/api/v1/staff/sollicituds-revisio/{sollicitud.pk}/aprovar-totes/"
    )
    assert r.status_code == 200
    sollicitud.refresh_from_db()
    assert sollicitud.estat == SolicitudRevisio.ESTAT_RESOLTA
    assert _pendents_verificades(sollicitud) == {True}
    assert any(sollicitud.gestor.email in m.to for m in mailoutbox)


def _mail_link(sollicitud, mailoutbox):
    import re

    from comptes.notifications import notify_admins_nova_sollicitud_revisio

    notify_admins_nova_sollicitud_revisio(sollicitud)
    html = (
        mailoutbox[-1].alternatives[0][0]
        if mailoutbox[-1].alternatives
        else mailoutbox[-1].body
    )
    m = re.search(r'https?://[^/"]+(/api/v1/staff/correu/sollicitud/[^"]+)"', html)
    assert m, "the staff mail must carry the one-click approve link"
    return m.group(1)


def test_mail_link_approves_all_for_staff_session(
    db, sollicitud, staff_user, mailoutbox
):
    from django.test import Client

    path = _mail_link(sollicitud, mailoutbox)
    c = Client()
    c.force_login(staff_user)
    assert c.get(path).status_code == 200
    sollicitud.refresh_from_db()
    assert sollicitud.estat == SolicitudRevisio.ESTAT_RESOLTA
    assert _pendents_verificades(sollicitud) == {True}


def test_mail_link_changes_nothing_without_staff_session_or_for_another_pk(
    db, sollicitud, staff_user, mailoutbox
):
    from django.test import Client

    path = _mail_link(sollicitud, mailoutbox)
    assert Client().get(path).status_code == 302  # anon → login
    c = Client()
    c.force_login(staff_user)
    swapped = path.replace(
        f"/sollicitud/{sollicitud.pk}/", f"/sollicitud/{sollicitud.pk + 1}/"
    )
    assert c.get(swapped).status_code == 400
    sollicitud.refresh_from_db()
    assert sollicitud.estat == SolicitudRevisio.ESTAT_PENDENT
    assert _pendents_verificades(sollicitud) == {False}


# ─────────────── Comentaris = conversa amb la bústia admin ───────────────
# Promise: what staff write on a sol·licitud reaches the requester's inbox,
# and the requester's reply from that inbox shows up on the staff page.


def test_staff_comment_reaches_user_and_reply_comes_back(
    client_staff, gestor, mailoutbox
):
    url = f"/api/v1/staff/usuaris/{gestor.pk}/conversa/"
    assert (
        client_staff.post(url, {"cos": "Ens falta l'enllaç de Deezer"}).status_code
        == 201
    )
    assert any(gestor.email in m.to for m in mailoutbox)

    user = APIClient()
    user.force_authenticate(user=gestor)
    inbox = user.get("/api/v1/missatges/").json()["results"]
    admin_pk = inbox[0]["altre"]["pk"]
    assert inbox[0]["darrer_missatge"]["cos"] == "Ens falta l'enllaç de Deezer"
    user.post(
        "/api/v1/missatges/nou/",
        {"destinatari_pk": admin_pk, "cos": "Ara el trobareu"},
    )

    fil = client_staff.get(url).json()["missatges"]
    assert [m["cos"] for m in fil] == [
        "Ens falta l'enllaç de Deezer",
        "Ara el trobareu",
    ]
    assert [m["meu"] for m in fil] == [True, False]


def test_conversa_is_staff_only(db, gestor):
    c = APIClient()
    c.force_authenticate(user=gestor)
    assert c.get(f"/api/v1/staff/usuaris/{gestor.pk}/conversa/").status_code == 403
