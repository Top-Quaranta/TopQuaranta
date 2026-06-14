"""Guard for the public `entrat_al_top` flag (Slice F3 badge signal)."""

from __future__ import annotations

import datetime

import pytest
from django.test import Client

from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal


def _monday(d):
    return d - datetime.timedelta(days=d.weekday())


def _seed(slug, in_prev):
    a = Artista.objects.create(nom=slug, slug=slug, aprovat=True)
    al = Album.objects.create(nom=f"al-{slug}", slug=f"al-{slug}", artista=a)
    c = Canco.objects.create(
        nom=f"c-{slug}",
        slug=f"c-{slug}",
        artista=a,
        album=al,
        verificada=True,
        activa=True,
    )
    week = _monday(datetime.date(2026, 6, 8))
    prev = week - datetime.timedelta(days=7)
    TopSetmanal.objects.create(
        canco=c, territori="PPCC", setmana=week, posicio=1, score_setmanal=1.0
    )
    if in_prev:
        TopSetmanal.objects.create(
            canco=c, territori="PPCC", setmana=prev, posicio=2, score_setmanal=0.9
        )
    return a


@pytest.mark.django_db
def test_entrat_al_top_true_for_new_entry():
    a = _seed("nou-al-top", in_prev=False)
    r = Client().get(f"/api/v1/artistes/{a.slug}/")
    assert r.status_code == 200
    assert r.json()["entrat_al_top"] is True


@pytest.mark.django_db
def test_entrat_al_top_false_when_already_there():
    a = _seed("ja-hi-era", in_prev=True)
    r = Client().get(f"/api/v1/artistes/{a.slug}/")
    assert r.status_code == 200
    assert r.json()["entrat_al_top"] is False
