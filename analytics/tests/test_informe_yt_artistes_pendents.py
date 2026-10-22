"""El correu diari també reparteix els artistes pendents de decidir.

La promesa: cada matí ixen deu artistes pendents, en l'ordre de la
mateixa cua que l'staff veu a `/staff/pendents` (propostes d'usuari,
cançons verificades, afinitat Last.fm), només els que de veres estan
pendents, i cada fila diu si té Deezer ID o MBID perquè sense cap dels
dos no es pot aprovar. Cap estat nou: un artista mirat i no decidit
torna demà.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime

import pytest
from django.contrib.auth import get_user_model

from comptes.models import PropostaArtista
from music.models import Album, Artista, ArtistaDeezer, ArtistaLocalitat, Canco

AVUI = datetime.date(2026, 10, 15)


def _artista(nom, *, pendent=True, aprovat=False, similars=0, mbid=""):
    return Artista.objects.create(
        nom=nom,
        lastfm_nom=nom,
        aprovat=aprovat,
        pendent_review=pendent,
        nb_similars_lastfm=similars,
        musicbrainz_id=mbid or None,
    )


def _verificades(artista, n):
    album = Album.objects.create(artista=artista, nom="Disc", data_llancament=AVUI)
    for i in range(n):
        Canco.objects.create(
            artista=artista,
            album=album,
            nom=f"Cançó {i}",
            data_llancament=AVUI,
            verificada=True,
        )


def _proposta(artista, deezer_id):
    ArtistaDeezer.objects.create(artista=artista, deezer_id=deezer_id)
    usuari, _ = get_user_model().objects.get_or_create(
        username="fan", defaults={"email": "fan@example.com"}
    )
    PropostaArtista.objects.create(
        usuari=usuari, nom=artista.nom, justificacio="x", deezer_ids=[deezer_id]
    )


def _calaix(**kw):
    from analytics.management.commands import enviar_informe_youtube as cmd

    return cmd._artistes_pendents(**kw)


@pytest.mark.django_db
def test_the_staff_queue_order_decides_and_only_pending_artists_come():
    """Propostes manen, després les cançons verificades, després Last.fm.

    És la cua de `/staff/pendents` tal qual: el correu no inventa un
    ordre propi. Els aprovats i els descartats (tombstone,
    `pendent_review=False`) no hi són.
    """
    _artista("Alfa")
    _artista("Delta", similars=50)
    beta = _artista("Beta")
    _verificades(beta, 2)
    gamma = _artista("Gamma", similars=1)
    _proposta(gamma, 4242)
    _artista("Aprovada", aprovat=True, pendent=False, similars=99)
    _artista("Descartada", pendent=False, similars=99)

    ap = _calaix()

    assert [f["titol"] for f in ap["files"]] == ["Gamma", "Beta", "Delta", "Alfa"]
    assert ap["resten"] == 4
    assert ap["files"][0]["propostes"] == 1 and ap["files"][0]["deezer"] is True
    assert ap["files"][1]["verificades"] == 2
    assert ap["files"][2]["similars"] == 50
    # L'enllaç filtra el llistat de l'staff fins a eixa fila.
    assert ap["files"][0]["on"] == "/staff/pendents?q=Gamma"


@pytest.mark.django_db
def test_ten_a_day_and_the_mail_says_how_many_are_left():
    for i in range(12):
        _artista(f"Artista {i:02d}")

    ap = _calaix()

    assert len(ap["files"]) == 10
    assert ap["resten"] == 12


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
    assert "ARTISTES PENDENTS" not in cmd.render_text(ctx)
    assert "artistes pendents de decidir" not in render_to_string(
        "analytics/informe_youtube.html", ctx
    )

    sol = _artista("Únic", mbid="0f3b8a1e-1111-4a2b-9c3d-000000000001")
    ArtistaLocalitat.objects.create(artista=sol, localitat_manual="Perpinyà")
    _artista("Sense ancora")
    ctx = cmd.build_context(AVUI)
    text = cmd.render_text(ctx)
    html = render_to_string("analytics/informe_youtube.html", ctx)
    assert "Únic — Perpinyà (ALT)" in text and "sense Deezer · MBID" in text
    assert "no es pot aprovar sense cap dels dos" in text
    assert "Únic" in html and "/staff/pendents?q=%C3%9Anic" in html
    assert "no es pot aprovar sense cap dels dos" in html
