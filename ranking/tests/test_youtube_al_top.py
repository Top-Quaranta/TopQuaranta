"""YouTube as a second signal source in the ranking.

There is no switch. Whether YouTube counts depends on a checkable fact —
how many days of per-video history exist — read once per chart. A switch
would add a second thing that can be wrong: a day when the data is ready
and the box is unticked, or the reverse.

The shape of the formula matters and was arrived at by measurement:

    senyal = escoltes × pes + visualitzacions

**Multiplying the plays** rather than dividing the views is not
cosmetic. `min_escoltes_top` is an absolute number in Last.fm units, so
dividing views to that scale pushes below the floor exactly the songs the
second source exists to rescue — a song with 400 views and no scrobbles
lands on 2 and is dropped. Measured 2026-08-18: dividing left 857
YouTube-only songs under the floor; multiplying, 393, and those are the
ones with fewer than five views in a week.
"""

from __future__ import annotations

import datetime

import pytest

from music.models import Album, Artista, Canco, Territori
from ranking.algorisme import calcular_top_territori
from ranking.models import ConfiguracioGlobal, SenyalDiari, SenyalYouTube

AVUI = datetime.date.today()
FA_UNA_SETMANA = AVUI - datetime.timedelta(days=7)


@pytest.fixture
def cfg(db):
    c, _ = ConfiguracioGlobal.objects.get_or_create(pk=1)
    return c


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


def _lastfm(canco, delta):
    for data, v in ((FA_UNA_SETMANA, 1000), (AVUI, 1000 + delta)):
        SenyalDiari.objects.create(
            canco=canco, data=data, lastfm_playcount=v, error=False
        )


def _youtube(canco, delta, *, dies=7, detall=True):
    """Two snapshots `dies` apart. `dies` also sets how old the history
    looks, which is what decides whether the source counts at all."""
    base_data = AVUI - datetime.timedelta(days=dies)
    for data, v in ((base_data, 5_000), (AVUI, 5_000 + delta)):
        SenyalYouTube.objects.create(
            canco=canco,
            data=data,
            views=v,
            n_videos=1,
            views_per_video={"v1": v} if detall else {},
            error=False,
        )


def _ids(territori="VAL"):
    return {r["canco_id"] for r in calcular_top_territori(territori)}


# ── When it turns itself on ────────────────────────────────────────


@pytest.mark.django_db
def test_history_younger_than_the_threshold_does_not_count(cfg):
    """Five days of history, threshold seven: the chart is Last.fm only,
    which is what every chart published before 2026-08 was.

    Five and not one on purpose — the weekly delta has its own window
    and refuses a base under four days old. At five it would answer, so
    what this measures is the activation gate and nothing else."""
    muda = _canco("Muda")
    _youtube(muda, 50_000, dies=5)
    assert cfg.youtube_dies_minims == 7
    assert muda.pk not in _ids()


@pytest.mark.django_db
def test_it_turns_itself_on_when_the_history_is_old_enough(cfg):
    """The whole point: the Valencian chart had 30 rows for 40 places
    because Last.fm barely sees Valencian music. Nobody ticks anything —
    the seventh day of history is what changes the answer."""
    muda = _canco("Muda")
    _youtube(muda, 50_000, dies=7)
    assert muda.pk in _ids()


@pytest.mark.django_db
def test_the_threshold_is_the_knob(cfg):
    """The same five-day history counts once we say five days is enough.
    Pinned so the number is known to be live: it is the only dial over
    when this starts, and lowering it widens the extrapolation the
    weekly delta has to do."""
    muda = _canco("Muda")
    _youtube(muda, 50_000, dies=5)
    cfg.youtube_dies_minims = 5
    cfg.save(update_fields=["youtube_dies_minims"])
    assert muda.pk in _ids()


@pytest.mark.django_db
def test_snapshots_without_per_video_detail_do_not_age_the_history(cfg):
    """A week of totals is not a week of usable history.

    A total cannot tell a week of views from a lane arriving — that is
    why the detail exists. Dating the history from rows that could not
    answer the question would turn the gate into a formality.

    The pair is seven days apart, inside the delta's own window, so if
    the gate counted these rows the song would chart. An older pair
    would fall outside that window and the test would pass without the
    gate doing anything."""
    muda = _canco("Muda")
    _youtube(muda, 50_000, dies=7, detall=False)
    assert muda.pk not in _ids()


# ── What the weight decides ────────────────────────────────────────


@pytest.mark.django_db
def test_at_the_default_weight_youtube_does_not_outrank_last_fm(cfg):
    """Measured on real data (2026-08-18): at 1000, YouTube fills the
    empty rows and does not overtake a single song Last.fm already sees.
    That is the "safety net, not a rewrite" the weight is chosen for."""
    escoltada = _canco("Escoltada")
    _lastfm(escoltada, 100)  # 100 escoltes × 1000 = 100.000
    mirada = _canco("Mirada")
    _youtube(mirada, 50_000)  # 50.000 visualitzacions

    ordre = [r["canco_id"] for r in calcular_top_territori("VAL")]
    assert ordre.index(escoltada.pk) < ordre.index(mirada.pk)


@pytest.mark.django_db
def test_the_weight_is_what_decides_the_balance(cfg):
    """Lower the weight enough and the same views do overtake. Pinned so
    the knob is known to be live: it is the editorial dial."""
    escoltada = _canco("Escoltada")
    _lastfm(escoltada, 100)
    mirada = _canco("Mirada")
    _youtube(mirada, 50_000)

    cfg.youtube_pes_escolta = 100  # 100 × 100 = 10.000 < 50.000
    cfg.save(update_fields=["youtube_pes_escolta"])

    ordre = [r["canco_id"] for r in calcular_top_territori("VAL")]
    assert ordre.index(mirada.pk) < ordre.index(escoltada.pk)


# ── What is not a week of views ────────────────────────────────────


@pytest.mark.django_db
def test_a_lane_that_appeared_this_week_does_not_count_as_views(cfg):
    """The guard that took two attempts to get right, now where the
    chart itself reads it. A song that gained a video jumps by that
    video's lifetime count; Andreu Valor went from 140 to 88.450 in a
    night and would have led the Valencian chart on 17 real views."""
    canco = _canco("Carril nou")
    SenyalYouTube.objects.create(
        canco=canco,
        data=FA_UNA_SETMANA,
        views=140,
        n_videos=1,
        views_per_video={"art": 140},
        error=False,
    )
    SenyalYouTube.objects.create(
        canco=canco,
        data=AVUI,
        views=88_450,
        n_videos=4,
        views_per_video={"art": 157, "clip1": 80_000, "clip2": 8_000, "clip3": 293},
        error=False,
    )

    # Només els 17 de l'Art Track compten, i no arriben al terra.
    assert canco.pk not in _ids()


@pytest.mark.django_db
def test_swapping_a_video_does_not_count_either(cfg):
    """`n_videos` is unchanged here, so only the per-video detail can
    catch it (Miquel, 2026-08-18)."""
    canco = _canco("Substitució")
    SenyalYouTube.objects.create(
        canco=canco,
        data=FA_UNA_SETMANA,
        views=1_010,
        n_videos=3,
        views_per_video={"a": 500, "b": 500, "menut": 10},
        error=False,
    )
    SenyalYouTube.objects.create(
        canco=canco,
        data=AVUI,
        views=51_000,
        n_videos=3,
        views_per_video={"a": 500, "b": 500, "gran": 50_000},
        error=False,
    )

    assert canco.pk not in _ids()
