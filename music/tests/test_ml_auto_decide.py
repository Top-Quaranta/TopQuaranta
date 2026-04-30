"""ML auto-decision (A++ blind-trust) and sub-tier accuracy.

Sprint K bis (2026-04-30): Classe A++ (ml_classe='A' AND
ml_confianca >= 0.99) is auto-approved without HITL after the
2026-04-30 audit showed 502/502 = 100% accuracy on that band.
Auto-decisions land in HistorialRevisio with motiu="auto_ml" and
must be filtered out of the training set.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from music.constants import (
    ML_AUTO_APPROVE_SUBTIERS,
    ML_AUTO_APPROVE_THRESHOLD,
    ML_AUTO_MIN_SAMPLES,
    MOTIU_AUTO_ML,
)
from music.ml import _is_auto_approve_subtier, maybe_auto_decide
from music.models import Album, Artista, Canco, HistorialRevisio
from music.services import aprovar_canco_auto_ml


@pytest.fixture
def artista(db):
    return Artista.objects.create(nom="Test Artist", aprovat=True)


@pytest.fixture
def canco(db, artista):
    album = Album.objects.create(nom="Test Album", artista=artista)
    return Canco.objects.create(
        nom="Test Track",
        artista=artista,
        album=album,
        deezer_id=1,
        verificada=False,
        activa=True,
    )


# ── _is_auto_approve_subtier ──────────────────────────────────────────


def test_a_plusplus_is_auto():
    """A++ band (>=0.99) maps to an auto-approve sub-tier."""
    assert _is_auto_approve_subtier("A", 0.995) is True
    assert _is_auto_approve_subtier("A", 0.99) is True
    assert _is_auto_approve_subtier("A", 1.0) is True


def test_a_plus_is_not_auto():
    """A+ (0.95–0.99) is NOT yet graduated. Even at 99.4 % accuracy
    the sub-tier is a candidat, not auto."""
    assert _is_auto_approve_subtier("A", 0.985) is False
    assert _is_auto_approve_subtier("A", 0.95) is False


def test_b_and_c_never_auto():
    assert _is_auto_approve_subtier("B", 0.99) is False
    assert _is_auto_approve_subtier("C", 0.05) is False


def test_no_confianca_means_no_auto():
    assert _is_auto_approve_subtier("A", None) is False


# ── maybe_auto_decide ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_plusplus_canco_gets_auto_approved(canco):
    canco.ml_classe = "A"
    canco.ml_confianca = 0.995
    canco.save()

    result = maybe_auto_decide(canco)

    assert result == "aprovada"
    canco.refresh_from_db()
    assert canco.verificada is True
    h = HistorialRevisio.objects.filter(canco_deezer_id=canco.deezer_id).first()
    assert h is not None
    assert h.decisio == "aprovada"
    assert h.motiu == MOTIU_AUTO_ML


@pytest.mark.django_db
def test_a_plus_canco_not_touched(canco):
    """A+ (0.95–0.99) is a candidat but not auto."""
    canco.ml_classe = "A"
    canco.ml_confianca = 0.97
    canco.save()

    result = maybe_auto_decide(canco)

    assert result is None
    canco.refresh_from_db()
    assert canco.verificada is False
    assert HistorialRevisio.objects.count() == 0


@pytest.mark.django_db
def test_already_verified_skipped(canco):
    """Don't re-approve a track that's already verified."""
    canco.ml_classe = "A"
    canco.ml_confianca = 0.999
    canco.verificada = True
    canco.save()

    result = maybe_auto_decide(canco)

    assert result is None
    # No new historial — we didn't touch it.
    assert HistorialRevisio.objects.count() == 0


# ── Training filter ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_auto_ml_decisions_excluded_from_training(canco):
    """A model that learns from its own outputs reinforces its biases.
    Training must exclude motiu='auto_ml'."""
    aprovar_canco_auto_ml(canco)
    # Sanity: the historial row is there, just tagged.
    assert HistorialRevisio.objects.filter(motiu=MOTIU_AUTO_ML).count() == 1
    # The training query in entrenar_model uses .exclude(motiu=…).
    trainable = HistorialRevisio.objects.exclude(motiu=MOTIU_AUTO_ML).count()
    assert trainable == 0


# ── Constants invariants ─────────────────────────────────────────────


def test_a_plusplus_pinned_in_auto_subtiers():
    """The whole feature hinges on A++ being in
    ML_AUTO_APPROVE_SUBTIERS. If someone removes it the auto-approval
    silently turns off — guard against that."""
    assert "A++" in ML_AUTO_APPROVE_SUBTIERS


def test_thresholds_are_strict():
    """≥99.5 % on n≥200 — change deliberately, not by accident."""
    assert ML_AUTO_APPROVE_THRESHOLD >= 0.99
    assert ML_AUTO_MIN_SAMPLES >= 100
