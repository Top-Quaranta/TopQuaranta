"""Re-issue guard: a single re-released inside a later EP/album.

Lives in its own module because the older ranking test files are gated
behind a PostgreSQL check that never passes (test settings are SQLite),
so a test written there would never run — which is how the first cut of
this guard shipped reading the candidate pool instead of the catalogue
and changed nothing.
"""

from datetime import date, timedelta

import pytest

from ranking.algorisme import calcular_top_territori
from ranking.models import ConfiguracioGlobal, SenyalDiari


@pytest.mark.django_db
def test_reissue_does_not_bank_the_originals_lifetime_playcount():
    """The original is normally OUTSIDE the 365-day pool — which is
    exactly why the re-issue reads as new. The guard must look at the
    artist's whole catalogue, not the candidate pool (first cut of it
    read the pool and caught nothing: Bocc stayed #1 after recalcular).
    """
    from music.models import Album, Artista, Canco, Territori

    ConfiguracioGlobal.objects.create(pk=1)
    cat, _ = Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Catalunya"})
    a = Artista.objects.create(nom="Bocc", lastfm_nom="Bocc", aprovat=True)
    a.territoris.add(cat)
    today = date.today()

    # Original: 15 months old → outside DIES_CADUCITAT, not a candidate.
    vell = Album.objects.create(
        artista=a, nom="Promo", data_llancament=today - timedelta(days=470)
    )
    Canco.objects.create(
        artista=a,
        album=vell,
        nom="Ànima d'Acer",
        data_llancament=today - timedelta(days=470),
        verificada=True,
        activa=True,
    )
    # Re-issue, 4 days ago, own ISRC — Last.fm answers the original's total.
    nou = Album.objects.create(
        artista=a, nom="Ànima D'Acer", data_llancament=today - timedelta(days=4)
    )
    reed = Canco.objects.create(
        artista=a,
        album=nou,
        nom="Ànima D'Acer",
        data_llancament=today - timedelta(days=4),
        verificada=True,
        activa=True,
    )
    for off in (2, 1, 0):
        SenyalDiari.objects.create(
            canco=reed,
            data=today - timedelta(days=off),
            lastfm_playcount=966,
            lastfm_listeners=286,
            error=False,
        )

    files = {r["canco"].pk: r for r in calcular_top_territori("CAT")}
    assert files.get(reed.pk, {}).get("weekly_plays", 0) == 0


@pytest.mark.django_db
def test_recalculating_the_same_week_is_idempotent():
    """Running the ranking twice for the same week must give the same
    scores. It did not: both the past-top penalty and the soft-cap knee
    read TopSetmanal without excluding the week being computed, so the
    second pass penalised each song for the position the first pass had
    just awarded it. `calcular_top` saves every territori BEFORE PPCC
    aggregates, and PPCC re-runs each source territori — so this fired on
    every single run, inverting the published CAT order inside PPCC
    (2026-08-15: Bocc #1 CAT but Rosalía #1 PPCC, both CAT-only acts).
    """
    from music.models import Album, Artista, Canco, Territori

    from ranking.models import TopSetmanal

    ConfiguracioGlobal.objects.create(pk=1)
    cat, _ = Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Catalunya"})
    today = date.today()
    setmana = today - timedelta(days=today.weekday())

    for nom, plays in (("Gran", 13000), ("Menut", 900)):
        a = Artista.objects.create(nom=nom, lastfm_nom=nom, aprovat=True)
        a.territoris.add(cat)
        alb = Album.objects.create(
            artista=a, nom=nom, data_llancament=today - timedelta(days=120)
        )
        c = Canco.objects.create(
            artista=a,
            album=alb,
            nom=f"Cançó {nom}",
            data_llancament=today - timedelta(days=120),
            verificada=True,
            activa=True,
        )
        for off, mult in ((8, 0), (0, 1)):
            SenyalDiari.objects.create(
                canco=c,
                data=today - timedelta(days=off),
                lastfm_playcount=plays * mult,
                lastfm_listeners=10,
                error=False,
            )

    primera = calcular_top_territori("CAT")
    # Persist it, exactly like `calcular_top` does before PPCC runs.
    for r in primera:
        TopSetmanal.objects.create(
            canco_id=r["canco_id"],
            territori="CAT",
            setmana=setmana,
            posicio=r["posicio"],
            score_setmanal=r["score_setmanal"] or 0.0,
            weekly_plays=r.get("weekly_plays") or 0,
            algorithm_version="v2.0",
        )

    segona = calcular_top_territori("CAT")
    assert [(r["canco_id"], r["score_setmanal"]) for r in segona] == [
        (r["canco_id"], r["score_setmanal"]) for r in primera
    ]
