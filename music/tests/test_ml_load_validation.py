"""Tests for the ML load-time validation + deploy-coordination guard.

Both defences land in `music.ml` after the 2026-05-23 incident, when a
background `entrenar_model()` triggered by `recalcular_ml_si_cal` wrote
a joblib with 49 features while the freshly-deployed code expected 50.
Every inference fell through to the heuristic fallback for ~1.5 h
because sklearn raised at predict-time and the broad except in
`pre_classificar` swallowed it as a WARNING.

These tests pin the two fixes:

1. `_get_clf()` MUST detect `clf.n_features_in_ != len(FEATURE_NAMES)`
   on (re)load, set `_model_cache["misaligned"]=True`, and expose the
   diagnostic via `model_misaligned()` so /staff/estat + tq-health can
   render a degraded-state banner in real time.

2. `entrenar_model()` MUST refuse to run while `DEPLOY_LOCK_PATH`
   exists (tq-deploy mid-run), to keep the next joblib write from
   landing against a half-updated codebase.
"""

# Spec: docs/ops/runbook.md (Inserir features ML noves: SEMPRE al final
# de FEATURE_NAMES)

from unittest.mock import patch

import pytest

from music import ml


@pytest.fixture(autouse=True)
def _reset_model_cache():
    """Each test gets a clean cache so flags from a prior run don't
    leak. We restore the original dict shape on teardown."""
    original = ml._model_cache.copy()
    ml._model_cache.update(
        {
            "tfidf": None,
            "tfidf_mtime": 0,
            "clf": None,
            "clf_mtime": 0,
            "misaligned": False,
            "misaligned_msg": "",
        }
    )
    yield
    ml._model_cache.clear()
    ml._model_cache.update(original)


class _StubClf:
    """Minimal RF stand-in. We only need `n_features_in_` for the
    validation; `_get_clf()` doesn't call any predict path."""

    def __init__(self, n_features):
        self.n_features_in_ = n_features


def test_get_clf_flags_misalignment_when_model_has_fewer_features(tmp_path, caplog):
    """The canonical 2026-05-23 scenario: joblib trained with 49
    features, code expects 50. The load MUST flip the misaligned
    flag and log at ERROR."""
    fake_model = tmp_path / "ml_model.joblib"
    fake_model.write_bytes(b"sentinel")  # exists() + stat() need a real file

    expected = len(ml.FEATURE_NAMES)
    stub = _StubClf(n_features=expected - 1)

    with (
        patch.object(ml, "MODEL_PATH", fake_model),
        patch("joblib.load", return_value=stub),
        caplog.at_level("ERROR", logger=ml.logger.name),
    ):
        clf = ml._get_clf()

    assert clf is stub
    assert ml._model_cache["misaligned"] is True
    assert str(expected - 1) in ml._model_cache["misaligned_msg"]
    assert str(expected) in ml._model_cache["misaligned_msg"]

    info = ml.model_misaligned()
    assert info is not None
    assert info["expected_features"] == expected
    assert info["model_features"] == expected - 1
    assert "MISALIGNED" in caplog.text


def test_get_clf_clears_flag_when_model_matches(tmp_path):
    """A subsequent reload with a correctly-shaped model MUST clear
    the misaligned flag — otherwise a one-time bad load would poison
    the dashboard until process restart."""
    fake_model = tmp_path / "ml_model.joblib"
    fake_model.write_bytes(b"sentinel")

    # Prime the cache as if a previous misaligned load happened.
    ml._model_cache["misaligned"] = True
    ml._model_cache["misaligned_msg"] = "stale"
    ml._model_cache["clf_mtime"] = 0  # force reload path

    good_stub = _StubClf(n_features=len(ml.FEATURE_NAMES))

    with (
        patch.object(ml, "MODEL_PATH", fake_model),
        patch("joblib.load", return_value=good_stub),
    ):
        ml._get_clf()

    assert ml._model_cache["misaligned"] is False
    assert ml._model_cache["misaligned_msg"] == ""
    assert ml.model_misaligned() is None


def test_model_misaligned_returns_none_when_healthy():
    """No load, no flag, no panel banner."""
    assert ml.model_misaligned() is None


@pytest.mark.django_db
def test_entrenar_model_refuses_during_deploy(caplog):
    """The deploy guard: if `DEPLOY_LOCK_PATH` exists, `entrenar_model()`
    MUST bail before touching joblib so the model on disk never reflects
    a half-updated codebase. The retrain will be re-attempted by the
    next `recalcular_ml_si_cal` tick once the deploy completes."""
    with (
        patch.object(ml, "_is_deploy_in_progress", return_value=True),
        patch("joblib.dump") as mock_dump,
        caplog.at_level("WARNING", logger=ml.logger.name),
    ):
        result = ml.entrenar_model()

    assert result is False
    assert mock_dump.call_count == 0
    assert "deploy in progress" in caplog.text
