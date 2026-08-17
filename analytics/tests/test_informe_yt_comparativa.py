"""The daily YouTube report answers one question now: can the two
signals be combined?

Discovery finished the catalogue on 2026-08-17 ("queden per provar: 0"),
so progress bars about it report a settled fact. What is still open is
whether a YouTube view can be converted into a Last.fm play, and how many
songs that would rescue — the reason the second source was built at all
(the Valencian top had 22 rows instead of 40).

The trap this guards: a ratio computed from a handful of pairs looks like
a number and is noise. The report must say so rather than print it flat.
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

    return build_context(AVUI)["comparativa"]


@pytest.mark.django_db
def test_a_song_moving_on_both_sources_is_comparable():
    _senyal(_canco("Totes dues"), lfm=10, yt=2000)
    c = _ctx()
    assert c["comparables"] == 1
    assert c["factor"]["mediana"] == 200  # 2000 / 10


@pytest.mark.django_db
def test_a_thin_sample_is_flagged_as_not_trustworthy():
    """One pair produces a median. Printing it flat would invite a
    decision it cannot support."""
    _senyal(_canco("Sola"), lfm=10, yt=2000)
    f = _ctx()["factor"]
    assert f["n"] == 1
    assert f["prou"] is False and f["indici"] is False


@pytest.mark.django_db
def test_songs_only_youtube_sees_are_counted_as_the_gain():
    """The whole point: songs that cannot enter the top today because
    Last.fm is silent about them."""
    _senyal(_canco("Muda a Last.fm"), yt=5000)  # cap senyal de Last.fm
    _senyal(_canco("Sonora"), lfm=50, yt=9000)
    c = _ctx()
    assert c["noves"] == 1
    val = next(g for g in c["guany"] if g["codi"] == "VAL")
    assert val["noves"] == 1 and val["lastfm"] == 1


@pytest.mark.django_db
def test_barely_moving_songs_do_not_enter_the_ratio():
    """1 play against 300 views yields a factor of 300 that means
    nothing. Below the floor a song is not comparable."""
    _senyal(_canco("Quieta"), lfm=1, yt=300)
    c = _ctx()
    assert c["comparables"] == 0
    assert c["factor"] is None


@pytest.mark.django_db
def test_a_song_without_a_week_of_snapshots_cannot_be_compared():
    """No photo from seven days ago, no weekly delta — and the report
    says how much of the catalogue is in that state, because that is
    what changes day to day right now."""
    c = _canco("Acabada de connectar")
    SenyalYouTube.objects.create(canco=c, data=AVUI, views=5000, error=False)
    ctx = _ctx()
    assert ctx["comparables"] == 0
    assert ctx["amb_avui"] == 1 and ctx["amb_setmana"] == 0
    assert ctx["pct_setmana"] == 0


@pytest.mark.django_db
def test_a_missing_day_does_not_empty_the_comparison():
    """The reference photo is looked up in a window around "seven days
    ago", not on that exact date. Demanding the exact day is brittle: one
    missed cron run would report "no comparable songs" when what is
    missing is a photograph, and the report would look like a finding.
    """
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
    SenyalYouTube.objects.create(
        canco=canco, data=AVUI - datetime.timedelta(days=8), views=1000, error=False
    )
    SenyalYouTube.objects.create(canco=canco, data=AVUI, views=9000, error=False)

    c = _ctx()
    assert c["comparables"] == 1
    # 8 days rescaled to 7: 8000 views / 40 plays = 200, unchanged by the
    # rescale because both sides get the same factor.
    assert c["factor"]["mediana"] == 200


@pytest.mark.django_db
def test_a_reference_far_outside_the_window_is_refused():
    """Twenty days back is not "a week ago". Rescaling that far would
    invent a weekly figure out of a monthly one."""
    canco = _canco("Massa vell")
    SenyalYouTube.objects.create(
        canco=canco, data=AVUI - datetime.timedelta(days=20), views=1000, error=False
    )
    SenyalYouTube.objects.create(canco=canco, data=AVUI, views=90000, error=False)
    _senyal_lfm = SenyalDiari.objects.create(
        canco=canco, data=AVUI, lastfm_playcount=100, error=False
    )
    assert _ctx()["mou_yt"] == 0
    del _senyal_lfm
