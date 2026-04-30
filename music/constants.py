# Shared constants for the TopQuaranta project.
# Import from here instead of using magic numbers.

DIES_CADUCITAT = 365  # tracks older than this are excluded from ingestion
MAX_POSICIONS_TOP = 40  # top N positions per territory

# Territory codes and display names — single source of truth.
# The canonical data lives in the Territori DB model (music_territori); this
# dict mirrors it for use in templates and Python constants where we want
# display strings without a DB hit.
TERRITORI_NOMS = {
    "PPCC": "Països Catalans",
    "CAT": "Catalunya",
    "VAL": "País Valencià",
    "BAL": "Illes Balears",
    "ALT": "Altres territoris",
    "AND": "Andorra",
    "CNO": "Catalunya del Nord",
    "FRA": "Franja de Ponent",
    "ALG": "L'Alguer",
    "CAR": "El Carxe",
}
# Territories that have a ranking visible on the public site.
TERRITORIS_VALIDS = ("CAT", "VAL", "BAL", "PPCC", "ALT")

# ML classifier thresholds
ML_CLASSE_A_THRESHOLD = 0.7  # confidence >= this → class A
ML_CLASSE_B_THRESHOLD = 0.4  # confidence >= this → class B (below → class C)
MIN_TRAINING_SAMPLES = 20  # minimum HistorialRevisio records to train RF
MIN_NEW_DECISIONS = 5  # new decisions since last recalc to trigger retrain

# TF-IDF capacity for the title char-n-gram features. Trimmed from 200
# (2026-04-21 audit) to 60 (Sprint B baseline) to 30 after a 5-fold CV
# A/B on 7 730 decisions (Sprint TF-IDF retall, 2026-04-25): max=30
# matched ROC-AUC (0.9998) and improved F1 (+0.0013) and Accuracy
# (+0.0006) over max=60. The bottom half of the 60-feature tail had
# individual importance <0.03 % and was acting as noise; dropping it
# tightened the decision boundary without losing signal.
TFIDF_MAX_FEATURES = 30

# Fixed ML sub-tier boundaries used by the staff status dashboard
# and the auto-approval logic. Within each main class A/B/C the band
# is split into 4 sub-bands by `ml_confianca`. The boundaries are
# fixed (not data-dependent quartiles) so auto-status decisions stay
# reproducible across reloads, and so a sub-tier definition lasts
# across retrains. Re-tune after each retrain if the distribution
# shifts noticeably.
#
# Boundaries derived from the 2026-04-30 audit on the live
# HistorialRevisio (n=4 798): A++ shows 502/502 = 100.0 % accuracy,
# A+ 99.4 %, the rest grey-zone. C-- and C- bordered 95 % rejection
# but didn't qualify for auto-reject.
ML_SUBTIER_BOUNDS: dict[str, list[tuple[str, float, float]]] = {
    "A": [
        ("A--", 0.000, 0.820),
        ("A-", 0.820, 0.950),
        ("A+", 0.950, 0.990),
        ("A++", 0.990, 1.001),
    ],
    "B": [
        ("B--", 0.000, 0.440),
        ("B-", 0.440, 0.510),
        ("B+", 0.510, 0.590),
        ("B++", 0.590, 1.001),
    ],
    "C": [
        ("C--", 0.000, 0.130),
        ("C-", 0.130, 0.240),
        ("C+", 0.240, 0.310),
        ("C++", 0.310, 1.001),
    ],
}

# A sub-tier becomes a blind-trust candidate when its accuracy on
# the last N decisions exceeds the threshold AND the sample size is
# large enough.
ML_AUTO_APPROVE_THRESHOLD = 0.995
ML_AUTO_REJECT_THRESHOLD = 0.995
ML_AUTO_MIN_SAMPLES = 200

# Sub-tiers that are currently auto-decided. Pinned manually here —
# threshold-passing alone makes a sub-tier a *candidate* on the
# dashboard, but graduating it to auto requires a deliberate edit.
# Auto-decided cançons land in HistorialRevisio with
# motiu="auto_ml" so they're excluded from the training set
# (avoids the model reinforcing its own decisions).
ML_AUTO_APPROVE_SUBTIERS: tuple[str, ...] = ("A++",)
ML_AUTO_REJECT_SUBTIERS: tuple[str, ...] = ()
MOTIU_AUTO_ML = "auto_ml"

# Bayesian smoothing on the three "ratio_rebuig_*" ML features. With
# few decisions the raw ratio rej/total is extremely noisy (two
# rejections in a row push it to 100 % and feed a reinforcement loop).
# Mixing in PRIOR_K virtual decisions at PRIOR_P (=0.5 = neutral)
# keeps the ratio anchored until there's enough real signal to overcome
# the prior. See `music/ml.py::_smoothed`.
RATIO_PRIOR_K = 5
RATIO_PRIOR_P = 0.5

# MB's Lucene score is a *search-relevance* metric, not a quality
# signal — it reflects how well-edited the MB record is, which biases
# hard towards mainstream international artists. For PPCC music (a
# niche on MB) the right answer often scores lower than a popular
# homonym. We set the floor low enough that MB's own ranking stops
# being the gatekeeper, and disambiguate ourselves via name+location
# in `mb_sync.resolve_mbid` (caught 2026-04-29 with the "Casual"
# case: US rapper at 100 vs CAT band at 91).
MB_AUTO_MATCH_SCORE = 50

# API rate limits (seconds between calls)
DEEZER_RATE_LIMIT = 1.0
LASTFM_RATE_LIMIT = 0.2
MAX_API_RETRIES = 3

# Score normalization batch size
SCORE_BATCH_SIZE = 500

# Motius de rebuig — single source of truth
MOTIUS_REBUIG = [
    ("no_catala", "No és en català"),
    ("artista_incorrecte", "El perfil Deezer no és el nostre artista"),
    ("album_incorrecte", "Àlbum incorrecte"),
    ("no_musica", "No és música"),
]
MOTIUS_VALIDS = {m[0] for m in MOTIUS_REBUIG}
