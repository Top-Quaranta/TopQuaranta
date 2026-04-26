"""
Track verification ML classifier.

Pipeline:
1. Feature extraction (_build_features): 19 structured features + 200 TF-IDF
   char n-gram features from the track title. Structured features include ISRC
   country, Deezer metadata (fans, albums, name similarity), artist rejection
   history, ISRC registrant rejection history, and artist approval status.
2. Classification: Random Forest (100 estimators, balanced class weights) trained
   on HistorialRevisio approve/reject decisions. Falls back to hand-tuned
   heuristics if fewer than MIN_TRAINING_SAMPLES (20) decisions exist.
3. Output: class A (likely Catalan, >= 0.7), B (uncertain, 0.4-0.7),
   C (likely false positive, < 0.4). Stored on Canco.ml_classe / ml_confianca.
4. Retraining: triggered automatically via recalcular_ml_si_cal() when >= 5 new
   decisions since last recalc. Runs in background daemon thread.

Model files: ml_model.joblib (RF), ml_tfidf.joblib (TF-IDF vectorizer).
"""

import logging
import re
import threading
import time
from pathlib import Path

from django.db.models import QuerySet

from .constants import (
    MIN_NEW_DECISIONS,
    MIN_TRAINING_SAMPLES,
    ML_CLASSE_A_THRESHOLD,
    ML_CLASSE_B_THRESHOLD,
    RATIO_PRIOR_K,
    RATIO_PRIOR_P,
    TFIDF_MAX_FEATURES,
)

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "ml_model.joblib"
# Signed direction vector saved alongside the RF model: for each feature
# stores `mean_approved - mean_rejected` from the training set. Positive
# means "higher value → more approvals"; negative means "higher value →
# more rejections". Magnitude is on feature scale — only the sign is
# surfaced to staff. Rebuilt on every training run.
DIRECTIONS_PATH = Path(__file__).parent / "ml_directions.joblib"
LAST_RECALC_FILE = "/tmp/tq_last_ml_recalc"

# Feature slimming (2026-04-21): the previous 23 structured + 200 TF-IDF
# model had 7 features with <0.6% importance each (total ~1.9%) plus a
# long TF-IDF tail where most features were effectively noise. Audit at
# that date showed the top 10 features carried 77% of the signal, and
# the bottom ~120 carried <0.01% combined. The set below drops:
#
#   isrc_digital, nb_collaboradors, any_llancament,
#   nb_cancons_aprovades_artista, isrc_any, isrc_prefix_q, artista_aprovat
#
# and cuts TF-IDF from 200 → 60 features (more than enough capacity for
# a char-n-gram signal from <5 k distinct titles). Total dim: 76.
FEATURE_NAMES = [
    "isrc_es",
    "isrc_international",
    "isrc_empty",
    "deezer_nb_fan",
    "deezer_nb_album",
    "deezer_nom_similitud",
    "nom_artista_len",
    "nb_decisions_artista",
    "ratio_rebuig_artista",
    "ratio_rebuig_isrc_prefix",
    "mes_llancament",
    "ratio_rebuig_registrant",
    # Whisper LID features. Extracted from Canco.whisper_all_probs (the
    # full 99-language distribution) to capture near-miss cases like
    # "Whisper says it=0.50 ca=0.45" — a much weaker rejection signal
    # than "it=0.95 ca=0.01". Missing data falls back to 0.0.
    "whisper_p_ca",
    "whisper_p_es",
    "whisper_p_en",
    "whisper_margin_ca",
    # MusicBrainz features. Sparse at start (coverage grows over time) but
    # very predictive when present: `mbrainz_confirmed=1` means MB
    # independently attests the track belongs to this artist,
    # `mb_lyrics_cat=1` means a human editor tagged the Work as Catalan,
    # `artista_te_mbid=1` means the artist is indexed at all (curated
    # artists skew heavily Catalan).
    "mbrainz_confirmed",
    "mb_lyrics_cat",
    "artista_te_mbid",
] + [f"tfidf_{i}" for i in range(TFIDF_MAX_FEATURES)]

TFIDF_PATH = Path(__file__).parent / "ml_tfidf.joblib"
# `TFIDF_MAX_FEATURES`, `RATIO_PRIOR_K`, `RATIO_PRIOR_P` live in
# `music/constants.py` since 2026-04-25 (Sprint A) so other modules
# can read the same numbers without importing the ML stack.

# P2: module-level cache for the two joblib artifacts (RF classifier +
# TF-IDF vectorizer), keyed on file mtime so recalcular_ml writing a new
# model is picked up on the next call without a gunicorn restart. The
# previous code re-read the ~1.3 MB RF model from disk on EVERY call to
# `pre_classificar` — that's ~30 ms per classification, invoked once
# per track during obtenir_novetats. The TF-IDF path was already cached
# but without invalidation (stale after retraining).
_model_cache: dict = {
    "clf_mtime": None,
    "clf": None,
    "tfidf_mtime": None,
    "tfidf": None,
}


def _get_tfidf():
    if not TFIDF_PATH.exists():
        return None
    mtime = TFIDF_PATH.stat().st_mtime
    if _model_cache["tfidf_mtime"] != mtime:
        import joblib

        _model_cache["tfidf"] = joblib.load(TFIDF_PATH)
        _model_cache["tfidf_mtime"] = mtime
    return _model_cache["tfidf"]


def _get_clf():
    """Return the cached RF classifier, reloading when the joblib file changes."""
    if not MODEL_PATH.exists():
        return None
    mtime = MODEL_PATH.stat().st_mtime
    if _model_cache["clf_mtime"] != mtime:
        import joblib

        _model_cache["clf"] = joblib.load(MODEL_PATH)
        _model_cache["clf_mtime"] = mtime
    return _model_cache["clf"]


def _tfidf_features(text: str) -> list[float]:
    """Returns TF-IDF char n-gram features for text."""
    tfidf = _get_tfidf()
    if tfidf is None:
        return [0.0] * TFIDF_MAX_FEATURES
    try:
        vec = tfidf.transform([text or ""]).toarray()[0].tolist()
    except Exception:
        return [0.0] * TFIDF_MAX_FEATURES
    # `TFIDF_MAX_FEATURES` is a CAP, not a guaranteed dimension —
    # `min_df=2` can yield a smaller vocabulary on tiny / repetitive
    # corpora, in which case `tfidf.transform()` returns a shorter
    # vector. Pad up to the cap so every row reaches the RF with a
    # consistent shape (and FEATURE_NAMES stays well-defined). Truncate
    # in the unlikely case vocab grows past the cap (defensive).
    if len(vec) < TFIDF_MAX_FEATURES:
        vec = vec + [0.0] * (TFIDF_MAX_FEATURES - len(vec))
    elif len(vec) > TFIDF_MAX_FEATURES:
        vec = vec[:TFIDF_MAX_FEATURES]
    return vec


def _isrc_category(isrc: str) -> tuple[int, int, int, int]:
    """Returns (es, digital, international, empty) as 0/1."""
    prefix = isrc[:2].upper() if len(isrc) >= 2 else ""
    if not prefix:
        return (0, 0, 0, 1)
    if prefix == "ES":
        return (1, 0, 0, 0)
    if prefix in ("QT", "QM", "QZ"):
        return (0, 1, 0, 0)
    return (0, 0, 1, 0)


def _smoothed(rej: int, total: int) -> float:
    """Bayesian-smoothed rejection ratio.

    Returns `(rej + prior_k * prior_p) / (total + prior_k)`, so an
    artist/prefix/registrant with few decisions can't jump straight
    to 0 or 1 from one or two calls. See RATIO_PRIOR_K / RATIO_PRIOR_P.
    """
    return (rej + RATIO_PRIOR_K * RATIO_PRIOR_P) / (total + RATIO_PRIOR_K)


def _get_rejection_ratio(artista_nom: str) -> tuple[int, float]:
    from music.models import HistorialRevisio

    total = HistorialRevisio.objects.filter(artista_nom=artista_nom).count()
    if total == 0:
        return (0, 0.5)
    rej = HistorialRevisio.objects.filter(
        artista_nom=artista_nom, decisio="rebutjada"
    ).count()
    return (total, _smoothed(rej, total))


def _get_isrc_prefix_rejection_ratio(isrc: str) -> float:
    from music.models import HistorialRevisio

    prefix = isrc[:2].upper() if len(isrc) >= 2 else ""
    if not prefix:
        return 0.5
    total = HistorialRevisio.objects.filter(isrc_prefix=prefix).count()
    if total == 0:
        return 0.5
    rej = HistorialRevisio.objects.filter(
        isrc_prefix=prefix, decisio="rebutjada"
    ).count()
    return _smoothed(rej, total)


def _get_registrant_rejection_ratio(isrc: str) -> float:
    from music.models import HistorialRevisio

    registrant = isrc[2:5] if len(isrc) >= 5 else ""
    if not registrant:
        return 0.5
    decs = HistorialRevisio.objects.filter(
        canco_isrc__regex=f"^.{{2}}{re.escape(registrant)}"
    )
    total = decs.count()
    if total == 0:
        return 0.5
    return _smoothed(decs.filter(decisio="rebutjada").count(), total)


def _get_registrant_rejection_ratio_excluding(isrc: str, exclude_pk: int) -> float:
    from music.models import HistorialRevisio

    registrant = isrc[2:5] if len(isrc) >= 5 else ""
    if not registrant:
        return 0.5
    decs = HistorialRevisio.objects.filter(
        canco_isrc__regex=f"^.{{2}}{re.escape(registrant)}"
    ).exclude(pk=exclude_pk)
    total = decs.count()
    if total == 0:
        return 0.5
    return _smoothed(decs.filter(decisio="rebutjada").count(), total)


def _whisper_features(
    all_probs: dict | None, fallback_lang: str = "", fallback_p: float = 0.0
) -> list[float]:
    """Pull the 4 Whisper LID features from an all_probs JSON dict.

    Returns [p_ca, p_es, p_en, margin_ca].

    When `all_probs` is missing we can still derive p_ca/p_es/p_en from
    the top-1 shortcut (fallback_lang + fallback_p) — a single-lang
    dict. But `margin_ca` = p(ca) − max(p over non-ca) would be 0 or
    equal to p(ca) in that degenerate dict, which diverges from the
    value computed against the full 99-lang distribution. To keep
    training and inference consistent across old/new rows, we zero
    out margin_ca whenever we don't have the full distribution. The
    RF then learns to rely on margin only when it's actually informed.
    """
    if not all_probs:
        p_ca = float(fallback_p or 0.0) if fallback_lang == "ca" else 0.0
        p_es = float(fallback_p or 0.0) if fallback_lang == "es" else 0.0
        p_en = float(fallback_p or 0.0) if fallback_lang == "en" else 0.0
        return [p_ca, p_es, p_en, 0.0]
    p_ca = float(all_probs.get("ca", 0.0))
    p_es = float(all_probs.get("es", 0.0))
    p_en = float(all_probs.get("en", 0.0))
    non_ca_max = max((float(v) for k, v in all_probs.items() if k != "ca"), default=0.0)
    margin = p_ca - non_ca_max
    return [p_ca, p_es, p_en, margin]


def _build_features(canco) -> list[float]:
    """Extract feature vector from a Canco.

    Must stay aligned with `FEATURE_NAMES` and with
    `_build_features_from_historial` (training side). After the
    2026-04-21 slim, structured part = 12 features + 4 Whisper.
    """
    isrc = canco.isrc or ""
    es, _digital, intl, empty = _isrc_category(isrc)
    artista = canco.artista
    nb_decisions, ratio_reb = _get_rejection_ratio(artista.nom)

    return (
        [
            float(es),
            float(intl),
            float(empty),
            float(artista.deezer_nb_fan or 0),
            float(artista.deezer_nb_album or 0),
            float(
                artista.deezer_nom_similitud
                if artista.deezer_nom_similitud is not None
                else 0.5
            ),
            float(len(artista.nom)),
            float(nb_decisions),
            float(ratio_reb),
            float(_get_isrc_prefix_rejection_ratio(isrc)),
            float(canco.data_llancament.month if canco.data_llancament else 0),
            float(_get_registrant_rejection_ratio(isrc)),
        ]
        + _whisper_features(
            canco.whisper_all_probs,
            fallback_lang=canco.whisper_lang,
            fallback_p=canco.whisper_p,
        )
        + _mb_features(canco, artista)
        + _tfidf_features(canco.nom)
    )


def _mb_features(canco, artista) -> list[float]:
    """Return [mbrainz_confirmed, mb_lyrics_cat, artista_te_mbid]."""
    return [
        1.0 if canco.mbrainz_confirmed else 0.0,
        1.0 if canco.mb_lyrics_language == "cat" else 0.0,
        1.0 if (artista and artista.musicbrainz_id) else 0.0,
    ]


def _build_features_from_historial(rec) -> list[float]:
    """Extract feature vector from an HistorialRevisio record.

    Mirrors `_build_features` (inference) but:
      * Excludes the rec itself from the rejection-ratio counts to
        prevent target leakage (the training row would "know" its own
        label via the ratio).
      * Smoothing still applies (same RATIO_PRIOR_K / RATIO_PRIOR_P).
    """
    from music.models import HistorialRevisio

    isrc = rec.canco_isrc or ""
    es, _digital, intl, empty = _isrc_category(isrc)
    prefix = isrc[:2].upper() if len(isrc) >= 2 else ""

    # Artist-level smoothed rejection ratio, excluding self.
    others = HistorialRevisio.objects.filter(artista_nom=rec.artista_nom).exclude(
        pk=rec.pk
    )
    total_others = others.count()
    if total_others > 0:
        ratio_reb = _smoothed(others.filter(decisio="rebutjada").count(), total_others)
    else:
        ratio_reb = 0.5

    # ISRC-prefix smoothed rejection ratio, excluding self.
    prefix_others = HistorialRevisio.objects.filter(isrc_prefix=prefix).exclude(
        pk=rec.pk
    )
    total_prefix = prefix_others.count()
    if total_prefix > 0:
        ratio_prefix = _smoothed(
            prefix_others.filter(decisio="rebutjada").count(), total_prefix
        )
    else:
        ratio_prefix = 0.5

    return (
        [
            float(es),
            float(intl),
            float(empty),
            float(rec.artista_deezer_nb_fan or 0),
            float(rec.artista_deezer_nb_album or 0),
            float(
                rec.artista_nom_similitud
                if rec.artista_nom_similitud is not None
                else 0.5
            ),
            float(len(rec.artista_nom)),
            float(total_others),
            float(ratio_reb),
            float(ratio_prefix),
            float(rec.data_llancament.month if rec.data_llancament else 0),
            float(_get_registrant_rejection_ratio_excluding(isrc, rec.pk)),
        ]
        + _whisper_features_from_historial(rec)
        + _mb_features_from_historial(rec)
        + _tfidf_features(rec.canco_nom)
    )


def _mb_features_from_historial(rec) -> list[float]:
    """Same signal as _mb_features but via the current Canco/Artista.

    Historical records don't snapshot MB state. Using the current state
    is a best-effort proxy: we ask "does MB now attest this track?" —
    accurate for any artist where staff has since set an MBID.
    """
    from music.models import Canco

    canco = None
    if rec.canco_deezer_id:
        canco = Canco.objects.filter(deezer_id=rec.canco_deezer_id).first()
    if canco is None and rec.canco_isrc:
        canco = Canco.objects.filter(isrc=rec.canco_isrc).first()
    if canco is None:
        return [0.0, 0.0, 0.0]
    return _mb_features(canco, canco.artista)


def _whisper_features_from_historial(rec) -> list[float]:
    """Pull Whisper LID features for a historial record.

    HistorialRevisio has no whisper_* columns (the track's Canco holds
    them). Look up the current Canco by deezer_id first, then ISRC as
    a fallback — the latter is essential because a merge or a Deezer
    reindex can leave historial rows pointing to a stale
    `canco_deezer_id` even though the Canco still exists keyed by its
    ISRC. Without this fallback, the RF was silently receiving zero
    vectors for all merged-track history (per audit finding #5).

    If neither lookup hits (track genuinely gone), return the neutral
    zero vector — the RF handles absent signal as "no evidence".
    """
    from music.models import Canco

    canco = None
    if rec.canco_deezer_id:
        canco = Canco.objects.filter(deezer_id=rec.canco_deezer_id).first()
    if canco is None and rec.canco_isrc:
        canco = Canco.objects.filter(isrc=rec.canco_isrc).first()
    if canco is None:
        return _whisper_features(None)
    return _whisper_features(
        canco.whisper_all_probs,
        fallback_lang=canco.whisper_lang,
        fallback_p=canco.whisper_p,
    )


def _artista_aprovat_from_historial(rec) -> int:
    """Look up whether the artist is currently approved."""
    from music.models import ArtistaDeezer

    if rec.artista_deezer_id:
        ad = (
            ArtistaDeezer.objects.filter(deezer_id=rec.artista_deezer_id)
            .select_related("artista")
            .first()
        )
        if ad:
            return 1 if ad.artista.aprovat else 0
    return 0


def entrenar_model() -> bool:
    """
    Train TF-IDF vectorizer + RandomForestClassifier from HistorialRevisio.
    Saves both to disk. Returns True if trained.
    """
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer

    from music.models import HistorialRevisio

    recs = list(HistorialRevisio.objects.all())
    if len(recs) < MIN_TRAINING_SAMPLES:
        logger.info(
            "Not enough training data (%d < %d)", len(recs), MIN_TRAINING_SAMPLES
        )
        return False

    # Train TF-IDF on all titles first
    titols = [rec.canco_nom or "" for rec in recs]
    tfidf = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        max_features=TFIDF_MAX_FEATURES,
        sublinear_tf=True,
        min_df=2,
    )
    tfidf.fit(titols)
    joblib.dump(tfidf, TFIDF_PATH)
    global _tfidf
    _tfidf = tfidf

    # Build dataset with TF-IDF now available
    X = []
    y = []
    for rec in recs:
        features = _build_features_from_historial(rec)
        X.append(features)
        y.append(1 if rec.decisio == "aprovada" else 0)

    clf = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        class_weight="balanced",
    )
    clf.fit(X, y)
    joblib.dump(clf, MODEL_PATH)

    # Compute per-feature direction: positive = higher value pushes
    # toward approval, negative = toward rejection. Simple mean-diff is
    # robust to the imbalance because RandomForest already handles it;
    # we only want the sign, not a calibrated effect size. Skip TF-IDF
    # entries (always ≥ 0 and noisy individually).
    try:
        import numpy as np  # noqa: F401 — lazy import, sklearn already pulls it

        n_struct = len(FEATURE_NAMES) - TFIDF_MAX_FEATURES
        arr_pos: list[list[float]] = []
        arr_neg: list[list[float]] = []
        for feats, label in zip(X, y):
            (arr_pos if label == 1 else arr_neg).append(feats[:n_struct])
        directions: dict[str, float] = {}
        if arr_pos and arr_neg:
            import statistics as stats

            for i in range(n_struct):
                mp = stats.fmean(row[i] for row in arr_pos)
                mn = stats.fmean(row[i] for row in arr_neg)
                directions[FEATURE_NAMES[i]] = mp - mn
        joblib.dump(directions, DIRECTIONS_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not compute feature directions: %s", exc)

    importances = dict(zip(FEATURE_NAMES, clf.feature_importances_))
    sorted_imp = sorted(importances.items(), key=lambda x: -x[1])
    logger.info(
        "RF model trained with %d samples. Feature importances: %s",
        len(X),
        sorted_imp[:5],
    )
    return True


def pre_classificar(canco) -> dict:
    """
    Classify a Canco using the RF model if available,
    or heuristic fallback if not.
    """
    clf = _get_clf()
    if clf is not None:
        try:
            features = _build_features(canco)
            proba = clf.predict_proba([features])[0]
            # proba[1] = probability of approval (class 1)
            confianca = float(proba[1]) if len(proba) > 1 else float(proba[0])
            if confianca >= ML_CLASSE_A_THRESHOLD:
                classe = "A"
            elif confianca >= ML_CLASSE_B_THRESHOLD:
                classe = "B"
            else:
                classe = "C"
            feature_imp = sorted(
                zip(FEATURE_NAMES, clf.feature_importances_),
                key=lambda x: -x[1],
            )
            raons = [f"{n}={v:.2f}" for n, v in feature_imp[:3]]
            return {"classe": classe, "confiança": round(confianca, 2), "raons": raons}
        except Exception as exc:
            logger.warning("RF model error, falling back to heuristic: %s", exc)

    return _heuristic_classificar(canco)


def _heuristic_classificar(canco) -> dict:
    """Fallback heuristic classifier."""
    from music.models import HistorialRevisio

    raons = []
    score = 0.5
    artista = canco.artista
    isrc = canco.isrc or ""

    isrc_prefix = isrc[:2].upper() if len(isrc) >= 2 else ""
    if isrc_prefix == "ES":
        score += 0.3
        raons.append("ISRC espanyol")
    elif isrc_prefix in ("QT", "QM", "QZ"):
        score -= 0.25
        raons.append(f"ISRC distrib. digital ({isrc_prefix})")
    elif isrc_prefix:
        score -= 0.3
        raons.append(f"ISRC internacional ({isrc_prefix})")

    nom_len = len(artista.nom)
    if nom_len <= 3:
        score -= 0.3
        raons.append(f"Nom molt curt ({nom_len})")
    elif nom_len <= 6:
        score -= 0.25
        raons.append(f"Nom curt ({nom_len})")

    if artista.deezer_nb_fan is not None:
        if artista.deezer_nb_fan > 100000:
            score -= 0.35
        elif artista.deezer_nb_fan > 50000:
            score -= 0.25
        elif artista.deezer_nb_fan < 1000:
            score += 0.1

    if artista.deezer_nb_album is not None:
        if artista.deezer_nb_album > 30:
            score -= 0.25
        elif artista.deezer_nb_album > 20:
            score -= 0.15

    if artista.deezer_nom_similitud is not None:
        if artista.deezer_nom_similitud < 0.5:
            score -= 0.3
        elif artista.deezer_nom_similitud >= 0.95:
            score += 0.15

    total_hist = HistorialRevisio.objects.filter(artista_nom=artista.nom).count()
    if total_hist >= 3:
        rebutjades = HistorialRevisio.objects.filter(
            artista_nom=artista.nom, decisio="rebutjada"
        ).count()
        ratio = rebutjades / total_hist
        if ratio > 0.8:
            score -= 0.35
        elif ratio > 0.5:
            score -= 0.2
        elif ratio < 0.2:
            score += 0.2

    score = max(0.0, min(1.0, score))
    # Use the same A/B/C boundaries as the RF path (constants.ML_CLASSE_*)
    # so a fallback doesn't silently reclassify tracks at a different
    # threshold — staff would see tracks moving between A/B/C just
    # because the model file failed to load once.
    if score >= ML_CLASSE_A_THRESHOLD:
        classe = "A"
    elif score >= ML_CLASSE_B_THRESHOLD:
        classe = "B"
    else:
        classe = "C"

    return {"classe": classe, "confiança": round(score, 2), "raons": raons}


def classificar_i_guardar(canco) -> None:
    """Compute ML classification and save to the canco's db fields."""
    result = pre_classificar(canco)
    canco.ml_classe = result["classe"]
    canco.ml_confianca = result["confiança"]
    canco.save(update_fields=["ml_classe", "ml_confianca"])


def recalcular_ml(qs: QuerySet | None = None, limit: int | None = None) -> int:
    """
    Recalculate ml_classe and ml_confianca for unverified cancons.
    Retrains the RF model first if enough data.
    """
    from music.models import Canco

    # Retrain before recalculating
    entrenar_model()

    if qs is None:
        qs = Canco.objects.filter(verificada=False).select_related("artista")

    if limit:
        qs = qs[:limit]

    updated = 0
    for canco in qs.iterator() if not limit else qs:
        result = pre_classificar(canco)
        canco.ml_classe = result["classe"]
        canco.ml_confianca = result["confiança"]
        try:
            canco.save(update_fields=["ml_classe", "ml_confianca"])
            updated += 1
        except Exception:
            pass

    try:
        with open(LAST_RECALC_FILE, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass

    logger.info("ML recalculated for %d cancons", updated)
    return updated


def recalcular_ml_si_cal() -> None:
    """
    Trigger ML recalc in a background thread if ≥5 new decisions since last recalc.
    """
    from music.models import HistorialRevisio

    last_recalc = 0.0
    try:
        with open(LAST_RECALC_FILE) as f:
            last_recalc = float(f.read().strip())
    except (OSError, ValueError):
        pass

    from datetime import datetime, timezone

    last_dt = datetime.fromtimestamp(last_recalc, tz=timezone.utc)
    new_decisions = HistorialRevisio.objects.filter(created_at__gt=last_dt).count()

    if new_decisions < MIN_NEW_DECISIONS:
        return

    logger.info(
        "ML recalc triggered in background: %d new decisions since last recalc",
        new_decisions,
    )
    thread = threading.Thread(target=recalcular_ml, daemon=True, name="ml-recalc")
    thread.start()
