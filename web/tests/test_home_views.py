"""Smoke + semantics tests for the HomePage feed endpoints.

`/api/v1/stats/`, `/api/v1/top/canco-destacada/`,
`/api/v1/artistes/destacat/`, `/api/v1/artistes/descoberta/`. Each
must be anonymous-friendly and respond with the expected shape.
"""

import datetime

import pytest
from rest_framework.test import APIClient

from comptes.models import UserArtista
from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal


@pytest.fixture(autouse=True)
def _clear_pagecache():
    """LocMem `pagecache` persists across tests in-process. Clear it
    so cached responses from earlier tests don't bleed into later
    ones (each test mutates the same URL space). Anonymous-only
    cache, so this is safe."""
    from django.core.cache import caches

    caches["pagecache"].clear()
    yield
    caches["pagecache"].clear()


@pytest.fixture
def anon():
    return APIClient()


def _mk_artista(nom, slug, **extra):
    return Artista.objects.create(nom=nom, slug=slug, aprovat=True, **extra)


def _mk_canco(nom, slug, artista, album=None):
    if album is None:
        # Canco.album is NOT NULL — give it a stub album when callers
        # don't care about album semantics.
        album = Album.objects.create(
            nom=f"stub-{slug}",
            slug=f"stub-{slug}",
            artista=artista,
        )
    return Canco.objects.create(
        nom=nom,
        slug=slug,
        artista=artista,
        album=album,
        verificada=True,
        activa=True,
    )


def _mk_album(nom, slug, artista, with_image=True, **extra):
    return Album.objects.create(
        nom=nom,
        slug=slug,
        artista=artista,
        imatge_url="https://example.com/cover.jpg" if with_image else "",
        **extra,
    )


def test_stats_anon_basic_shape(db, anon):
    a = _mk_artista("Test One", "test-one")
    _mk_canco("c1", "test-one-c1", a)
    r = anon.get("/api/v1/stats/")
    assert r.status_code == 200
    body = r.json()
    for k in (
        "cancons_verificades",
        "artistes_aprovats",
        "territoris_actius",
        "cancons_noves_setmana",
    ):
        assert k in body, k
    assert body["cancons_verificades"] >= 1
    assert body["artistes_aprovats"] >= 1


def test_canco_destacada_falls_back_to_pos1_when_no_prev(db, anon):
    """First-week edge: with one PPCC week stored, the endpoint
    must return the #1 (delta=null) instead of empty."""
    a = _mk_artista("DA", "da")
    al = _mk_album("AlbA", "alb-a", a)
    c = _mk_canco("songA", "song-a", a, album=al)
    setmana = datetime.date(2026, 4, 13)
    TopSetmanal.objects.create(
        canco=c,
        territori="PPCC",
        setmana=setmana,
        posicio=1,
        score_setmanal=100.0,
    )
    r = anon.get("/api/v1/top/canco-destacada/")
    assert r.status_code == 200
    e = r.json()["entry"]
    assert e is not None
    assert e["posicio"] == 1
    assert e["delta"] is None


def test_canco_destacada_picks_biggest_climber(db, anon):
    """With two weeks, the biggest position improvement wins."""
    a = _mk_artista("DA", "da")
    al = _mk_album("AlbA", "alb-a", a)
    big = _mk_canco("big", "big", a, album=al)
    flat = _mk_canco("flat", "flat", a, album=al)
    prev = datetime.date(2026, 4, 6)
    cur = datetime.date(2026, 4, 13)
    # Week prev: big at #20, flat at #5.
    TopSetmanal.objects.create(
        canco=big, territori="PPCC", setmana=prev, posicio=20, score_setmanal=10
    )
    TopSetmanal.objects.create(
        canco=flat, territori="PPCC", setmana=prev, posicio=5, score_setmanal=50
    )
    # Week cur: big at #2 (climbed 18), flat at #5 (no change).
    TopSetmanal.objects.create(
        canco=big, territori="PPCC", setmana=cur, posicio=2, score_setmanal=80
    )
    TopSetmanal.objects.create(
        canco=flat, territori="PPCC", setmana=cur, posicio=5, score_setmanal=50
    )
    r = anon.get("/api/v1/top/canco-destacada/")
    assert r.status_code == 200
    e = r.json()["entry"]
    assert e["canco"]["slug"] == "big"
    assert e["delta"] == 18


def test_descoberta_filters_to_distinct_territoris(db, anon):
    """The diversity rule prefers one artist per primary territori."""
    from music.models import Territori

    cat = Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Catalunya"})[0]
    val = Territori.objects.get_or_create(
        codi="VAL", defaults={"nom": "País Valencià"}
    )[0]
    bal = Territori.objects.get_or_create(
        codi="BAL", defaults={"nom": "Illes Balears"}
    )[0]

    def _mk(nom, slug, terr):
        a = _mk_artista(nom, slug)
        a.territoris.set([terr])
        al = _mk_album(
            f"A-{slug}", f"a-{slug}", a, data_llancament=datetime.date.today()
        )
        _mk_canco(f"c-{slug}", f"c-{slug}", a, album=al)
        return a

    _mk("CAT1", "cat1", cat)
    _mk("CAT2", "cat2", cat)
    _mk("VAL1", "val1", val)
    _mk("BAL1", "bal1", bal)

    r = anon.get("/api/v1/artistes/descoberta/?limit=3")
    assert r.status_code == 200
    items = r.json()["results"]
    assert len(items) == 3
    # All three territoris should appear before any duplicate.
    primary_terrs = [it["territoris"][0] for it in items]
    assert set(primary_terrs) == {"CAT", "VAL", "BAL"}


def test_artista_destacat_requires_verified_manager(db, anon, django_user_model):
    """Without any UserArtista.verificat=True, endpoint returns null."""
    a = _mk_artista("X", "x")
    al = _mk_album("AlbX", "alb-x", a)
    c = _mk_canco("xc", "xc", a, album=al)
    prev = datetime.date(2026, 4, 6)
    cur = datetime.date(2026, 4, 13)
    TopSetmanal.objects.create(
        canco=c, territori="PPCC", setmana=prev, posicio=10, score_setmanal=10
    )
    TopSetmanal.objects.create(
        canco=c, territori="PPCC", setmana=cur, posicio=2, score_setmanal=80
    )
    r = anon.get("/api/v1/artistes/destacat/")
    assert r.status_code == 200
    assert r.json()["artista"] is None

    # Add a verified manager → now it surfaces. Clear pagecache
    # between the two GETs so the second hit doesn't replay the
    # cached null body.
    from django.core.cache import caches

    caches["pagecache"].clear()
    u = django_user_model.objects.create_user(
        username="u", email="u@e.com", password="x"
    )
    UserArtista.objects.create(
        usuari=u,
        artista=a,
        sollicitud_text="x" * 25,
        verificat=True,
        estat=UserArtista.ESTAT_APROVAT,
    )
    r = anon.get("/api/v1/artistes/destacat/")
    body = r.json()
    assert body["artista"] is not None
    assert body["artista"]["slug"] == "x"
    assert body["delta"] == 8


def test_top_oficial_only_returns_empty_when_no_weekly(db, anon):
    """`oficial=true` must NOT fall back to TopProvisional."""
    r = anon.get("/api/v1/top/?territori=PPCC&oficial=true")
    assert r.status_code == 200
    assert r.json()["entries"] == []


def test_top_includes_prev_next_setmana(db, anon):
    a = _mk_artista("Y", "y")
    c = _mk_canco("yc", "yc", a)
    s1 = datetime.date(2026, 3, 30)
    s2 = datetime.date(2026, 4, 6)
    s3 = datetime.date(2026, 4, 13)
    for s in (s1, s2, s3):
        TopSetmanal.objects.create(
            canco=c, territori="PPCC", setmana=s, posicio=1, score_setmanal=10
        )
    # Middle week: both prev and next present.
    r = anon.get("/api/v1/top/?territori=PPCC&setmana=2026-04-06")
    body = r.json()
    assert body["prev_setmana"] == "2026-03-30"
    assert body["next_setmana"] == "2026-04-13"
    # First week: prev=None.
    r = anon.get("/api/v1/top/?territori=PPCC&setmana=2026-03-30")
    assert r.json()["prev_setmana"] is None
    # Latest week: next=None.
    r = anon.get("/api/v1/top/?territori=PPCC&setmana=2026-04-13")
    assert r.json()["next_setmana"] is None
