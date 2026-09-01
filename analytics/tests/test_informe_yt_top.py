"""The daily YouTube report, active phase: what does YouTube decide.

Since 2026-08-26 the second source counts in the real top, so the mail's
headline is no longer "can the signals be merged" but "how many rows
change and who decides them", computed with the live configuration. The
trap this guards: attributing to YouTube rows that the lower combined
floor let in — the causes must stay separate and sum up.
"""

from __future__ import annotations

import datetime

import pytest

from music.models import Album, Artista, Canco, Territori
from ranking.models import SenyalDiari, SenyalYouTube

AVUI = datetime.date(2026, 8, 17)
FA_UNA_SETMANA = AVUI - datetime.timedelta(days=7)


def _canco(nom, terr="VAL"):
    t, _ = Territori.objects.get_or_create(codi=terr, defaults={"nom": terr})
    a = Artista.objects.create(nom=f"A {nom}", lastfm_nom=f"A {nom}", aprovat=True)
    a.territoris.add(t)
    alb = Album.objects.create(
        artista=a, nom="D", data_llancament=AVUI - datetime.timedelta(days=30)
    )
    return Canco.objects.create(
        artista=a,
        album=alb,
        nom=nom,
        data_llancament=AVUI - datetime.timedelta(days=30),
        verificada=True,
        activa=True,
    )


def _senyal(canco, lfm=None, yt=None):
    for data, mult in ((FA_UNA_SETMANA, 0), (AVUI, 1)):
        if lfm is not None:
            SenyalDiari.objects.create(
                canco=canco, data=data, lastfm_playcount=100 + lfm * mult, error=False
            )
        if yt is not None:
            SenyalYouTube.objects.create(
                canco=canco, data=data, views=1000 + yt * mult, error=False
            )


def _ctx():
    from analytics.management.commands.enviar_informe_youtube import build_context

    return build_context(AVUI)["efecte_top"]


@pytest.mark.django_db
def test_the_report_says_what_youtube_decides_in_the_chart():
    """The useful question with the source live: how many rows change,
    and who decides them. Computed with the live configuration, so
    moving the weight in the panel changes tomorrow's mail."""
    from ranking import senyal_youtube
    from ranking.models import ConfiguracioGlobal

    cfg, _ = ConfiguracioGlobal.objects.get_or_create(pk=1)

    escoltada = _canco("Escoltada")
    _senyal(escoltada, lfm=100)
    muda = _canco("Muda")
    _senyal(muda, yt=50_000)

    e = _ctx()
    # Property asserted: `actiu` and `pes` mirror the live sources of
    # truth (history + `youtube_dies_minims`, `youtube_pes_escolta`) —
    # not whatever today's default happens to be.
    assert e["actiu"] == senyal_youtube.actiu(AVUI, cfg.youtube_dies_minims)
    assert e["pes"] == cfg.youtube_pes_escolta

    val = next(t for t in e["territoris"] if t["codi"] == "VAL")
    assert val["ara"] == 1  # només la que Last.fm veu
    assert val["amb_yt"] == 2  # …i la muda hi entra
    assert val["noves"] == 1
    # Al pes per defecte, les escoltes manen: cap fila decidida per YouTube
    # per damunt d'una que Last.fm ja veu.
    assert val["mana_yt"] == 1  # la muda, que no té escoltes


@pytest.mark.django_db
def test_the_chart_effect_separates_what_youtube_earned_from_what_the_floor_gave():
    """«+11 noves» no vol dir «YouTube n'ha portat onze».

    El terra combinat també deixa entrar cançons que el terra en
    escoltes deixava fora, i eixes no les porta la segona font: les
    porta haver abaixat el llistó. Sense separar-ho, el correu
    s'atribueix un guany que no és seu i la decisió es pren sobre un
    número inflat.
    """
    from ranking.models import ConfiguracioGlobal

    cfg, _ = ConfiguracioGlobal.objects.get_or_create(pk=1)
    cfg.min_escoltes_top = 5
    cfg.youtube_pes_escolta = 1000
    cfg.min_senyal_combinat = 200
    cfg.save()

    # Cap escolta, molt públic a YouTube: només hi entra per la segona font.
    _senyal(_canco("Només YouTube"), yt=50_000)
    # Dues escoltes: 2×1000 = 2000 ≥ 200 (terra combinat) però < 5
    # escoltes (terra vell). Hi entra perquè el terra ha canviat.
    _senyal(_canco("Poques escoltes"), lfm=2)

    val = next(t for t in _ctx()["territoris"] if t["codi"] == "VAL")
    assert val["noves"] == 2
    assert val["noves_yt"] == 1, "compta com a mèrit de YouTube el que no ho és"
    assert val["noves_terra"] == 1, "amaga que el terra ha deixat entrar una fila"
    assert val["noves_ordre"] == 0
    # I la suma ha de quadrar sempre: són causes excloents.
    assert val["noves_yt"] + val["noves_terra"] + val["noves_ordre"] == val["noves"]


@pytest.mark.django_db
def test_a_missing_day_does_not_empty_the_lastfm_week():
    """The Last.fm reference photo is looked up in a window around
    "seven days ago", not on that exact date. Demanding the exact day is
    brittle: one missed cron run would blank the "sense YT" column and
    every row would read as brought in by YouTube."""
    canco = _canco("Amb forat")
    # Reference is 8 days back, not 7 — the cron missed a day.
    SenyalDiari.objects.create(
        canco=canco,
        data=AVUI - datetime.timedelta(days=8),
        lastfm_playcount=100,
        error=False,
    )
    SenyalDiari.objects.create(
        canco=canco, data=AVUI, lastfm_playcount=140, error=False
    )

    val = next(t for t in _ctx()["territoris"] if t["codi"] == "VAL")
    # 40 plays over 8 days rescale to 35 a week — over the floor of 5.
    assert val["ara"] == 1


# ── La plantilla renderitza els dos estats ─────────────────────────
#
# Una errada de sintaxi a la plantilla no peta: es menja la frase i el
# correu arriba dient res. Rendered, not asserted on the dict: el dict
# el sap escriure qualsevol, el que ha d'arribar és el text.


def _render(efecte):
    from django.template.loader import render_to_string

    return render_to_string(
        "analytics/informe_youtube.html",
        {"efecte_top": efecte, "avui": datetime.date(2026, 9, 1)},
    )


def test_the_email_shouts_if_youtube_stops_counting():
    """`actiu` should always be true since 26/08: if one day it is not,
    the per-video history is gone and the mail must say so in red, not
    hide the block."""
    base = {"pes": 1000, "terra": 200, "territoris": []}

    html = _render({**base, "actiu": True})
    assert "Actiu" in html
    assert "Inactiu" not in html

    html = _render({**base, "actiu": False})
    assert "Inactiu" in html and "no compta al top" in html
