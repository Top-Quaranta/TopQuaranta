"""El brief diari diu QUÈ espera a cada cua de l'staff, i qui s'ha registrat.

La promesa: les tasques ixen dels mateixos comptadors que el panell
(`comptadors()`), només les que no són a zero, i cada una porta les
seues primeres files (què és, de qui, on decidir-ho) amb un «… i N més»
quan n'hi ha més que les que caben. Els usuaris nous de l'última
setmana ixen amb si han activat el compte i acabat l'onboarding. L'assumpte
resumeix el que hi ha per fer.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from analytics.management.commands import enviar_informe_youtube as cmd
from comptes.models import PerfilUsuari, PropostaArtista, Publicacio, Usuari

AVUI = timezone.localdate()


def _ctx(monkeypatch):
    monkeypatch.setattr(
        cmd, "flux_cancons", lambda today: {"target_verificacio_setmanal": 0}
    )
    return cmd.build_context(AVUI)


def _usuari(email, *, dies=0, actiu=True, onboarding=False):
    u = Usuari.objects.create_user(
        email=email, password="x", username=email, is_active=actiu
    )
    Usuari.objects.filter(pk=u.pk).update(
        date_joined=timezone.now() - datetime.timedelta(days=dies)
    )
    PerfilUsuari.objects.filter(usuari=u).update(onboarding_complet=onboarding)
    return u


@pytest.mark.django_db
def test_each_open_queue_lists_its_rows_and_the_subject_counts_them(monkeypatch):
    jordi = _usuari("jordi@example.test", dies=30, onboarding=True)
    for i in range(cmd._FILES_TASCA + 1):
        PropostaArtista.objects.create(
            usuari=jordi, nom=f"Proposta {i}", justificacio="x", localitzacions=[]
        )
    Publicacio.objects.create(
        autor=jordi, titol="Busco lletristes", cos="x", estat=Publicacio.ESTAT_PENDENT
    )
    ctx = _ctx(monkeypatch)
    per_cua = {t["on"]: t for t in ctx["tasques"]}
    assert set(per_cua) == {"/staff/propostes", "/staff/publicacions"}
    props = per_cua["/staff/propostes"]
    assert props["n"] == cmd._FILES_TASCA + 1
    assert len(props["files"]) == cmd._FILES_TASCA and props["mes"] == 1
    assert props["files"][0]["titol"] == "Proposta 0"
    assert props["files"][0]["on"].startswith("/staff/propostes/")
    assert "jordi@example.test" in props["files"][0]["sub"]
    pub = per_cua["/staff/publicacions"]
    assert [f["titol"] for f in pub["files"]] == ["Busco lletristes"] and pub[
        "mes"
    ] == 0
    assert ctx["subject"].startswith("[TopQuaranta] Brief diari · ")
    assert f"{cmd._FILES_TASCA + 2} tasques" in ctx["subject"]
    text = cmd.render_text(ctx)
    assert (
        "TASQUES PENDENTS" in text
        and "Busco lletristes" in text
        and "… i 1 més" in text
    )


@pytest.mark.django_db
def test_new_users_of_the_week_say_whether_they_got_in(monkeypatch):
    _usuari("ahir@example.test", dies=1, onboarding=True)
    _usuari("penjat@example.test", dies=3, actiu=False)
    _usuari("vell@example.test", dies=cmd._DIES_USUARIS_NOUS + 1, onboarding=True)
    ctx = _ctx(monkeypatch)
    files = {u["email"]: u for u in ctx["usuaris_nous"]}
    assert list(files) == ["ahir@example.test", "penjat@example.test"]
    assert (
        files["ahir@example.test"]["actiu"] and files["ahir@example.test"]["onboarding"]
    )
    assert not files["penjat@example.test"]["actiu"]
    assert not files["penjat@example.test"]["onboarding"]
    assert files["ahir@example.test"]["on"].startswith("/staff/usuaris/")
    assert "2 usuaris nous" in ctx["subject"]
    assert "USUARIS NOUS" in cmd.render_text(ctx)


@pytest.mark.django_db
def test_nothing_open_means_no_blocks_and_nothing_in_the_subject(monkeypatch):
    ctx = _ctx(monkeypatch)
    assert ctx["tasques"] == [] and ctx["usuaris_nous"] == []
    assert "tasques" not in ctx["subject"] and "usuaris" not in ctx["subject"]
    text = cmd.render_text(ctx)
    assert "TASQUES PENDENTS" not in text and "USUARIS NOUS" not in text
