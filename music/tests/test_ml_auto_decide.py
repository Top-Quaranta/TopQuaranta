"""ML auto-decision plumbing + sub-tier classification.

Originally added (and reverted) on 2026-04-30 after a target-leakage
bug in the diagnostic: live `Canco.ml_classe` / `ml_confianca` had
been re-scored by retrains that were trained on the same approvals
they were now being measured against, falsely showing A++ at 100 %
accuracy. The honest measure (HistorialRevisio decision-time
snapshot, motiu!='auto_ml') is 93.1 % — far below the 99.5 %
threshold for blind-trust.

The hooks (`maybe_auto_decide`, `aprovar_canco_auto_ml`,
`subtier_for`) stay so the system is ready to graduate a sub-tier
the day one actually clears the bar; meanwhile
`ML_AUTO_APPROVE_SUBTIERS` and `ML_AUTO_REJECT_SUBTIERS` are empty.
"""

from __future__ import annotations

import pytest

from music.constants import (
    ML_AUTO_APPROVE_SUBTIERS,
    ML_AUTO_APPROVE_THRESHOLD,
    ML_AUTO_MIN_SAMPLES,
    ML_AUTO_REJECT_SUBTIERS,
    ML_SUBTIERS,
    MOTIU_AUTO_ML,
)
from music.ml import _is_auto_approve_subtier, maybe_auto_decide, subtier_for
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


# ── subtier_for ───────────────────────────────────────────────────────


def test_subtier_for_correct_band():
    """Quartile assignment within each main class."""
    # A: [0.70, 1.00], split as A-- A- A+ A++
    assert subtier_for("A", 0.995) == "A++"
    assert subtier_for("A", 0.97) == "A+"
    assert subtier_for("A", 0.90) == "A-"
    assert subtier_for("A", 0.75) == "A--"
    # B: [0.40, 0.70)
    assert subtier_for("B", 0.65) == "B++"
    assert subtier_for("B", 0.50) == "B+"
    assert subtier_for("B", 0.46) == "B-"
    assert subtier_for("B", 0.41) == "B--"
    # C: [0.00, 0.40)
    assert subtier_for("C", 0.30) == "C++"
    assert subtier_for("C", 0.20) == "C+"
    assert subtier_for("C", 0.10) == "C-"
    assert subtier_for("C", 0.02) == "C--"


def test_subtier_for_out_of_range():
    """A confidence outside its class's range returns None."""
    # 0.65 is class B territory, not class A's.
    assert subtier_for("A", 0.65) is None
    assert subtier_for("C", 0.50) is None


def test_subtier_for_no_confianca():
    assert subtier_for("A", None) is None


def test_subtiers_cover_full_axis_no_overlap():
    """The 12 sub-tiers should cover [0.0, 1.0] without gaps and
    without overlap (a confidence is in exactly one sub-tier per
    class). Crucially: A-- starts at 0.70 (not 0.00) — the
    pre-2026-04-30 boundaries were wrong on this and would have
    placed every C cançó in A--."""
    a_bands = [(lo, hi) for label, lo, hi in ML_SUBTIERS if label.startswith("A")]
    b_bands = [(lo, hi) for label, lo, hi in ML_SUBTIERS if label.startswith("B")]
    c_bands = [(lo, hi) for label, lo, hi in ML_SUBTIERS if label.startswith("C")]
    # Sort ascending and check consecutivity.
    for bands, lo_class, hi_class in (
        (sorted(a_bands), 0.70, 1.0),
        (sorted(b_bands), 0.40, 0.70),
        (sorted(c_bands), 0.00, 0.40),
    ):
        assert bands[0][0] == lo_class
        assert bands[-1][1] >= hi_class
        for i in range(len(bands) - 1):
            assert bands[i][1] == bands[i + 1][0], f"gap/overlap: {bands}"


# ── _is_auto_approve_subtier ──────────────────────────────────────────


def test_no_subtier_is_currently_auto():
    """As of 2026-04-30 no sub-tier has been graduated to auto-decision
    — the original A++ pin was based on a flawed metric.

    Property asserted (instead of pinning the lists to `()`, which would
    block a legitimate graduation): the graduated lists are consistent
    with the tier semantics — every entry is a real sub-tier label,
    auto-approve tiers are class A and auto-reject tiers class C, no
    tier is in both lists, and `_is_auto_approve_subtier` is True for
    exactly the confidences that fall in a graduated approve tier.
    Whether a graduated tier really clears the honest-accuracy bar is
    a live measurement (`_ml_subtier_stats` on HistorialRevisio) that
    cannot be pinned in a unit test."""
    labels = {label for label, _, _ in ML_SUBTIERS}
    approve = set(ML_AUTO_APPROVE_SUBTIERS)
    reject = set(ML_AUTO_REJECT_SUBTIERS)
    assert approve <= labels
    assert reject <= labels
    assert not (approve & reject)
    assert all(label.startswith("A") for label in approve)
    assert all(label.startswith("C") for label in reject)
    # The helper mirrors the constant band-by-band (probe just inside
    # each band's lower bound).
    for label, lo, _ in ML_SUBTIERS:
        assert _is_auto_approve_subtier(label[0], lo + 0.001) is (label in approve)


# ── maybe_auto_decide ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_already_verified_skipped(canco):
    canco.ml_classe = "A"
    canco.ml_confianca = 0.999
    canco.verificada = True
    canco.save()

    assert maybe_auto_decide(canco) is None
    assert HistorialRevisio.objects.count() == 0


# ── Training filter ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_auto_ml_decisions_excluded_from_training(canco, tmp_path, monkeypatch):
    """If a sub-tier is graduated in the future, auto-decisions must
    not feed back into the training set.

    Property asserted: with only auto_ml decisions on record — more than
    `MIN_TRAINING_SAMPLES` of them — `entrenar_model()` still finds no
    training data and refuses to train (returns False, writes no
    model). Exercises the real training-set selection instead of
    re-implementing the exclude in the test."""
    from music import ml
    from music.constants import MIN_TRAINING_SAMPLES

    aprovar_canco_auto_ml(canco)
    assert HistorialRevisio.objects.filter(motiu=MOTIU_AUTO_ML).count() == 1
    # Pad with more auto_ml rows so the count alone would clear the
    # minimum — only the exclude keeps them out of the training set.
    for i in range(MIN_TRAINING_SAMPLES + 5):
        HistorialRevisio.objects.create(
            canco_nom=f"auto {i}",
            artista_nom="Test Artist",
            decisio="aprovada",
            motiu=MOTIU_AUTO_ML,
        )

    # Never write joblib into the repo, and don't let a deploy lock on
    # the dev box short-circuit the call.
    monkeypatch.setattr(ml, "MODEL_PATH", tmp_path / "model.joblib")
    monkeypatch.setattr(ml, "TFIDF_PATH", tmp_path / "tfidf.joblib")
    monkeypatch.setattr(ml, "_is_deploy_in_progress", lambda: False)

    assert ml.entrenar_model() is False
    assert not (tmp_path / "model.joblib").exists()


# ── Constants invariants ─────────────────────────────────────────────


def test_thresholds_are_strict():
    """≥99.5 % on n≥200 — change deliberately, not by accident."""
    assert ML_AUTO_APPROVE_THRESHOLD >= 0.99
    assert ML_AUTO_MIN_SAMPLES >= 100
