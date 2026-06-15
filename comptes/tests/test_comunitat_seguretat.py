"""Guards for community safety: block, report, DM gate, hidden DM (Slice A)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from analytics.models import MetricaEsdeveniment
from comptes.models import BloqueigUsuari, DenunciaUsuari, Missatge, PerfilUsuari


def _user(django_user_model, name):
    # PerfilUsuari is auto-created by the post_save signal.
    return django_user_model.objects.create_user(
        username=name, email=f"{name}@example.com", password="x"
    )


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
def test_block_prevents_dm_both_directions(django_user_model):
    a = _user(django_user_model, "alice")
    b = _user(django_user_model, "bob")
    BloqueigUsuari.objects.create(blocker=a, blocked=b)
    # Blocked user (b) cannot DM the blocker (a).
    r = _client(b).post(
        "/api/v1/missatges/nou/", {"destinatari_pk": a.pk, "cos": "hola"}, format="json"
    )
    assert r.status_code == 403, r.content
    # And the blocker (a) cannot DM the blocked (b) either.
    r2 = _client(a).post(
        "/api/v1/missatges/nou/", {"destinatari_pk": b.pk, "cos": "hola"}, format="json"
    )
    assert r2.status_code == 403
    assert Missatge.objects.count() == 0


@pytest.mark.django_db
def test_accepta_dm_false_blocks_dm(django_user_model):
    a = _user(django_user_model, "anna")
    c = _user(django_user_model, "carles")
    PerfilUsuari.objects.filter(usuari=c).update(accepta_dm=False)
    r = _client(a).post(
        "/api/v1/missatges/nou/", {"destinatari_pk": c.pk, "cos": "ei"}, format="json"
    )
    assert r.status_code == 403
    assert Missatge.objects.count() == 0


@pytest.mark.django_db
def test_dm_allowed_when_no_block(django_user_model):
    a = _user(django_user_model, "x1")
    b = _user(django_user_model, "x2")
    r = _client(a).post(
        "/api/v1/missatges/nou/", {"destinatari_pk": b.pk, "cos": "hola"}, format="json"
    )
    assert r.status_code == 201
    assert Missatge.objects.count() == 1


@pytest.mark.django_db
def test_denunciar_creates_report(django_user_model):
    a = _user(django_user_model, "rep")
    b = _user(django_user_model, "tgt")
    r = _client(a).post(
        "/api/v1/comunitat/denunciar/",
        {"tipus": "usuari", "target_pk": b.pk, "motiu": "spam"},
        format="json",
    )
    assert r.status_code == 201, r.content
    d = DenunciaUsuari.objects.get()
    assert (
        d.tipus == "usuari" and d.usuari_denunciat_id == b.pk and d.estat == "pendent"
    )
    # Slice E: server-side instrumentation fired.
    assert MetricaEsdeveniment.objects.filter(
        clau="denuncia_creada", dimensio_1="usuari"
    ).exists()


@pytest.mark.django_db
def test_thread_exposes_block_state(django_user_model):
    a = _user(django_user_model, "tb1")
    b = _user(django_user_model, "tb2")
    Missatge.objects.create(remitent=a, destinatari=b, cos="hola")
    body = _client(a).get(f"/api/v1/missatges/amb/{b.pk}/").json()
    assert body["altre"]["bloquejat"] is False
    BloqueigUsuari.objects.create(blocker=a, blocked=b)
    body2 = _client(a).get(f"/api/v1/missatges/amb/{b.pk}/").json()
    assert body2["altre"]["bloquejat"] is True


@pytest.mark.django_db
def test_dm_and_block_events_registered(django_user_model):
    a = _user(django_user_model, "ev1")
    b = _user(django_user_model, "ev2")
    _client(a).post(
        "/api/v1/missatges/nou/", {"destinatari_pk": b.pk, "cos": "hi"}, format="json"
    )
    _client(a).post("/api/v1/comunitat/bloquejar/", {"usuari_pk": b.pk}, format="json")
    assert MetricaEsdeveniment.objects.filter(clau="dm_enviat").exists()
    assert MetricaEsdeveniment.objects.filter(clau="bloqueig_creat").exists()


@pytest.mark.django_db
def test_hidden_dm_not_served(django_user_model):
    a = _user(django_user_model, "h1")
    b = _user(django_user_model, "h2")
    m = Missatge.objects.create(remitent=a, destinatari=b, cos="secret")
    # Visible before hiding.
    body = _client(a).get(f"/api/v1/missatges/amb/{b.pk}/").json()
    assert any(x["cos"] == "secret" for x in body["missatges"])
    # Hidden -> not served to either party.
    m.ocult = True
    m.save(update_fields=["ocult"])
    body2 = _client(a).get(f"/api/v1/missatges/amb/{b.pk}/").json()
    assert all(x["cos"] != "secret" for x in body2["missatges"])
    body3 = _client(b).get("/api/v1/missatges/").json()
    assert body3["results"] == []


@pytest.mark.django_db
def test_staff_resolve_report_hides_dm(django_user_model):
    a = _user(django_user_model, "s1")
    b = _user(django_user_model, "s2")
    staff = django_user_model.objects.create_user(
        username="modstaff", email="m@example.com", password="x", is_staff=True
    )
    m = Missatge.objects.create(remitent=a, destinatari=b, cos="abús")
    d = DenunciaUsuari.objects.create(
        reporter=b, tipus="missatge", missatge=m, motiu="abús"
    )
    r = _client(staff).post(
        f"/api/v1/staff/denuncies/{d.pk}/resoldre/",
        {"action": "revisar", "ocultar": True},
        format="json",
    )
    assert r.status_code == 200, r.content
    m.refresh_from_db()
    d.refresh_from_db()
    assert m.ocult is True and d.estat == "revisada"
