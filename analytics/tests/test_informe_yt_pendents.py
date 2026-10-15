"""El correu diari també reparteix les cançons pendents d'aprovar.

La promesa: cada matí ixen tantes pendents com cal per a no acumular
backlog —el nombre el dona la mateixa fórmula que `/staff/estat`, no una
constant del correu—, les de més confiança ML primer, i només les que
de veres estan pendents. Una cançó mirada i no decidida torna demà;
una decidida no torna.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime

import pytest

from music.models import Album, Artista, Canco

AVUI = datetime.date(2026, 10, 15)


def _canco(nom, *, confianca, verificada=False, activa=True, classe="A"):
    a, _ = Artista.objects.get_or_create(
        nom="Pendent", defaults={"lastfm_nom": "Pendent", "aprovat": True}
    )
    album, _ = Album.objects.get_or_create(
        artista=a, nom="Disc", defaults={"data_llancament": AVUI}
    )
    return Canco.objects.create(
        artista=a,
        album=album,
        nom=nom,
        data_llancament=AVUI - datetime.timedelta(days=10),
        verificada=verificada,
        activa=activa,
        ml_classe=classe,
        ml_confianca=confianca,
    )


def _pendents(monkeypatch, *, target_setmanal):
    from analytics.management.commands import enviar_informe_youtube as cmd

    monkeypatch.setattr(
        cmd,
        "flux_cancons",
        lambda today: {"target_verificacio_setmanal": target_setmanal},
    )
    return cmd.build_context(AVUI)["pendents"]


@pytest.mark.django_db
def test_the_daily_count_comes_from_the_backlog_formula(monkeypatch):
    """Un target setmanal de 75 són 11 al dia, com el 18/09.

    El número no viu al correu: si la fórmula del panell canvia, el
    correu la segueix. I quan el backlog baixa sol (target 0) encara en
    proposa una, perquè la cua no es quede sense mirar.
    """
    for i in range(15):
        _canco(f"Cançó {i}", confianca=i / 100)

    assert len(_pendents(monkeypatch, target_setmanal=75)["files"]) == 11
    assert len(_pendents(monkeypatch, target_setmanal=0)["files"]) == 1


@pytest.mark.django_db
def test_the_most_confident_pending_songs_come_first_and_only_pending_ones(
    monkeypatch,
):
    _canco("Dubtosa", confianca=0.40, classe="B")
    segura = _canco("Segura", confianca=0.99)
    _canco("Ja aprovada", confianca=1.0, verificada=True)
    _canco("Desactivada", confianca=1.0, activa=False)
    _canco("Sense nota", confianca=None, classe="")

    p = _pendents(monkeypatch, target_setmanal=21)

    assert [f["titol"] for f in p["files"]] == ["Segura", "Dubtosa", "Sense nota"]
    assert p["resten"] == 3
    # L'enllaç filtra el llistat de l'staff fins a eixa fila.
    assert p["files"][0]["on"] == (
        f"/staff/cancons?q=Segura&artista_pk={segura.artista_id}"
    )


@pytest.mark.django_db
def test_both_renderings_carry_the_block_and_skip_it_when_nothing_is_pending(
    monkeypatch,
):
    from django.template.loader import render_to_string

    from analytics.management.commands import enviar_informe_youtube as cmd

    monkeypatch.setattr(
        cmd, "flux_cancons", lambda today: {"target_verificacio_setmanal": 7}
    )
    ctx = cmd.build_context(AVUI)
    assert "PENDENTS D'APROVAR" not in cmd.render_text(ctx)
    assert "pendents d'aprovar" not in render_to_string(
        "analytics/informe_youtube.html", ctx
    )

    _canco("Única", confianca=0.87)
    ctx = cmd.build_context(AVUI)
    text = cmd.render_text(ctx)
    html = render_to_string("analytics/informe_youtube.html", ctx)
    assert "Única" in text and "ML A 0.87" in text
    assert "Única" in html and "/staff/cancons?q=%C3%9Anica" in html
