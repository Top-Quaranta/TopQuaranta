"""FASE A — SolicitudRevisio + HistorialRevisio.reconsiderada.

Model-level tests only (no API). The full workflow tests land in
`web/tests/test_workflow_sollicituds_revisio.py` once FASE B brings
the endpoints online.
"""

from __future__ import annotations

import pytest

from comptes.models import SolicitudRevisio, Usuari
from music.models import Artista, HistorialRevisio


@pytest.fixture
def artista(db):
    return Artista.objects.create(nom="A", slug="a", aprovat=True)


@pytest.fixture
def gestor(db):
    return Usuari.objects.create_user(username="g", email="g@example.com", password="x")


# ── SolicitudRevisio ────────────────────────────────────────────────


def test_create_with_defaults(db, gestor, artista):
    s = SolicitudRevisio.objects.create(gestor=gestor, artista=artista)
    assert s.estat == SolicitudRevisio.ESTAT_PENDENT
    assert s.pendents_ids == []
    assert s.rebutjades_snapshot == []
    assert s.resolt_at is None
    assert s.resolt_per is None
    assert s.nota_resolucio == ""
    assert s.n_pendents == 0
    assert s.n_rebutjades == 0


def test_str_carries_artista_and_estat(db, gestor, artista):
    s = SolicitudRevisio.objects.create(gestor=gestor, artista=artista)
    txt = str(s)
    assert artista.nom in txt
    assert "pendent" in txt
    assert f"#{s.pk}" in txt


def test_ordering_desc_created_at(db, gestor, artista):
    a = SolicitudRevisio.objects.create(gestor=gestor, artista=artista)
    b = SolicitudRevisio.objects.create(gestor=gestor, artista=artista)
    rows = list(SolicitudRevisio.objects.all())
    assert rows[0] == b
    assert rows[1] == a


def test_estat_choices_are_three(db):
    keys = [k for k, _ in SolicitudRevisio.ESTAT_CHOICES]
    assert keys == ["pendent", "revisada", "resolta"]


def test_workbench_query_pendent_default(db, gestor, artista):
    """Workbench landing page filters `estat=pendent`, ordered desc."""
    p = SolicitudRevisio.objects.create(gestor=gestor, artista=artista)
    r = SolicitudRevisio.objects.create(gestor=gestor, artista=artista)
    r.estat = SolicitudRevisio.ESTAT_RESOLTA
    r.save(update_fields=["estat"])
    qs = SolicitudRevisio.objects.filter(estat="pendent").order_by("-created_at")
    assert list(qs) == [p]


def test_n_pendents_and_n_rebutjades_count(db, gestor, artista):
    s = SolicitudRevisio.objects.create(
        gestor=gestor,
        artista=artista,
        pendents_ids=[10, 11, 12],
        rebutjades_snapshot=[{"historial_pk": 1}, {"historial_pk": 2}],
    )
    assert s.n_pendents == 3
    assert s.n_rebutjades == 2


# ── HistorialRevisio.reconsiderada ──────────────────────────────────


def test_reconsiderada_default_false(db):
    h = HistorialRevisio.objects.create(
        canco_nom="x",
        artista_nom="y",
        decisio="rebutjada",
        motiu="no_catala",
    )
    assert h.reconsiderada is False


def test_reconsiderada_can_be_flipped(db):
    h = HistorialRevisio.objects.create(
        canco_nom="x",
        artista_nom="y",
        decisio="rebutjada",
        motiu="no_catala",
    )
    h.reconsiderada = True
    h.save(update_fields=["reconsiderada"])
    h.refresh_from_db()
    assert h.reconsiderada is True


def test_reconsiderada_filter_used_by_cron(db):
    """Sentinel for FASE D: the ingestion cron will query
    `decisio="rebutjada", reconsiderada=False`. Make sure both filters
    are honoured before the cron diff lands."""
    HistorialRevisio.objects.create(
        canco_nom="a",
        artista_nom="x",
        decisio="rebutjada",
        motiu="no_catala",
        reconsiderada=False,
    )
    HistorialRevisio.objects.create(
        canco_nom="b",
        artista_nom="x",
        decisio="rebutjada",
        motiu="no_catala",
        reconsiderada=True,
    )
    HistorialRevisio.objects.create(
        canco_nom="c",
        artista_nom="x",
        decisio="aprovada",
        motiu="ok",
    )
    n_blocking = HistorialRevisio.objects.filter(
        decisio="rebutjada", reconsiderada=False
    ).count()
    assert n_blocking == 1
